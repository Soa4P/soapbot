"""Operator-visible operation log for screen (and later, control-plane) actions.

The design's third precondition for a control plane is "the operator can watch
what the robot does, live". This ring is that view: every capture attempt, every
kill/revive, with metadata only — never pixels, never frame content. It mirrors
the audit log but is dedicated: the operator should not have to filter a general
audit stream to answer "what did the bot just do on that machine?".
"""

from __future__ import annotations

import threading
import time
from collections import deque
from typing import Any


class OpsLog:
    """Bounded, thread-safe ring of operation metadata."""

    def __init__(self, *, capacity: int = 200, clock: Any = None) -> None:
        self._capacity = capacity
        self._clock = clock or time.time
        self._entries: deque[dict[str, Any]] = deque(maxlen=capacity)
        self._lock = threading.Lock()

    def record(self, *, action: str, outcome: str, session: str = "", plugin: str = "",
               frames: int = 0, bytes_written: int = 0, reason: str = "", by: str = "") -> dict[str, Any]:
        entry = {
            "ts": self._clock(),
            "action": action,
            "outcome": outcome,
            "session": session,
            "plugin": plugin,
            "frames": frames,
            "bytes": bytes_written,
            "reason": reason,
            "by": by,
        }
        with self._lock:
            # Store a copy: the caller's dict stays theirs, so nobody can smuggle
            # extra keys into the ring after the fact.
            stored = dict(entry)
            self._entries.append(stored)
        return entry

    def recent(self, limit: int = 100) -> list[dict[str, Any]]:
        limit = max(1, min(limit, self._capacity))
        with self._lock:
            entries = list(self._entries)
        return list(reversed(entries))[:limit]

    def clear(self) -> None:
        with self._lock:
            self._entries.clear()


#: One host process owns one screen; capture entry points and the kill API all
#: write here so the operator sees one coherent sequence of what happened.
SCREEN_OPS = OpsLog()
