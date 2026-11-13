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
    penalty_decay: float = 0.05
    """每次道歉/负向事件的对数衰减系数——v2 的「伤害不对称」：一次负向事件的
    减量大于一次正向交互的增量（longing 复核的设计输入，见
    docs/qq-autonomy-design.md §6）。"""

    @classmethod
    def from_mapping(cls, raw: Any) -> WarmthParams:
        if not isinstance(raw, dict):
            return cls()
        values: dict[str, float] = {}
        for name in ("baseline", "growth", "decay_per_hour", "threshold", "penalty_decay"):
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
    interactions: int,
    hours_since_last: float,
    params: WarmthParams | None = None,
    *,
    penalties: int = 0,
) -> float:
    """Log-normalised activity minus penalty decay minus idle decay.

    v2 的两处语义（longing 复核的设计输入）：

    * **伤害不对称**：负向事件按对数衰减（``penalty_decay * log1p(penalties)``），
      第一次道歉伤害最大，之后的边际递减——与正向的 log1p 增量对称；
    * **日常值回归**：有过交互史的会话，闲置衰减推得到日常（baseline），
      **推不到 0**——长期冷落被读成「回到了平常」，而不是「关系归零」。
      从未交互过的会话仍是 0。
    """
    p = params or WarmthParams()
    score = p.baseline + p.growth * math.log1p(max(0, interactions))
    score -= p.penalty_decay * math.log1p(max(0, penalties))
    score -= p.decay_per_hour * max(0.0, hours_since_last)
    if interactions == 0 and penalties == 0:
        # 从未交互过的会话保持 0——「日常」只属于有过交流的关系。
        return 0.0
    # 有过交互史的会话不会因闲置被读成「关系归零」。
    score = max(score, p.baseline)
    return min(1.0, max(0.0, score))


class WarmthTracker:
    """In-memory, per-session interaction counts for the current seven-day window.

    Deliberately not persisted: warmth is a *conversation* signal, not an identity
    record. A restart starting from zero is honest and avoids inventing an intimate
    history from stale rows. Bounded so a busy group cannot grow it without limit.
    """

    def __init__(self) -> None:
        self._events: dict[str, list[float]] = {}
        self._penalties: dict[str, list[float]] = {}
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

    def record_penalty(self, session_key: str, *, now: float | None = None) -> None:
        """Record one negative event (道歉/说错话的确定性识别，见 memory/stages）。

        与正向事件同一套有界窗口；惩罚按对数衰减计入 warmth，随窗口一起过期。
        """
        ts = time.time() if now is None else now
        with self._lock:
            if session_key not in self._penalties and len(self._penalties) >= self._max_sessions:
                oldest = min(self._penalties, key=lambda k: self._penalties[k][-1])
                del self._penalties[oldest]
            penalties = self._penalties.setdefault(session_key, [])
            penalties.append(ts)
            cutoff = ts - WINDOW_SECONDS
            self._penalties[session_key] = [t for t in penalties if t >= cutoff][-500:]

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
            penalties = [
                t for t in self._penalties.get(session_key, []) if ts - t <= WINDOW_SECONDS
            ]
        if not events and not penalties:
            return 0.0
        last = max(events or penalties)
        return compute_warmth(
            len(events),
            (ts - last) / 3600.0,
            params,
            penalties=len(penalties),
        )

    def clear(self) -> None:
        with self._lock:
            self._events.clear()
            self._penalties.clear()


#: One process owns one pipeline; the same object is read by ``SessionView`` and
#: written by ``PersistReplyStage``, so they cannot disagree about the count.
WARMTH_TRACKER = WarmthTracker()
