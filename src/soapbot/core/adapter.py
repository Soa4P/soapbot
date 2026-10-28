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
    extra: dict[str, Any] = field(default_factory=dict)


class Adapter(ABC):
    """Base class for all platform adapters."""

    meta: AdapterMeta
    capabilities: frozenset[Capability]

    def __init__(self) -> None:
        self._handlers: list[EventHandler] = []
        self._handler_tasks: set[asyncio.Task[Any]] = set()
        self.health = AdapterHealth()

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
        """Fan out an inbound event to all subscribers.

        CRITICAL: handlers run as *detached tasks*, never inline. The reader loop
        must stay free to receive API responses, but a handler (the pipeline) may
        call ``send()``, which waits for such a response. Awaiting handlers inline
        therefore deadlocks the adapter against itself: the reply is written to
        the socket, but nobody reads the acknowledgement that would unblock it.
        Ordering per session is preserved downstream by ``SessionLockManager``.
        """
        # ``REQUEST``/``META`` stay dropped: those are protocol-level handshakes the
        # adapter handles itself, and forwarding them would let a peer drive
        # plugin code before any admission check. ``NOTICE`` must pass through —
        # this early return was one of the three breaks in the notice chain, so a
        # plugin's ``on_notice`` hook could not fire even when an adapter produced
        # a notice, which made the whole capability a documented no-op.
        if event.event_type not in (EventType.MESSAGE, EventType.NOTICE):
            return
        for handler in list(self._handlers):
            task = asyncio.create_task(
                self._run_handler(handler, event),
                name=f"handler:{self.meta.name}:{event.trace_id}",
            )
            self._handler_tasks.add(task)
            task.add_done_callback(self._handler_tasks.discard)

    async def _run_handler(self, handler: EventHandler, event: IncomingMessage) -> None:
        try:
            await handler(event)
        except asyncio.CancelledError:
            raise
        except Exception:
            logger.exception(
                "event handler failed adapter=%s trace=%s", self.meta.name, event.trace_id
            )

    async def drain_handlers(self, timeout: float = 5.0) -> None:
        """Wait for in-flight handler tasks (used by tests and graceful shutdown)."""
        tasks = [t for t in self._handler_tasks if not t.done()]
        if tasks:
            await asyncio.wait(tasks, timeout=timeout)

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
