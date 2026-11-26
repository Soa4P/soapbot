"""Live-room status: poll a followed room, announce when it starts or stops (product面: bili 直播).

Why this is its own module
--------------------------
The video path answers a question somebody asked ("what is this video"). This one is the
opposite shape: nothing asks, and the answer changes on its own. Everything here follows
from that:

* **Transitions, not states.** A room that has been live for six hours is one
  announcement, not one per poll. The announcer keeps the last observed state per room
  and speaks only when it changes.
* **A cold start is silent.** The first poll of a process records the baseline. Speaking
  it would mean a restart narrates "room X is live" for every room that happens to be
  live right now — which is how an operator turns the feature off.
* **Failure is not an event.** A refused request or a 风控 answer changes nothing: the
  last known state stays, and the next poll tries again. Announcing "cannot check" once
  per interval is noise dressed as information.
* **Bounded by the same throttle as everything else.** Polling uses the shared client, so
  the per-minute budget and the minimum interval apply to this feature too — a live check
  every five minutes does not get to be exempt from the rate that protects the account.

Delivery: the announcer takes a ``send`` callable (session key → text). The host wires it
to the runtime's existing send path, so a live announcement goes through exactly the same
``OutgoingMessage`` construction as a reply and cannot address a session by guessing a
group id.
"""

from __future__ import annotations

import logging
import time
from collections.abc import Callable, Iterable
from dataclasses import dataclass
from typing import Any

from soapbot.bilibili.client import (
    BilibiliError,
    BilibiliNotFoundError,
    BilibiliRateLimitedError,
    BilibiliRiskControlError,
)

logger = logging.getLogger(__name__)

#: ``live_status`` values from the room endpoint. 1 is live; 2 is a round-play
#: (轮播), which the platform shows as offline content — treating it as live would
#: announce rooms nobody is streaming in.
LIVE = 1


@dataclass(slots=True)
class LiveStatus:
    room_id: int
    live: bool
    title: str = ""
    online: int = 0
    area: str = ""

    @property
    def url(self) -> str:
        return f"https://live.bilibili.com/{self.room_id}"


def parse_room_info(room_id: int, data: Any) -> LiveStatus:
    """Tolerant parse of ``room/v1/Room/get_info``'s ``data``.

    Missing fields degrade to "not live with no title" rather than raising: a rename on
    Bilibili's side must not take the poller down, and the announcement is still worth
    making if only the state is known.
    """
    if not isinstance(data, dict):
        return LiveStatus(room_id=room_id, live=False)
    raw_status = data.get("live_status")
    try:
        # ``str(...)`` first: the field arrives as an int or a string depending on the
        # endpoint generation, and ``int(None)`` is the case the except below is for.
        status = int(str(raw_status)) if raw_status is not None else 0
    except (TypeError, ValueError):
        status = 0
    try:
        online = int(data.get("online") or 0)
    except (TypeError, ValueError):
        online = 0
    return LiveStatus(
        room_id=room_id,
        live=status == LIVE,
        title=str(data.get("title") or "").strip()[:200],
        online=max(0, online),
        area=str(data.get("area_name") or "").strip()[:40],
    )


def room_fetcher(client: Any) -> Callable[[int], Any]:
    """Wrap a client into the ``fetch(room_id) -> LiveStatus`` the announcer expects.

    Kept here rather than in the scheduler so the polling shape (client → payload →
    parse) is one readable chain, and so a test can build the same callable from a fake
    client without touching the scheduler.
    """

    async def fetch(room_id: int) -> LiveStatus:
        return parse_room_info(room_id, await client.live_room(room_id))

    return fetch


def render_status(status: LiveStatus) -> str:
    """One line for a manual check: unlike :func:`render_transition`, state is reported
    even when it has not changed — that is the point of asking."""
    if status.live:
        facts = " · ".join(x for x in (status.area, f"{status.online} 人气") if x)
        return f"直播中：{status.title or status.room_id}" + (f"（{facts}）" if facts else "")
    return f"未开播：{status.title or status.room_id}"


def render_transition(status: LiveStatus) -> str:
    """The one message an operator gets. Facts only: title, audience, link."""
    if status.live:
        lines = [f"【开播】{status.title or f'直播间 {status.room_id}'}"]
        if status.area:
            lines.append(f"分区：{status.area}")
        if status.online:
            lines.append(f"当前人气：{status.online}")
    else:
        lines = [f"【下播】{status.title or f'直播间 {status.room_id}'}"]
    lines.append(status.url)
    return "\n".join(lines)


