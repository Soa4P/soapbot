"""Idle-boundary compaction gate.

Compaction is a second model call, so both directions of the trade-off are real:
running it on a timer burns money on groups that went quiet, and never running it
lets the context fill with the same conversation until every reply pays for it.

The condition is therefore two-sided — **idle long enough** and **context large
enough**. Either one alone produces the wrong behaviour: idle-only compacts a group
with three messages, size-only compacts in the middle of an argument.

The write path lives in :mod:`soapbot.memory.idle_fold` (``IdleFoldRunner``), which
drives the *engine's own incremental fold* at the idle boundary and persists through
``MemoryStore.save_summary`` — vet guard, L0 row-id watermark, the same path the
turn-time fold uses. An earlier variant wrote a separate row via ``MemoryLayers``
with an epoch timestamp in ``window_end``; that poisoned the fold watermark and
bypassed the vet guard, and was removed when the runner was wired.
"""

from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True, slots=True)
class CompactionOutcome:
    compacted: bool
    reason: str


def should_compact(
    *,
    now: float,
    last_activity: float,
    idle_minutes: int,
    tokens: int,
    token_threshold: int,
) -> CompactionOutcome:
    """The gate on its own, so the policy can be tested without a model or a database."""
    if idle_minutes <= 0 or token_threshold <= 0:
        return CompactionOutcome(False, "disabled")
    if now - last_activity < idle_minutes * 60:
        return CompactionOutcome(False, "active")
    if tokens < token_threshold:
        return CompactionOutcome(False, "below_threshold")
    return CompactionOutcome(True, "ready")
