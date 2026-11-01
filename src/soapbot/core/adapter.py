"""Adapter contract.

Every QQ integration (OneBot v11, QQ official, mock) implements ``Adapter``.
The core never imports a concrete adapter: it discovers them by name through
``soapbot.adapters.registry`` so a single adapter crashing cannot take down
the process.

Capability negotiation: adapters declare what they can render (markdown, at,
reply, image, record, forward, ...). The pipeline degrades any unsupported
segment instead of failing the whole reply.
"""

from __future__ import annotations

import asyncio
import logging
import time
from abc import ABC, abstractmethod
from collections.abc import Awaitable, Callable
from dataclasses import dataclass, field
from enum import StrEnum
from typing import Any

from soapbot.core.message import (
    EventType,
    IncomingMessage,
    MessageReceipt,
    MessageScene,
    MessageSegment,
    OutgoingMessage,
    SegmentType,
)

logger = logging.getLogger(__name__)


def _max_inflight_handlers() -> int:
    """Read the cap lazily so a test can move it without rebuilding the adapter."""
    from soapbot.config import settings

    return int(getattr(settings, "max_inflight_handlers", 0) or 0)


def _handler_timeout_seconds() -> float:
    from soapbot.config import settings

    return float(getattr(settings, "handler_timeout_seconds", 0) or 0)


def _busy_notice_text() -> str:
    from soapbot.config import settings

    return str(getattr(settings, "busy_notice", "") or "").strip()


def _audit_drop(
    adapter: str, event: IncomingMessage, *, inflight: int, limit: int
) -> None:
    """Dropping a message is a decision, and decisions are auditable.

    Only called for events the adapter admitted far enough to dispatch — the audit
    log is not a debug stream, and a flood of dropped traffic must not push out the
    security events it sits next to.
    """
    try:
        from soapbot.security.audit import get_audit_log

        get_audit_log().record(
            kind="rate_limit",
            action="dispatch",
            outcome="dropped",
            detail=f"inflight={inflight} limit={limit} adapter={adapter}",
            trace_id=event.trace_id,
            # ``session`` is not a ``record`` parameter; it belongs in ``meta`` so it
            # lands in the structured payload rather than being silently absorbed.
            meta_session=event.session_key,
        )
    except Exception:  # pragma: no cover - auditing must never break dispatch
        logger.debug("dispatch drop audit failed", exc_info=True)


def _audit_timeout(
    adapter: str, event: IncomingMessage, *, elapsed: float, timeout: float
) -> None:
    try:
        from soapbot.security.audit import get_audit_log

        get_audit_log().record(
            kind="rate_limit",
            action="handler",
            outcome="timeout",
            detail=f"elapsed={elapsed:.1f}s limit={timeout:.1f}s adapter={adapter}",
            trace_id=event.trace_id,
            meta_session=event.session_key,
        )
    except Exception:  # pragma: no cover
        logger.debug("handler timeout audit failed", exc_info=True)


class Capability(StrEnum):
    TEXT = "text"
    MARKDOWN = "markdown"
    IMAGE = "image"
    AT = "at"
    REPLY = "reply"
    FACE = "face"
    RECORD = "record"
    VIDEO = "video"
    FILE = "file"
    FORWARD = "forward"
    RECALL = "recall"
    MUTE = "mute"
    KICK = "kick"
    GROUP_LIST = "group_list"
    PROGRESSIVE = "progressive"
    """Can receive a reply as several messages, one per sentence.

    Declared separately from TEXT because it is a delivery-shape promise, not a
    content promise: the official QQ API has a narrow passive-reply window where a
    second unsolicited message is rejected, so an adapter must opt in rather than
    have the pipeline assume that sending twice is fine.
    """


@dataclass(slots=True)
class AdapterMeta:
    name: str
    display_name: str
    protocol: str
    docs_url: str = ""
    notes: str = ""


@dataclass(slots=True)
class AccountInfo:
    self_id: str
    nickname: str = ""
    adapter: str = ""


EventHandler = Callable[[IncomingMessage], Awaitable[None]]
Unsubscribe = Callable[[], None]