class LiveAnnouncer:
    """Polls configured rooms and speaks on transitions.

    ``fetch`` and ``send`` are injected so the logic is testable without the network and
    so the host decides where announcements land.
    """

    def __init__(
        self,
        *,
        rooms: Iterable[int],
        sessions: Iterable[str],
        send: Callable[[str, str], Any] | None = None,
        audit: Any = None,
        interval_minutes: int = 5,
        clock: Callable[[], float] | None = None,
    ) -> None:
        self.rooms = tuple(sorted({int(r) for r in rooms if int(r) > 0}))
        self.sessions = tuple(s for s in sessions if s)
        self._send = send
        self._audit = audit
        #: Last observed state per room. Empty means "no baseline yet".
        self._last: dict[int, bool] = {}
        self.interval_seconds = max(60, int(interval_minutes) * 60)
        self._clock = clock or time.monotonic
        self._last_poll = 0.0

    @property
    def configured(self) -> bool:
        return bool(self.rooms and self.sessions)

    def due(self) -> bool:
        """Whether the interval has elapsed. The scheduler ticks every 30 s; this is what
        turns that into "poll every N minutes" without a second timer."""
        return self._clock() - self._last_poll >= self.interval_seconds

    async def poll(self, fetch: Callable[[int], Any], *, force: bool = False) -> list[str]:
        """``check_once`` gated by the interval. ``force`` is for a manual check."""
        if not self.configured:
            return []
        if not force and not self.due():
            return []
        self._last_poll = self._clock()
        return await self.check_once(fetch)

    async def check_once(self, fetch: Callable[[int], Any]) -> list[str]:
        """Poll every room once; return the announcements that were sent.

        Returns what it said so a caller (and a test) can assert on the outcome without
        reading logs. A room that fails is skipped silently for this round: its last
        known state stays, which is what makes a transient error harmless.
        """
        said: list[str] = []
        for room_id in self.rooms:
            try:
                status = await fetch(room_id)
            except (BilibiliNotFoundError, BilibiliRateLimitedError, BilibiliRiskControlError):
                # Expected, transient, and not worth a message each time.
                logger.info("live check skipped room=%s (transient)", room_id)
                continue
            except BilibiliError as exc:
                logger.warning("live check failed room=%s: %s", room_id, exc)
                continue
            except Exception as exc:  # pragma: no cover - transport surprises
                logger.warning("live check crashed room=%s: %s", room_id, type(exc).__name__)
                continue

            if not isinstance(status, LiveStatus):
                continue
            previous = self._last.get(room_id)
            self._last[room_id] = status.live
            if previous is None or previous == status.live:
                # Cold start, or nothing changed: no announcement.
                continue
            text = render_transition(status)
            said.append(text)
            await self._announce(room_id, status.live, text)
        return said

    async def _announce(self, room_id: int, live: bool, text: str) -> None:
        if self._send is None:
            logger.info("live transition room=%s live=%s (no send path configured)", room_id, live)
            return
        for session in self.sessions:
            try:
                await self._send(session, text)
            except Exception as exc:
                # One unreachable session must not stop the others.
                logger.warning(
                    "live announcement failed session=%s room=%s: %s",
                    session,
                    room_id,
                    type(exc).__name__,
                )
        if self._audit is not None:
            self._audit.record(
                kind="command",
                action="bilibili.live",
                outcome="allow",
                detail=f"room={room_id} live={live} sessions={len(self.sessions)}",
            )


def parse_rooms(text: str) -> list[int]:
    """``"123, 456"`` → ``[123, 456]``. Junk entries are dropped, not fatal.

    Operators paste room ids from all sorts of places; refusing the whole list because
    one entry has a trailing comma would be a poor trade.
    """
    out: list[int] = []
    for chunk in str(text or "").replace("，", ",").split(","):
        chunk = chunk.strip()
        if not chunk:
            continue
        try:
            value = int(chunk)
        except ValueError:
            logger.warning("ignoring non-numeric bilibili room id %r", chunk[:20])
            continue
        if value > 0 and value not in out:
            out.append(value)
    return out


__all__ = [
    "LIVE",
    "LiveAnnouncer",
    "LiveStatus",
    "parse_room_info",
    "parse_rooms",
    "render_transition",
]
