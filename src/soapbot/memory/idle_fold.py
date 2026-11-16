"""Idle-boundary pre-fold: the engine's own fold, run while nobody is talking.

Why run the fold on a timer: the turn-time fold changes the message layout near the
top of the prompt, which breaks provider prefix-cache hits exactly when the user is
most active (qq-dsh-bridge's measured win: never compact mid-conversation, compact at
the idle boundary). This runner performs the *same* fold — same compressor instance,
same summariser (the ``light`` slot), same store write path with vet + watermark —
while the session is quiet, so the next active turn starts from an already-folded
prefix and never crosses the budget mid-argument.

Selection mirrors the engine: the gate is :func:`soapbot.memory.compaction.should_compact`
(idle minutes × estimated tokens), the fold window is the same ``history_limit`` the
engine's history provider uses, and the write goes through ``MemoryStore.save_summary``
(so the vet guard and the L0 row-id watermark are identical). A run that finds no new
candidates writes nothing — the engine's own dedup (``summary != prior``) would skip
the row anyway.

Concurrency: an active turn racing this runner is last-writer-wins on the newest
``SummaryRow``; the worst case is one duplicate summary row, never lost history (L0
is append-only and untouched here). Accepted and documented rather than locked, because
the runner only fires on sessions that have been quiet for the whole idle window.
"""

from __future__ import annotations

import logging
import time
from dataclasses import dataclass
from typing import Any

from soapbot.ai.compressor import ContextCompressor
from soapbot.ai.tokens import count_messages, count_tokens
from soapbot.memory.compaction import should_compact

logger = logging.getLogger(__name__)

#: Sessions folded per ``run_due``. A cold start with many quiet sessions must not
#: spend the summariser budget on all of them in one tick; the rest wait for the next.
MAX_SESSIONS_PER_RUN = 3


@dataclass(slots=True)
class FoldOutcome:
    session_key: str
    compacted: bool
    reason: str
    folded_turns: int = 0

    def to_dict(self) -> dict[str, Any]:
        return {
            "session_key": self.session_key,
            "compacted": self.compacted,
            "reason": self.reason,
            "folded_turns": self.folded_turns,
        }


class IdleFoldRunner:
    """Folds quiet sessions' prompts at the idle boundary, through the engine's fold.

    ``compressor`` is the engine's own instance (same ``keep_recent_turns`` config);
    ``summarize`` is the engine's ``_summarize`` (the ``light`` slot). Passing both as
    callables keeps this module free of the engine, the same way the engine is kept
    free of SQL.
    """

    def __init__(
        self,
        store,
        *,
        compressor: ContextCompressor,
        summarize,
        history_limit: int,
        idle_minutes: int,
        token_threshold: int,
        max_sessions_per_run: int = MAX_SESSIONS_PER_RUN,
    ) -> None:
        self._store = store
        self._compressor = compressor
        self._summarize = summarize
        self._history_limit = max(2, int(history_limit))
        self._idle_minutes = int(idle_minutes)
        self._token_threshold = int(token_threshold)
        self._max_per_run = max(1, int(max_sessions_per_run))

    async def run_due(self, *, now: float | None = None) -> list[dict[str, Any]]:
        """Fold every quiet session whose next prompt would cross the token gate.

        Never raises: a session whose fold fails is reported in the outcomes and the
        remaining sessions still run (same isolation contract as the scheduler's
        other units).
        """
        now = time.time() if now is None else now
        sessions = await self._store.list_sessions(limit=200)
        outcomes: list[dict[str, Any]] = []
        folded_count = 0
        for row in sessions:
            if folded_count >= self._max_per_run:
                break
            session_key = str(row.get("session_key", ""))
            last_activity = float(row.get("last_at", 0.0))
            outcome = await self._fold_one(session_key, last_activity=last_activity, now=now)
            outcomes.append(outcome.to_dict())
            if outcome.compacted:
                folded_count += 1
        if folded_count:
            logger.info("idle fold: %d session(s) folded", folded_count)
        return outcomes

    async def _fold_one(
        self, session_key: str, *, last_activity: float, now: float | None = None
    ) -> FoldOutcome:
        now = time.time() if now is None else now
        summary, watermark = await self._store.latest_summary_meta(session_key)
        history = await self._store.history(session_key, limit=self._history_limit)
        tokens = count_messages(history) + (count_tokens(summary) if summary else 0)
        gate = should_compact(
            now=now,
            last_activity=last_activity,
            idle_minutes=self._idle_minutes,
            tokens=tokens,
            token_threshold=self._token_threshold,
        )
        if not gate.compacted:
            return FoldOutcome(session_key=session_key, compacted=False, reason=gate.reason)

        try:
            result = await self._compressor.compress(
                history, prior_summary=summary, prior_watermark=watermark
            )
        except Exception as exc:
            logger.warning(
                "idle fold compress failed session=%s err=%s", session_key, type(exc).__name__
            )
            return FoldOutcome(session_key=session_key, compacted=False, reason="compress_failed")

        changed = result.summary != summary and result.summary.strip()
        if not changed or result.folded_turns <= 0:
            # Nothing new to fold (engine dedup semantics): no row, no spam.
            return FoldOutcome(session_key=session_key, compacted=False, reason="no_new_candidates")

        try:
            await self._store.save_summary(
                session_key,
                result.summary,
                result.folded_turns,
                watermark=result.watermark,
                window_start=result.window_start,
            )
        except Exception as exc:
            logger.warning(
                "idle fold save failed session=%s err=%s", session_key, type(exc).__name__
            )
            return FoldOutcome(session_key=session_key, compacted=False, reason="write_failed")

        return FoldOutcome(
            session_key=session_key,
            compacted=True,
            reason="folded",
            folded_turns=result.folded_turns,
        )
