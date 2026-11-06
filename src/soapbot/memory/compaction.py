"""Idle-boundary compaction.

Compaction is a second model call, so both directions of the trade-off are real:
running it on a timer burns money on groups that went quiet, and never running it
lets the context fill with the same conversation until every reply pays for it.

The condition is therefore two-sided — **idle long enough** and **context large
enough**. Either one alone produces the wrong behaviour: idle-only compacts a group
with three messages, size-only compacts in the middle of an argument.

Failure policy: the summary is produced *before* anything is written, so a failed
call changes nothing. If the summary call succeeds but the write fails, the L1 row
is what is lost, not the conversation — L0 is append-only and never touched here.
"""

from __future__ import annotations

import logging
from collections.abc import Awaitable, Callable
from dataclasses import dataclass

from soapbot.memory.layers import MemoryLayers

logger = logging.getLogger(__name__)


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


async def compact_if_idle(
    layers: MemoryLayers,
    session_key: str,
    *,
    now: float,
    last_activity: float,
    idle_minutes: int,
    tokens: int,
    token_threshold: int,
    summarize: Callable[[], Awaitable[tuple[str, str | None]]],
    window_start: float = 0.0,
) -> CompactionOutcome:
    """Summarise the session into L1 (and optionally one L4 note) when both gates pass.

    ``summarize`` returns ``(summary, self_note_or_none)``. Injected rather than
    imported so this module never depends on the provider router, and so a test can
    describe the failure mode it is exercising.
    """
    gate = should_compact(
        now=now,
        last_activity=last_activity,
        idle_minutes=idle_minutes,
        tokens=tokens,
        token_threshold=token_threshold,
    )
    if not gate.compacted:
        return gate

    try:
        summary, note = await summarize()
    except Exception as exc:
        logger.warning(
            "compaction summarise failed session=%s err=%s", session_key, type(exc).__name__
        )
        return CompactionOutcome(False, "summarise_failed")

    if not summary.strip():
        return CompactionOutcome(False, "empty_summary")

    try:
        await layers.add_summary(
            session_key,
            summary,
            window_start=window_start,
            window_end=now,
            model="",
        )
        if note and note.strip():
            await layers.add_self_note(note, source_session=session_key)
    except Exception as exc:
        logger.warning(
            "compaction write failed session=%s err=%s", session_key, type(exc).__name__
        )
        return CompactionOutcome(False, "write_failed")

    return CompactionOutcome(True, "compacted")
