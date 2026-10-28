"""Sliding-window rate limiting for abuse detection.

Rate limiting is an authorization control here, not just a politeness measure:
`/forget 1..N` enumeration, `/recall` probing for another group's data, and
repeated injection attempts are all detectable as *bursts of denied actions*.
Limiting the attempt rate is what stops a brute-force walk from succeeding in
the window between two operator config updates.

Sliding window (not fixed window) because a fixed window lets an attacker send
the full budget at 00:59 and again at 00:01 — 2x the intended rate at the seam.
"""

from __future__ import annotations

import time
from collections import deque
from dataclasses import dataclass


@dataclass(slots=True)
class LimitResult:
    allowed: bool
    remaining: int
    retry_after: float = 0.0

    @property
    def limited(self) -> bool:
        return not self.allowed


class SlidingWindowLimiter:
    """Per-key sliding window counter."""

    def __init__(self, *, limit: int, window_seconds: float) -> None:
        if limit <= 0:
            raise ValueError("limit must be positive")
        if window_seconds <= 0:
            raise ValueError("window_seconds must be positive")
        self.limit = limit
        self.window = window_seconds
        self._hits: dict[str, deque[float]] = {}

    def check(self, key: str, *, now: float | None = None) -> LimitResult:
        ts = time.time() if now is None else now
        bucket = self._hits.setdefault(key, deque())
        cutoff = ts - self.window
        while bucket and bucket[0] < cutoff:
            bucket.popleft()

        if len(bucket) >= self.limit:
            retry_after = max(0.0, self.window - (ts - bucket[0]))
            return LimitResult(allowed=False, remaining=0, retry_after=retry_after)

        bucket.append(ts)
        return LimitResult(allowed=True, remaining=self.limit - len(bucket))

    def reset(self, key: str) -> None:
        self._hits.pop(key, None)

    def prune(self, *, now: float | None = None) -> int:
        """Drop empty buckets so a long-running process cannot leak memory."""
        ts = time.time() if now is None else now
        cutoff = ts - self.window
        stale = [
            k
            for k, bucket in self._hits.items()
            if not bucket or bucket[-1] < cutoff
        ]
        for k in stale:
            self._hits.pop(k, None)
        return len(stale)