@dataclass(slots=True)
class AdapterHealth:
    online: bool = False
    last_error: str = ""
    connected_at: float = 0.0
    reconnect_attempts: int = 0
    last_seen_at: float = 0.0
    """Last time the transport proved it was alive — a frame, a reply, or a heartbeat.

    ``online`` alone cannot be trusted. A websocket can be half-open: the OS keeps the
    socket ESTABLISHED because neither side sent a FIN, but nothing will ever arrive on
    it again. Measured on a real box, a bot reported ``online = True`` for seventeen
    hours with no socket to NapCat at all (``Get-NetTCPConnection`` showed no
    connection to port 3001, the process was alive, the scheduler was ticking). The
    operator's report was "适配器和 QQ 又掉了" and every health check agreed it was fine.

    So ``online`` now means "we have evidence of life within the liveness window", and
    a socket that has gone quiet is treated as dead.
    """
    extra: dict[str, Any] = field(default_factory=dict)


class Adapter(ABC):
    """Base class for all platform adapters."""

    meta: AdapterMeta
    capabilities: frozenset[Capability]

    def __init__(self) -> None:
        self._handlers: list[EventHandler] = []
        self._handler_tasks: set[asyncio.Task[Any]] = set()
        self._notice_tasks: set[asyncio.Task[Any]] = set()
        self.health = AdapterHealth()
        # Counters rather than only a log line: a cap that silently drops is a cap
        # nobody can tune, and the operator's only symptom would be unanswered
        # messages. ``busy_notices`` is the subset of ``dropped_events`` that was a
        # direct mention and therefore got an answer instead of vanishing.
        self.dropped_events = 0
        self.busy_notices = 0
        self.handler_timeouts = 0

    # ---- lifecycle ----
    @abstractmethod
    async def start(self) -> None:
        """Connect / begin serving."""

    @abstractmethod
    async def stop(self) -> None:
        """Disconnect and release resources."""

    @abstractmethod
    async def get_self(self) -> AccountInfo:
        """Return the bot account bound to this adapter."""

    @abstractmethod
    async def send(self, message: OutgoingMessage) -> MessageReceipt:
        """Deliver a message, degrading unsupported segments."""

    # ---- group moderation ----
    # Declared capabilities without these methods were the pattern to avoid: the
    # OneBot adapter advertised ``RECALL``/``MUTE``/``KICK``/``GROUP_LIST`` in its
    # capability set while implementing none of them, so the WebUI reported a
    # group-management feature that had no code behind it. The defaults below make
    # "declared but unimplemented" impossible to ship silently: a subclass that
    # advertises the capability but forgets the method answers with an honest
    # failure instead of an AttributeError.
    #
    # Every one of these returns a receipt rather than raising, because the caller
    # is a chat command: the user needs a reason, and a traceback in the log is not
    # one. ``NotImplementedError`` is reserved for programming errors at the call
    # site, which is why these check ``supports()`` first.
    async def recall(self, message_id: str) -> MessageReceipt:
        """Withdraw one message. Requires ``Capability.RECALL``."""
        if not self.supports(Capability.RECALL):
            return MessageReceipt(ok=False, error="此适配器不支持撤回")
        raise NotImplementedError(f"{type(self).__name__} declares RECALL but has no recall()")

    async def set_group_ban(
        self, group_id: str, user_id: str, duration_seconds: int
    ) -> MessageReceipt:
        """Mute (``duration > 0``) or unmute (``duration == 0``) one member.

        ``duration_seconds`` is spelled out rather than taking a "ban/unban" flag:
        the two operations are the same protocol call with different numbers, and a
        boolean would make ``/mute 0`` ambiguous at every layer above.
        """
        if not self.supports(Capability.MUTE):
            return MessageReceipt(ok=False, error="此适配器不支持禁言")
        raise NotImplementedError(
            f"{type(self).__name__} declares MUTE but has no set_group_ban()"
        )

    async def set_group_kick(
        self, group_id: str, user_id: str, *, reject_add_request: bool = False
    ) -> MessageReceipt:
        """Remove one member from the group."""
        if not self.supports(Capability.KICK):
            return MessageReceipt(ok=False, error="此适配器不支持踢人")
        raise NotImplementedError(
            f"{type(self).__name__} declares KICK but has no set_group_kick()"
        )

    async def get_group_list(self) -> list[dict[str, Any]]:
        """Groups this account is in, as ``{group_id, group_name}`` dicts."""
        if not self.supports(Capability.GROUP_LIST):
            return []
        raise NotImplementedError(
            f"{type(self).__name__} declares GROUP_LIST but has no get_group_list()"
        )

    # ---- events ----
    def on_event(self, handler: EventHandler) -> Unsubscribe:
        self._handlers.append(handler)

        def _remove() -> None:
            if handler in self._handlers:
                self._handlers.remove(handler)

        return _remove

    async def emit(self, event: IncomingMessage) -> None:
        """Fan out an inbound event to all subscribers, bounded.

        CRITICAL: handlers run as *detached tasks*, never inline. The reader loop
        must stay free to receive API responses, but a handler (the pipeline) may
        call ``send()``, which waits for such a response. Awaiting handlers inline
        therefore deadlocks the adapter against itself: the reply is written to
        the socket, but nobody reads the acknowledgement that would unblock it.

        The cap exists because that same property is what makes an unbounded fan-out
        dangerous: every inbound line is a task that runs a full pipeline and may
        reach the model provider, so a burst costs money and memory in proportion to
        how fast strangers can type. Over the cap the event is **dropped, not
        queued** — see ``Settings.max_inflight_handlers`` for why a queue is worse.
        An @mention is answered with one detached notice instead of silence.
        """
        # ``REQUEST``/``META`` stay dropped: those are protocol-level handshakes the
        # adapter handles itself, and forwarding them would let a peer drive
        # plugin code before any admission check. ``NOTICE`` must pass through —
        # this early return was one of the three breaks in the notice chain, so a
        # plugin's ``on_notice`` hook could not fire even when an adapter produced
        # a notice, which made the whole capability a documented no-op.
        if event.event_type not in (EventType.MESSAGE, EventType.NOTICE):
            return
        if not self._handlers:
            # Nothing would run, so nothing is being dropped. Counting it would make
            # the panel report backpressure on a runtime that is merely unsubscribed.
            return

        limit = _max_inflight_handlers()
        inflight = sum(1 for task in self._handler_tasks if not task.done())
        if limit > 0 and inflight >= limit:
            self.dropped_events += 1
            addressed = event.event_type is EventType.MESSAGE and event.addresses_me
            logger.warning(
                "dispatch capped adapter=%s trace=%s inflight=%d limit=%d addressed=%s",
                self.meta.name,
                event.trace_id,
                inflight,
                limit,
                addressed,
            )
            _audit_drop(self.meta.name, event, inflight=inflight, limit=limit)
            if addressed:
                self._send_busy_notice(event)
            return

        for handler in list(self._handlers):
            task = asyncio.create_task(
                self._run_handler(handler, event),
                name=f"handler:{self.meta.name}:{event.trace_id}",
            )
            self._handler_tasks.add(task)
            task.add_done_callback(self._handler_tasks.discard)

    def _send_busy_notice(self, event: IncomingMessage) -> None:
        """Tell an overloaded @mention that it was seen, without blocking the reader.

        Detached and *not* counted against the cap: the notice is the last thing this
        adapter should refuse to do when it is already at its limit, and it must not
        occupy a slot that real work is waiting for. ``send()`` is awaited inside the
        task, never here — the reader loop is the coroutine that reads send
        acknowledgements, so awaiting it from ``emit`` deadlocks (see ``emit``).

        The outgoing message is rebuilt from the event's ids alone; holding the event
        would pin the request for as long as the socket takes to answer.
        """
        text = _busy_notice_text()
        if not text:
            return
        target = OutgoingMessage(
            scene=event.scene,
            segments=[MessageSegment.text(text)],
            group_id=event.group_id,
            user_id=event.sender.user_id,
        )
        name = f"busy:{self.meta.name}:{event.trace_id}"

        async def _send() -> None:
            try:
                receipt = await self.send(target)
            except asyncio.CancelledError:
                raise
            except Exception as exc:
                # Nothing to escalate to: the member already lost their answer, and a
                # failed apology must not become the adapter's problem too.
                logger.warning("busy notice failed adapter=%s: %s", self.meta.name, exc)
                return
            if not receipt.ok:
                logger.warning(
                    "busy notice refused adapter=%s: %s", self.meta.name, receipt.error
                )

        self.busy_notices += 1
        task = asyncio.create_task(_send(), name=name)
        # Held so the loop cannot collect the notice mid-flight; discarded on
        # completion so a long run does not accumulate finished tasks.
        self._notice_tasks.add(task)
        task.add_done_callback(self._notice_tasks.discard)

    async def _run_handler(self, handler: EventHandler, event: IncomingMessage) -> None:
        """Run one handler under a wall-clock bound.

        The bound is applied here rather than around each ``await`` inside the
        pipeline: the operator's question is "how long until this message is given
        up on", and a dozen scattered deadlines cannot answer it.

        A timeout cancels the handler and is reported, but it cannot unsend a reply
        that already went out — a partially answered message stays partially
        answered. That is a deliberate trade: the alternative is a stuck task holding
        a session lock until the process restarts.
        """
        timeout = _handler_timeout_seconds()
        started = time.monotonic()
        deadline: asyncio.Timeout | None = None
        # ``asyncio.timeout`` rather than ``wait_for`` so the deadline can be told apart
        # from a timeout *inside* the handler. ``wait_for`` converts its own expiry into
        # ``TimeoutError``, and so does a socket/provider timeout raised by the pipeline,
        # so ``except TimeoutError`` would report every slow provider as "handler stuck"
        # and inflate the counter the panel uses to decide something is wrong.
        try:
            if timeout > 0:
                async with asyncio.timeout(timeout) as deadline:
                    await handler(event)
            else:
                await handler(event)
        except TimeoutError:
            if deadline is None or not deadline.expired():
                # A TimeoutError the handler raised itself: it is the handler's failure,
                # not ours, and must not be counted as a dispatch timeout.
                logger.exception(
                    "event handler failed adapter=%s trace=%s",
                    self.meta.name,
                    event.trace_id,
                )
                return
            elapsed = time.monotonic() - started
            self.handler_timeouts += 1
            logger.error(
                "event handler timed out adapter=%s trace=%s after %.1fs",
                self.meta.name,
                event.trace_id,
                elapsed,
            )
            _audit_timeout(self.meta.name, event, elapsed=elapsed, timeout=timeout)
        except asyncio.CancelledError:
            raise
        except Exception:
            logger.exception(
                "event handler failed adapter=%s trace=%s", self.meta.name, event.trace_id
            )

    async def drain_handlers(self, timeout: float = 5.0) -> None:
        """Wait for in-flight handler tasks (used by tests and graceful shutdown)."""
        pending = self._handler_tasks | self._notice_tasks
        tasks = [t for t in pending if not t.done()]
        if tasks:
            await asyncio.wait(tasks, timeout=timeout)

    def backpressure_status(self) -> dict[str, int]:
        """Counters for the panel: a cap that never reports is a cap nobody tunes."""
        return {
            "inflight": sum(1 for t in self._handler_tasks if not t.done()),
            "dropped": self.dropped_events,
            "busy_notices": self.busy_notices,
            "handler_timeouts": self.handler_timeouts,
        }

    # ---- capability helpers ----
    def supports(self, cap: Capability) -> bool:
        return cap in self.capabilities

    def supports_segment(self, seg_type: SegmentType) -> bool:
        mapping = {
            SegmentType.TEXT: Capability.TEXT,
            SegmentType.IMAGE: Capability.IMAGE,
            SegmentType.AT: Capability.AT,
            SegmentType.REPLY: Capability.REPLY,
            SegmentType.FACE: Capability.FACE,
            SegmentType.RECORD: Capability.RECORD,
            SegmentType.VIDEO: Capability.VIDEO,
            SegmentType.FILE: Capability.FILE,
            SegmentType.FORWARD: Capability.FORWARD,
        }
        cap = mapping.get(seg_type)
        return cap is None or self.supports(cap)

    def degrade(self, segments: list[MessageSegment]) -> list[MessageSegment]:
        """Replace unsupported segments with text placeholders.

        This is the whole point of capability declaration: a reply that used
        markdown/at/record on a limited platform must still be deliverable.
        """
        out: list[MessageSegment] = []
        for seg in segments:
            if self.supports_segment(seg.type):
                out.append(seg)
            else:
                placeholder = seg.plain()
                if placeholder:
                    out.append(MessageSegment.text(placeholder))
        return out or [MessageSegment.text("")]

    def supports_scene(self, scene: MessageScene) -> bool:  # pragma: no cover - overridden
        return True
