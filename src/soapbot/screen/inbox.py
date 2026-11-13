"""Host-owned handoff for captured screen frames: capture side → model context.

The design's rule (``docs/autonomous-capabilities-design.md`` §1.1, boundary 2) is
that frames travel one way only — into the model context — and are never persisted,
audited or handed to plugin storage. This inbox is the seam that makes that real:

* the capture side (``screen.capture`` surface) puts the tile here and keeps only a
  ref + metadata for its caller — plugin code never touches the bitmap;
* :class:`~soapbot.core.stages.ScreenFrameStage` consumes the entry once, right
  before the model runs, and appends the image to ``ctx.extras["clean_segments"]``
  (the seam ModelStage already reads) without touching the archived event;
* entries are bounded per session and expire, so a plugin that captures and never
  gets a model turn cannot grow memory or leak stale frames into a later turn.
"""

from __future__ import annotations

import threading
import time
from typing import Any

from soapbot.ai.vision import ImagePayload

_TTL_SECONDS = 120.0
_MAX_ENTRIES = 16


class ScreenInbox:
    """Bounded, per-session, one-shot handoff of screen tiles."""

    def __init__(
        self,
        *,
        ttl: float = _TTL_SECONDS,
        max_entries: int = _MAX_ENTRIES,
        clock: Any = None,
    ) -> None:
        self._ttl = ttl
        self._max = max_entries
        self._clock = clock or time.time
        self._entries: dict[str, tuple[ImagePayload, float]] = {}
        self._lock = threading.Lock()

    def put(self, session_key: str, payload: ImagePayload) -> None:
        """Store one tile for the session's next model turn. Replaces any pending
        entry: the newest look wins, stale frames are not what anyone wants to see."""
        now = self._clock()
        with self._lock:
            if len(self._entries) >= self._max and session_key not in self._entries:
                oldest = min(self._entries, key=lambda k: self._entries[k][1])
                del self._entries[oldest]
            self._entries[session_key] = (payload, now)

    def take(self, session_key: str) -> ImagePayload | None:
        """Consume the pending tile, or ``None``. Expired entries count as absent."""
        now = self._clock()
        with self._lock:
            entry = self._entries.pop(session_key, None)
        if entry is None:
            return None
        payload, stored_at = entry
        if now - stored_at > self._ttl:
            return None
        return payload

    def pending(self, session_key: str) -> bool:
        with self._lock:
            entry = self._entries.get(session_key)
            return entry is not None and self._clock() - entry[1] <= self._ttl

    def clear(self) -> None:
        with self._lock:
            self._entries.clear()


#: One host process owns one screen; the same singleton is written by the capture
#: surface and read by ScreenFrameStage, so they cannot disagree about the handoff.
SCREEN_INBOX = ScreenInbox()
