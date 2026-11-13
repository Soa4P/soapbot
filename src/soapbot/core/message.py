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

from soapbot.config import settings


def scrub_surrogates(text: str) -> str:
    """Replace lone surrogates so the string can be encoded and logged.

    A JSON payload can carry ``\\ud800`` on its own — the escape is legal, the resulting
    code point is not. Python happily holds it in a ``str``, and then three separate
    things break later, in three unrelated places: ``.encode('utf-8')`` raises
    ``UnicodeEncodeError`` when the message is persisted, ``json.dumps`` produces a
    document no other parser accepts, and the log formatter raises *inside* the error
    handler while reporting the first failure.

    ``errors="replace"`` through UTF-8 is the cheapest correct normalisation: it turns the
    unpaired half of a pair into U+FFFD and leaves every valid character — including
    astral-plane emoji, which are a legitimate surrogate *pair* in UTF-16 terms — intact.
    """
    if not text:
        return text
    try:
        text.encode("utf-8")
    except UnicodeEncodeError:
        return text.encode("utf-8", "replace").decode("utf-8", "replace")
    return text


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
    def record(b64: str = "", *, url: str = "", path: str = "") -> MessageSegment:
        """A voice message. OneBot takes the audio inline, hence ``b64`` first.

        Sent as base64 rather than a local path on purpose: a path would be read by the
        *adapter's* machine, which is not necessarily the bot's once the two run in
        separate containers.
        """
        payload: dict[str, Any] = {}
        if b64:
            payload["file"] = f"base64://{b64}"
        if url:
            payload["url"] = url
        if path:
            payload["path"] = path
        return MessageSegment(SegmentType.RECORD, payload)

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

    truncated: bool = False
    """Whether normalisation dropped or shortened anything.

    Kept on the event rather than only logged, because the *reply* may need to say so:
    a bot that silently answers the first 8000 characters of a 40 000-character paste
    looks like it ignored the rest of the question.
    """

    session_key_override: str = ""
    """Replace the derived session key when set (unified chat).

    Only the host's session mapper sets this, and only when the operator bound the
    sender's platform identity to an account (``accounts.qq_user_id``): the QQ private
    message then joins the account's ``web:private:account-<id>`` session so every
    client sees one continuous conversation. ``adapter`` stays ``onebot11`` — the
    reply must still route back to the platform the message came from. Default empty
    means "use the derived key"; unset it never happens by accident.
    """

    def __post_init__(self) -> None:
        """Bound and sanitise the message at construction, once.

        Deliberately here and not in a pipeline stage. Every adapter builds one of these,
        and the stages that follow — injection screening, recall, prompt assembly — all
        cost time proportional to the text. A limit enforced in one stage would still let
        the earlier stages pay for the oversized input, and a limit enforced in each
        adapter would be four copies that drift.

        The three limits answer three different attacks, so they are separate knobs:
        many segments (array flood), one huge segment (single-string flood), and a large
        total (death by a thousand segments).
        """
        self.adapter = scrub_surrogates(self.adapter)
        self.group_name = scrub_surrogates(self.group_name)
        self.sender.nickname = scrub_surrogates(self.sender.nickname)
        self.sender.card = scrub_surrogates(self.sender.card)

        max_segments = settings.max_segments
        if len(self.segments) > max_segments:
            # Keep the head: an @mention and the first line of text are at the front, and
            # those decide whether this message is even addressed to the bot. Dropping the
            # tail loses content; dropping the head would lose the addressing.
            self.segments = self.segments[:max_segments]
            self.truncated = True

        budget = settings.max_incoming_chars
        per_segment = settings.max_segment_chars
        remaining = budget
        kept: list[MessageSegment] = []
        for segment in self.segments:
            if segment.type is SegmentType.TEXT:
                text = scrub_surrogates(str(segment.data.get("text", "")))
                allowed = min(per_segment, remaining)
                if len(text) > allowed:
                    text = text[:allowed]
                    self.truncated = True
                remaining -= len(text)
                if remaining <= 0:
                    # Budget exhausted. Stop rather than keep appending empty text
                    # segments, which would inflate the segment count for nothing.
                    if text:
                        kept.append(MessageSegment(SegmentType.TEXT, {"text": text}))
                    self.truncated = True
                    break
                segment.data["text"] = text
            kept.append(segment)
        self.segments = kept

    @property
    def is_blank(self) -> bool:
        """Nothing worth running through the pipeline.

        Three shapes arrive looking like a message and are not one: ``content: null``
        (an empty segment list), ``content: "   "`` (whitespace), and a bare ``@bot``
        with no text. All three would otherwise reach the model, cost a provider call,
        and produce a reply to nothing — which reads as the bot talking to itself.

        An image is *not* blank: the model can describe it, so it is a real message even
        with no text. A face or a file is blank, because nothing downstream can use it.
        """
        if any(segment.type is SegmentType.IMAGE for segment in self.segments):
            return False
        return not any(
            segment.type is SegmentType.TEXT and str(segment.data.get("text", "")).strip()
            for segment in self.segments
        )

    @property
    def session_key(self) -> str:
        """Stable key used for conversation isolation and per-session locking."""
        if self.session_key_override:
            return self.session_key_override
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

    @property
    def addresses_me(self) -> bool:
        """Whether this message is aimed at the bot specifically.

        Private messages always are. In a group it takes an AT segment naming this
        account — ``all`` (``@全体成员``) does not count, because that is addressed to
        everyone and a bot that treats it as a direct mention would answer every
        announcement.

        Used by dispatch backpressure to decide whether silence is acceptable. Dropping
        an ordinary group message costs a missed read; dropping an @mention is
        indistinguishable from a dead bot, and that is exactly the failure this project
        kept being told about.
        """
        if self.scene is MessageScene.PRIVATE:
            return True
        if not self.self_id:
            return False
        for segment in self.segments:
            if segment.type is not SegmentType.AT:
                continue
            target = str(segment.data.get("qq", ""))
            if target and target == self.self_id:
                return True
        return False


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
