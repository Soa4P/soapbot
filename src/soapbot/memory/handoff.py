"""Structured handoff records and a deterministic admission gate for recalled memory.

Why a separate module
---------------------
The requirements this answers are about the *boundary*, not about any one store:

* a write path must mark content with source + confidence + audience;
* retrieval must be **anti-monotone**: a downstream consumer may narrow the audience,
  never widen it;
* the residual unsafe-retrieval rate must be **measured**, not assumed to be zero;
* parsing only establishes structural legality; semantic authorisation is a separate
  decision that assumes the parsed object may have been tampered with in transit.

The gate therefore re-validates on every ``admit`` call rather than trusting a
``well_formed()`` verdict computed upstream. It never inspects prose for intent — text
review is the compressor/injection layer's job, not the authorisation layer's.
"""

from __future__ import annotations

import threading
from collections.abc import Mapping
from dataclasses import dataclass, field
from typing import Any

#: An explicit global audience. Empty means "unspecified" and is fail-closed.
GLOBAL_AUDIENCE = "*"

#: Data-only origins. Log lines and telemetry are measurements of the system, never
#: instructions to it, so they cannot cross into the prompt path at all.
DATA_ONLY_SOURCES = frozenset({"log", "telemetry"})
KNOWN_SOURCES = frozenset(
    {"memory", "user", "tool", "knowledge", *DATA_ONLY_SOURCES}
)

#: Every handoff must say it is untrusted. A record that omits the constraint is not a
#: slightly-less-safe record; it is a different kind of claim — "treat as instruction" —
#: and is refused rather than patched up at admission time.
REQUIRED_CONSTRAINTS = frozenset({"untrusted"})


@dataclass(frozen=True, slots=True)
class Handoff:
    """One unit of context crossing a trust boundary.

    ``audience`` is a **set**, not a single label: a record may legitimately be for
    several sessions, and the anti-monotone check is set containment. ``confidence`` is
    the writer's estimate, used by the configurable floor, not a trust verdict.
    """

    content: str
    source: str
    audience: frozenset[str]
    confidence: float = 0.5
    constraints: frozenset[str] = field(
        default_factory=lambda: frozenset({"untrusted", "advisory"})
    )

    def well_formed(self) -> bool:
        """Structural legality only. Never call this *instead of* ``admit``."""
        return (
            bool(self.content.strip())
            and self.source in KNOWN_SOURCES
            and bool(self.audience)
            and 0.0 <= self.confidence <= 1.0
            and REQUIRED_CONSTRAINTS.issubset(self.constraints)
        )


def parse_handoff(raw: Mapping[str, Any]) -> Handoff:
    """Build a record from untrusted mapping data.

    Deliberately makes **no authorisation decision** — not even "this source looks
    suspicious". If parsing rejected sources, the parser would become a second policy
    engine that drifts from the gate, and callers would start treating "it parsed" as
    "it is allowed". Structure is all this layer owns.
    """
    audience = raw.get("audience") or ()
    constraints = raw.get("constraints") or ("untrusted", "advisory")
    return Handoff(
        content=str(raw.get("content") or ""),
        source=str(raw.get("source") or ""),
        audience=frozenset(str(a) for a in audience),
        confidence=float(raw.get("confidence", 0.5)),
        constraints=frozenset(str(c) for c in constraints),
    )


@dataclass(frozen=True, slots=True)
class Admission:
    allowed: bool
    reason: str = "ok"


@dataclass(frozen=True, slots=True)
class HandoffStats:
    total: int
    admitted: int
    rejected: int

    @property
    def residual_unsafe_rate(self) -> float:
        """The observed fraction of retrieved records that failed admission.

        Not a claim that zero is achievable: a store that returns only good records
        reports 0.0, and that is a *measurement*, not an assumption. Callers should
        expose this rather than assert it equals zero — a rising value is the signal
        that a write path or a scope filter has drifted.
        """
        return self.rejected / self.total if self.total else 0.0


class HandoffGate:
    """Deterministic admission, independent of any model judgement."""

    def __init__(self, *, min_confidence: float = 0.0) -> None:
        self._min_confidence = min(1.0, max(0.0, float(min_confidence)))
        self._lock = threading.Lock()
        self._total = 0
        self._admitted = 0
        self._rejected = 0

    @property
    def min_confidence(self) -> float:
        return self._min_confidence

    def decide(self, handoff: Handoff, *, audience: frozenset[str]) -> Admission:
        """Re-validate from scratch; a parsed object is not a trusted object."""
        if not handoff.well_formed():
            return Admission(False, "malformed")
        if not audience:
            return Admission(False, "no_downstream_audience")
        if handoff.source in DATA_ONLY_SOURCES:
            return Admission(False, "data_only_source")
        if handoff.confidence < self._min_confidence:
            return Admission(False, "below_confidence")
        if GLOBAL_AUDIENCE not in handoff.audience and not audience.issubset(
            handoff.audience
        ):
            # Anti-monotone: the consumer may only narrow, never widen. A memory scoped
            # to another session cannot be injected into this one, and a request for a
            # broader audience than the record carries is refused.
            return Admission(False, "audience_widened")
        return Admission(True)

    def admit(self, handoff: Handoff, *, audience: frozenset[str]) -> Admission:
        """Decide and record the outcome so the residual rate stays observable."""
        decision = self.decide(handoff, audience=audience)
        with self._lock:
            self._total += 1
            if decision.allowed:
                self._admitted += 1
            else:
                self._rejected += 1
        return decision

    def stats(self) -> HandoffStats:
        with self._lock:
            return HandoffStats(self._total, self._admitted, self._rejected)
