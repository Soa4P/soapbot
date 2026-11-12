"""Persona autonomy knobs and a deterministic, host-owned warmth model.

Why these live in ``extra`` rather than as new ``Persona`` fields
---------------------------------------------------------------
The panel's editor only knows nine fields. Adding three known fields would make
every save from the panel silently replace them with defaults — the exact failure
``dump_persona_file`` already guards against for hand-written keys. Keeping them
in ``extra`` means: the panel preserves them on save, the serialiser writes them
back, and :func:`parse_autonomy` is the single place that validates their shape.

Warmth is deterministic and computed by the host, never written by a model. A
model-authored "how close are we" number would be a persistent, cross-session
write driven by untrusted output — the same shape the memory layers refuse.
"""

from __future__ import annotations

import math
import threading
import time
from dataclasses import dataclass
from typing import Any

MAX_SESSIONS = 50
MAX_DAILY_LIMIT = 20
WINDOW_SECONDS = 7 * 24 * 3600


@dataclass(frozen=True, slots=True)
class WarmthParams:
    baseline: float = 0.10
    growth: float = 0.15
    decay_per_hour: float = 0.01
    threshold: float = 0.60

    @classmethod
    def from_mapping(cls, raw: Any) -> WarmthParams:
        if not isinstance(raw, dict):
            return cls()
        values: dict[str, float] = {}
        for name in ("baseline", "growth", "decay_per_hour", "threshold"):
            try:
                value = float(raw.get(name, getattr(cls(), name)))
            except (TypeError, ValueError):
                value = float(getattr(cls(), name))
            values[name] = min(1.0, max(0.0, value))
        return cls(**values)


@dataclass(frozen=True, slots=True)
class AutonomyConfig:
    """What one persona allows the bot to do on its own."""

    sessions: tuple[str, ...] = ()
    daily_limit: int = 2
    warmth: WarmthParams = WarmthParams()
    voice_self_select: bool = False

    def allows_session(self, session_key: str) -> bool:
        return session_key in self.sessions


def parse_autonomy(persona: Any) -> AutonomyConfig:
    """Validate the three optional keys in a persona card's front matter.

    A malformed value falls back to the conservative default rather than raising
    at startup: a typo in a persona file must not stop the bot, but it also must
    not silently widen what the bot may do on its own.
    """
    extra = getattr(persona, "extra", None) or {}
    raw = extra.get("autonomy") if isinstance(extra, dict) else None
    sessions: tuple[str, ...] = ()
    daily_limit = 2
    if isinstance(raw, dict):
        listed = raw.get("sessions") or []
        if isinstance(listed, list):
            sessions = tuple(str(s) for s in listed[:MAX_SESSIONS] if isinstance(s, str))
        try:
            daily_limit = min(MAX_DAILY_LIMIT, max(0, int(raw.get("daily_limit", 2))))
        except (TypeError, ValueError):
            daily_limit = 2
    warmth = WarmthParams.from_mapping(extra.get("warmth") if isinstance(extra, dict) else None)
    voice = bool(extra.get("voice_self_select", False)) if isinstance(extra, dict) else False
    return AutonomyConfig(
        sessions=sessions,
        daily_limit=daily_limit,
        warmth=warmth,
        voice_self_select=voice,
    )


def compute_warmth(
    interactions: int, hours_since_last: float, params: WarmthParams | None = None
) -> float:
    """Log-normalised recent activity minus a linear idle decay, clamped to [0, 1]."""
    p = params or WarmthParams()
    score = p.baseline + p.growth * math.log1p(max(0, interactions))
    score -= p.decay_per_hour * max(0.0, hours_since_last)
    return min(1.0, max(0.0, score))


class WarmthTracker:
    """In-memory, per-session interaction counts for the current seven-day window.

    Deliberately not persisted: warmth is a *conversation* signal, not an identity
    record. A restart starting from zero is honest and avoids inventing an intimate
    history from stale rows. Bounded so a busy group cannot grow it without limit.
    """

    def __init__(self) -> None:
        self._events: dict[str, list[float]] = {}
        self._lock = threading.Lock()
        self._max_sessions = 2000

    def record(self, session_key: str, *, now: float | None = None) -> None:
        ts = time.time() if now is None else now
        with self._lock:
            if session_key not in self._events and len(self._events) >= self._max_sessions:
                oldest = min(self._events, key=lambda k: self._events[k][-1])
                del self._events[oldest]
            events = self._events.setdefault(session_key, [])
            events.append(ts)
            cutoff = ts - WINDOW_SECONDS
            self._events[session_key] = [t for t in events if t >= cutoff][-500:]

    def warmth(
        self,
        session_key: str,
        params: WarmthParams | None = None,
        *,
        now: float | None = None,
    ) -> float:
        ts = time.time() if now is None else now
        with self._lock:
            events = [t for t in self._events.get(session_key, []) if ts - t <= WINDOW_SECONDS]
        if not events:
            return 0.0
        return compute_warmth(len(events), (ts - max(events)) / 3600.0, params)

    def clear(self) -> None:
        with self._lock:
            self._events.clear()


#: One process owns one pipeline; the same object is read by ``SessionView`` and
#: written by ``PersistReplyStage``, so they cannot disagree about the count.
WARMTH_TRACKER = WarmthTracker()
