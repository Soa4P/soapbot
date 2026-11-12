"""One-shot, in-memory hand-off of inbound image references to plugins.

QQ image URLs are short-lived and often signed. They must reach a plugin's own
storage and nowhere else: not a log line, not the audit trail, not the trace, and
not the messages table. This module is the entire store — there is no persistence,
no serialisation hook, and no ``__repr__`` that could carry a URL into an exception
or a f-string.

The host puts what it saw into a per-session slot at the message-hook stage. A
plugin holding ``media_observe`` takes it once and the slot disappears. Consuming
it is deliberate: unlike an event broadcast, a plugin that never asks never
receives, a URL cannot be replayed later, and a plugin for group A cannot name
group B's key because the API takes no session argument at all — the caller comes
from the host's contextvar (in-process) or the invoke frame (isolated), never from
the request body.

Only http(s) references cross the boundary. Local paths are attacker-controlled
input on a remote adapter, and inline base64 is image *content*, not a reference:
handing either to a plugin would enlarge the surface without enabling the one use
case this exists for (an operator-configured URL allowlist in the sticker plugin).
"""

from __future__ import annotations

import time
from collections.abc import Callable
from dataclasses import dataclass
from typing import Any

from soapbot.core.message import MessageSegment, SegmentType

#: A QQ image URL can expire within minutes. Keeping it longer only grows the
#: window in which a stray read could pick up an attachment from an earlier turn.
INBOX_TTL_SECONDS = 120.0
#: Bounded so one forwarded message cannot make the hand-off dominate memory.
MAX_IMAGES_PER_MESSAGE = 16
MAX_REF_CHARS = 2000

_ALLOWED_KEYS = ("url", "file")


@dataclass(slots=True, repr=False)
class _Slot:
    expires_at: float
    images: list[dict[str, str]]


def _http_reference(data: dict[str, Any]) -> str:
    for key in _ALLOWED_KEYS:
        value = data.get(key)
        if not isinstance(value, str):
            continue
        value = value.strip()
        if len(value) > MAX_REF_CHARS:
            continue
        if value.startswith(("https://", "http://")):
            return value
    return ""


class MediaInbox:
    """Per-session, TTL-bounded, consume-once slots of inbound image references."""

    def __init__(
        self,
        *,
        ttl_seconds: float = INBOX_TTL_SECONDS,
        clock: Callable[[], float] = time.monotonic,
    ) -> None:
        self._ttl = ttl_seconds
        self._clock = clock
        self._slots: dict[str, _Slot] = {}

    def put(
        self,
        session_key: str,
        segments: list[MessageSegment] | tuple[MessageSegment, ...],
    ) -> int:
        """Offer the http(s) image references of one inbound message.

        A text-only message does **not** clear an existing slot: the sticker plugin's
        flow is "send a picture, then send /meme-save", and the command is a separate
        text message. Expiry, not the next text message, is what ends the window.
        """
        images: list[dict[str, str]] = []
        for segment in segments:
            if segment.type is not SegmentType.IMAGE:
                continue
            ref = _http_reference(segment.data or {})
            if not ref:
                continue
            images.append({"url": ref})
            if len(images) >= MAX_IMAGES_PER_MESSAGE:
                break
        if not images:
            return 0
        self._evict_expired()
        self._slots[session_key] = _Slot(self._clock() + self._ttl, images)
        return len(images)

    def take(self, session_key: str) -> list[dict[str, str]]:
        """Consume and return the references for this session, or an empty list."""
        self._evict_expired()
        slot = self._slots.pop(session_key, None)
        if slot is None:
            return []
        # Copies: a plugin mutating its result must not alter another plugin's view
        # of a slot the host still owns (and must not hand it a live dict).
        return [dict(image) for image in slot.images]

    def _evict_expired(self) -> None:
        now = self._clock()
        for key, slot in list(self._slots.items()):
            if slot.expires_at <= now:
                del self._slots[key]

    def clear(self) -> None:
        """Test/host-only: drop every reference without returning any."""
        self._slots.clear()


#: One process owns one pipeline, so one inbox is enough. It is deliberately a
#: module-level object rather than an attribute of the runtime: the surface router
#: is constructed per plugin by the supervisor and has no runtime reference to walk.
MEDIA_INBOX = MediaInbox()
