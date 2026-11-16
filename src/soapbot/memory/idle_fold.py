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

#: Turn pairs the optional Dream extraction may consume per session per run
#: (SeekMemory's Dream budget template: batches are capped, not open-ended).
MAX_DREAM_PAIRS_PER_SESSION = 6


@dataclass(slots=True)
class FoldOutcome:
    session_key: str
    compacted: bool
    reason: str
    folded_turns: int = 0
    dreamed: int = 0
    """Memory rows the optional Dream extraction wrote (0 when disabled/over budget)."""

    def to_dict(self) -> dict[str, Any]:
        return {
            "session_key": self.session_key,
            "compacted": self.compacted,
            "reason": self.reason,
            "folded_turns": self.folded_turns,
            "dreamed": self.dreamed,
        }


class IdleFoldRunner:
    """Folds quiet sessions' prompts at the idle boundary, through the engine's fold.

    ``compressor`` is the engine's own instance (same ``keep_recent_turns`` config);
    ``summarize`` is the engine's ``_summarize`` (the ``light`` slot). Passing both as
    callables keeps this module free of the engine, the same way the engine is kept
    free of SQL.

    Optional Dream pass (``extractor`` + ``dream_enabled`` + ``dream_max_calls_per_day``):
    before the fold runs, the turns that are about to be folded get a model-based
    memory-extraction pass (qq-dsh-bridge's "先写记忆、再压缩"), written into L2 with
    the same vet guard as the turn-time write path. Off by default — it spends model
    calls, and heuristic-only extraction is the runtime's existing stance.
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
        extractor=None,
        dream_enabled: bool = False,
        dream_max_calls_per_day: int = 12,
    ) -> None:
        self._store = store
        self._compressor = compressor
        self._summarize = summarize
        self._history_limit = max(2, int(history_limit))
        self._idle_minutes = int(idle_minutes)
        self._token_threshold = int(token_threshold)
        self._max_per_run = max(1, int(max_sessions_per_run))
        self._extractor = extractor
        self._dream_enabled = bool(dream_enabled) and extractor is not None
        self._dream_max_calls_per_day = max(1, int(dream_max_calls_per_day))
        self._dream_day = ""
        self._dream_calls_today = 0

    async def run_due(self, *, now: float | None = None) -> list[dict[str, Any]]:
        """Fold every quiet session whose next prompt would cross the token gate.

        Never raises: a session whose fold fails is reported in the outcomes and the
        remaining sessions still run (same isolation contract as the scheduler's
        other units).
        """
        now = time.time() if now is None else now
        self._reset_daily_budget_if_new_day(now)
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

    def _reset_daily_budget_if_new_day(self, now: float) -> None:
        day = time.strftime("%Y-%m-%d", time.localtime(now))
        if day != self._dream_day:
            self._dream_day = day
            self._dream_calls_today = 0

    def _dream_budget_left(self, now: float) -> int:
        self._reset_daily_budget_if_new_day(now)
        return max(0, self._dream_max_calls_per_day - self._dream_calls_today)

    async def _dream_extract(
        self, session_key: str, pairs: list[tuple[dict[str, Any], dict[str, Any]]], now: float
    ) -> int:
        """Model-based extraction over the to-fold turn pairs → L2, vet-guarded.

        Returns the number of memory rows written. Budget: per-day LIGHT-slot calls
        (``dream_max_calls_per_day``) + per-session pair cap. Any failure (extractor,
        vet, write) is contained here and never reaches the fold.
        """
        from soapbot.security.audit import get_audit_log
        from soapbot.security.injection import vet_memory

        written = 0
        audit = get_audit_log()
        for user_msg, assistant_msg in pairs:
            if self._dream_budget_left(now) <= 0:
                logger.info("dream budget exhausted; skipping remaining pairs session=%s", session_key)
                break
            user_text = str(user_msg.get("content", ""))
            assistant_text = str(assistant_msg.get("content", ""))
            try:
                result = await self._extractor.extract(user_text, assistant_text)
            except Exception as exc:
                logger.warning("dream extract failed session=%s err=%s", session_key, type(exc).__name__)
                continue
            if result.used_model:
                self._dream_calls_today += 1
            source_id = f"dream-{user_msg.get('_id', 0)}"
            for mem in result.memories:
                allowed, reason = vet_memory(mem.content)
                if not allowed:
                    audit.record(
                        kind="memory",
                        action="store",
                        outcome="quarantine",
                        detail=f"dream extraction refused: {reason}",
                    )
                    continue
                try:
                    await self._store.add_memory(
                        content=mem.content,
                        layer=mem.layer,
                        scope=session_key,
                        importance=mem.importance,
                        source_message_id=source_id,
                    )
                    written += 1
                except Exception as exc:
                    logger.warning("dream memory write failed err=%s", type(exc).__name__)
        return written

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

        # Dream pass (optional): distill the turns that are about to be folded into
        # L2 before the fold removes them from the prompt. Candidates follow the
        # fold's own rule — window messages above the watermark (a watermark of 0,
        # i.e. the first fold, means the whole foldable window is a candidate).
        dreamed = 0
        if self._dream_enabled and self._extractor is not None:
            to_fold = [
                m
                for m in history
                if isinstance(m.get("_id"), int) and (m["_id"] > watermark or not summary)
            ]
            pairs = [
                (to_fold[i], to_fold[i + 1])
                for i in range(0, len(to_fold) - 1, 2)
                if to_fold[i].get("role") == "user" and to_fold[i + 1].get("role") == "assistant"
            ][:MAX_DREAM_PAIRS_PER_SESSION]
            if pairs:
                try:
                    dreamed = await self._dream_extract(session_key, pairs, now)
                except Exception as exc:
                    logger.warning("dream pass failed session=%s err=%s", session_key, type(exc).__name__)

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
            return FoldOutcome(session_key=session_key, compacted=False, reason="no_new_candidates", dreamed=dreamed)

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
            dreamed=dreamed,
        )
