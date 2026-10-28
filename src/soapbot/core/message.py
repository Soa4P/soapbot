"""Unified message model shared by every adapter.

Adapters translate their native payloads into these types, so the pipeline,
AI layer and plugins never need to know which platform a message came from.

Design notes:
- ``MessageSegment`` is the smallest unit (text / image / at / reply / face /
  record / file). Adapters that cannot render a segment must declare it missing
  in their ``Capability`` set so the pipeline can degrade gracefully.
- ``IncomingMessage`` is what adapters emit; ``OutgoingMessage`` is what the
  pipeline hands back for delivery.
"""

from __future__ import annotations

import time
import uuid
from dataclasses import dataclass, field
from enum import StrEnum
from typing import Any


class SegmentType(StrEnum):
    TEXT = "text"
    IMAGE = "image"
    AT = "at"
    REPLY = "reply"
    FACE = "face"
    RECORD = "record"
    VIDEO = "video"
    FILE = "file"
    FORWARD = "forward"


class EventType(StrEnum):
    MESSAGE = "message"
    NOTICE = "notice"
    REQUEST = "request"
    META = "meta"


class MessageScene(StrEnum):
    """Where the message happened.

    ``CHANNEL`` is intentionally absent: QQ guild/channel support is out of scope.
    """

    GROUP = "group"
    PRIVATE = "private"


@dataclass(slots=True)
class MessageSegment:
    """One piece of a message."""

    type: SegmentType
    data: dict[str, Any] = field(default_factory=dict)

    @staticmethod
    def text(content: str) -> MessageSegment:
        return MessageSegment(SegmentType.TEXT, {"text": content})

    @staticmethod
    def image(url: str = "", *, path: str = "", b64: str = "") -> MessageSegment:
        payload: dict[str, Any] = {}
        if url:
            payload["url"] = url
        if path:
            payload["path"] = path
        if b64:
            payload["base64"] = b64
        return MessageSegment(SegmentType.IMAGE, payload)

    @staticmethod
    def at(qq: str | int) -> MessageSegment:
        return MessageSegment(SegmentType.AT, {"qq": str(qq)})

    @staticmethod
    def reply(message_id: str) -> MessageSegment:
        return MessageSegment(SegmentType.REPLY, {"id": str(message_id)})

    @property
    def is_text(self) -> bool:
        return self.type is SegmentType.TEXT

    def plain(self) -> str:
        """Best-effort plain-text rendering, used for logging and token counting."""
        if self.type is SegmentType.TEXT:
            return str(self.data.get("text", ""))
        if self.type is SegmentType.AT:
            return f"@{self.data.get('qq', '')}"
        if self.type is SegmentType.FACE:
            return f"[表情:{self.data.get('id', '')}]"
        if self.type is SegmentType.IMAGE:
            return "[图片]"
        if self.type is SegmentType.RECORD:
            return "[语音]"
        if self.type is SegmentType.VIDEO:
            return "[视频]"
        if self.type is SegmentType.FILE:
            return f"[文件:{self.data.get('name', '')}]"
        if self.type is SegmentType.FORWARD:
            return "[合并转发]"
        if self.type is SegmentType.REPLY:
            return ""
        return f"[{self.type}]"


def segments_to_plain(segments: list[MessageSegment]) -> str:
    return "".join(s.plain() for s in segments)


@dataclass(slots=True)
class Sender:
    user_id: str
    nickname: str = ""
    card: str = ""
    role: str = "member"  # owner / admin / member

    @property
    def display_name(self) -> str:
        return self.card or self.nickname or self.user_id

    @property
    def is_admin(self) -> bool:
        return self.role in ("owner", "admin")


@dataclass(slots=True)
class IncomingMessage:
    """Normalised inbound event."""

    adapter: str
    message_id: str
    scene: MessageScene
    sender: Sender
    segments: list[MessageSegment]
    group_id: str = ""
    group_name: str = ""
    self_id: str = ""
    timestamp: float = field(default_factory=time.time)
    raw: dict[str, Any] = field(default_factory=dict)
    event_type: EventType = EventType.MESSAGE
    trace_id: str = field(default_factory=lambda: uuid.uuid4().hex[:12])
    transport_authenticated: bool = True
    """Whether the transport proved the sender's identity.

    ``True`` is the correct default only because every constructor here runs
    in-process (mock protocol end, tests). **Network-facing adapters must set this
    explicitly.** When ``False``, the guard stage denies every permission, so an
    unauthenticated peer cannot benefit from a fabricated ``user_id`` or ``role``.
    """

    @property
    def session_key(self) -> str:
        """Stable key used for conversation isolation and per-session locking."""
        if self.scene is MessageScene.GROUP:
            return f"{self.adapter}:group:{self.group_id}"
        return f"{self.adapter}:private:{self.sender.user_id}"

    @property
    def text(self) -> str:
        return segments_to_plain(self.segments).strip()

    @property
    def images(self) -> list[MessageSegment]:
        return [s for s in self.segments if s.type is SegmentType.IMAGE]

    @property
    def has_image(self) -> bool:
        return any(s.type is SegmentType.IMAGE for s in self.segments)


@dataclass(slots=True)
class OutgoingMessage:
    """What the pipeline asks an adapter to deliver."""

    scene: MessageScene
    segments: list[MessageSegment]
    group_id: str = ""
    user_id: str = ""
    reply_to: str = ""
    """Message id to reply-quote when the adapter supports it."""

    @property
    def target_id(self) -> str:
        return self.group_id if self.scene is MessageScene.GROUP else self.user_id

    @property
    def text(self) -> str:
        return segments_to_plain(self.segments)


@dataclass(slots=True)
class MessageReceipt:
    ok: bool
    message_id: str = ""
    error: str = ""
