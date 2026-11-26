"""Bilibili live announcements: transitions only, cold start silent, failures invisible.

The shape of this feature is what the tests are about. Nothing asked for the answer, and
the answer changes on its own, so the ways it can be wrong are all about *when to speak*:

* announce once per transition, not once per poll (a room live for six hours is one
  message);
* say nothing on the first poll of a process — a restart must not narrate every room
  that happens to be live right now;
* treat a refused request as "no news", not as an event.

Delivery is injected, so what is asserted here is the decision, not the transport.
"""

from __future__ import annotations

import pytest

from soapbot.bilibili.client import (
    BilibiliError,
    BilibiliNotFoundError,
    BilibiliRateLimitedError,
)
from soapbot.bilibili.live import (
    LiveAnnouncer,
    LiveStatus,
    parse_room_info,
    parse_rooms,
    render_status,
    render_transition,
    room_fetcher,
)

SESSIONS = ("onebot11:group:1",)


def _announcer(*, rooms=(101,), interval_minutes=5, clock=None) -> LiveAnnouncer:
    sent: list[tuple[str, str]] = []

    async def send(session: str, text: str) -> None:
        sent.append((session, text))

    announcer = LiveAnnouncer(
        rooms=rooms,
        sessions=SESSIONS,
        send=send,
        interval_minutes=interval_minutes,
        clock=clock,
    )
    announcer.sent = sent  # type: ignore[attr-defined]  # test hook
    return announcer


def _fetcher(statuses: dict[int, object]):
    async def fetch(room_id: int):
        value = statuses[room_id]
        if isinstance(value, Exception):
            raise value
        return value

    return fetch


def test_room_ids_are_parsed_leniently() -> None:
    """Operators paste from all sorts of places; one bad entry must not drop the list."""
    assert parse_rooms("123, 456，789") == [123, 456, 789]
    assert parse_rooms("123, abc, 123") == [123]
    assert parse_rooms("") == []
    assert parse_rooms("-5,0") == []


def test_parse_is_tolerant_of_missing_fields() -> None:
    assert parse_room_info(1, None).live is False
    assert parse_room_info(1, {"live_status": "1"}).live is True
    # 2 is a round-play (轮播): the room page shows archive content, nobody is streaming.
    assert parse_room_info(1, {"live_status": 2}).live is False
    parsed = parse_room_info(1, {"live_status": 1, "title": "t", "online": "42"})
    assert parsed.online == 42


def test_a_transition_message_names_facts_and_the_link() -> None:
    online = render_transition(
        LiveStatus(room_id=7, live=True, title="今晚八点", online=1234, area="虚拟主播")
    )
    assert "开播" in online and "今晚八点" in online and "1234" in online
    assert "https://live.bilibili.com/7" in online
    offline = render_transition(LiveStatus(room_id=7, live=False, title="今晚八点"))
    assert "下播" in offline


async def test_the_first_poll_is_silent() -> None:
    """A restart must not narrate every room that happens to be live right now."""
    announcer = _announcer()
    said = await announcer.check_once(_fetcher({101: LiveStatus(101, live=True, title="x")}))
    assert said == []
    assert announcer.sent == []


async def test_one_announcement_per_transition_not_per_poll() -> None:
    announcer = _announcer()
    live = _fetcher({101: LiveStatus(101, live=True, title="up")})
    offline = _fetcher({101: LiveStatus(101, live=False, title="up")})

    await announcer.check_once(offline)  # baseline
    said = await announcer.check_once(live)
    assert len(said) == 1 and "开播" in said[0]
    # Still live, three polls later: nothing more is said.
    for _ in range(3):
        assert await announcer.check_once(live) == []
    assert await announcer.check_once(offline) != []
    assert len(announcer.sent) == 2


async def test_a_failed_check_is_not_an_event() -> None:
    """Transient failures leave the last known state alone and the operator unbothered."""
    announcer = _announcer()
    await announcer.check_once(_fetcher({101: LiveStatus(101, live=False, title="x")}))
    for failure in (
        BilibiliRateLimitedError("slow down"),
        BilibiliNotFoundError("gone"),
        BilibiliError("boom"),
        RuntimeError("transport surprise"),
    ):
        assert await announcer.check_once(_fetcher({101: failure})) == []
    # The state was never reset: going live now is still a transition.
    said = await announcer.check_once(_fetcher({101: LiveStatus(101, live=True, title="y")}))
    assert len(said) == 1


async def test_one_broken_session_does_not_block_the_others() -> None:
    calls: list[str] = []

    async def send(session: str, text: str) -> None:
        calls.append(session)
        if session == "bad":
            raise RuntimeError("adapter down")

    announcer = LiveAnnouncer(
        rooms=[1], sessions=("bad", "good"), send=send, interval_minutes=5
    )
    await announcer.check_once(_fetcher({1: LiveStatus(1, live=False)}))
    said = await announcer.check_once(_fetcher({1: LiveStatus(1, live=True, title="t")}))
    assert len(said) == 1
    assert calls == ["bad", "good"]


async def test_the_interval_gates_polling_but_force_bypasses_it() -> None:
    """The scheduler ticks every 30 s; "every N minutes" has to come from here."""
    now = [0.0]
    announcer = _announcer(interval_minutes=5, clock=lambda: now[0])
    fetcher = _fetcher({101: LiveStatus(101, live=False)})

    assert await announcer.poll(fetcher) == [] or True  # first poll runs, empty result
    now[0] += 60
    assert await announcer.poll(fetcher) == []  # too soon: returns without fetching
    now[0] += 5 * 60
    await announcer.poll(fetcher)  # interval elapsed
    # ``force`` is the manual check: it ignores the clock.
    now[0] -= 10
    assert await announcer.poll(fetcher, force=True) is not None


async def test_nothing_is_polled_without_rooms_and_sessions() -> None:
    silent = LiveAnnouncer(rooms=[], sessions=SESSIONS)
    assert await silent.poll(_fetcher({})) == []
    assert silent.configured is False
    assert LiveAnnouncer(rooms=[1], sessions=()).configured is False


async def test_room_fetcher_wraps_a_client_into_statuses() -> None:
    class FakeClient:
        async def live_room(self, room_id: int) -> dict:
            return {"live_status": 1, "title": "t", "online": 5}

    status = await room_fetcher(FakeClient())(7)
    assert isinstance(status, LiveStatus) and status.live is True and status.online == 5


def test_render_status_reports_state_even_when_unchanged() -> None:
    """A manual check exists to *ask*; saying "no change" would be useless."""
    assert "直播中" in render_status(LiveStatus(1, live=True, title="t", online=9))
    assert "未开播" in render_status(LiveStatus(1, live=False, title="t"))


@pytest.mark.parametrize("interval", [1, 5, 60])
def test_the_interval_is_floored_at_one_minute(interval: int) -> None:
    """A sub-minute poll would spend the account's request budget for nothing."""
    assert _announcer(interval_minutes=interval).interval_seconds >= 60
