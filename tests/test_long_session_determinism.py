"""Bounds that must still hold on turn 1000, not just on turn 1.

These components are all "bounded" by construction, but bounded code has a habit of
being tested only at the happy path: one insert, one request, one message. The failure
mode this file exists for is the one that shows up after hours of traffic — a ring that
grows, a limiter that never forgets, a period key that stops rolling over.

Everything here is in-memory and clock-injected: no database, no network, no sleeps.
"""

from __future__ import annotations

from types import SimpleNamespace

import pytest

from soapbot.budget.policy import BudgetPolicy
from soapbot.core.message import IncomingMessage, MessageScene, Sender
from soapbot.core.pipeline import PipelineContext
from soapbot.core.stages import DedupStage
from soapbot.core.trace import TraceStore
from soapbot.security.ratelimit import SlidingWindowLimiter

TURNS = 1000


def _dedup_ctx(message_id: str, *, self_id: str = "1001") -> PipelineContext:
    event = IncomingMessage(
        adapter="onebot11",
        message_id=message_id,
        scene=MessageScene.GROUP,
        sender=Sender(user_id="9001"),
        segments=[],
        self_id=self_id,
    )
    return PipelineContext(event=event, adapter=None)


def _trace_ctx(trace_id: str) -> SimpleNamespace:
    return SimpleNamespace(
        event=SimpleNamespace(trace_id=trace_id, session_key="qq:group:1"),
        started_at=0.0,
        timings={},
        halted=False,
        halt_reason="",
        extras={},
    )


@pytest.mark.asyncio
async def test_dedup_capacity_does_not_grow_past_its_bound() -> None:
    stage = DedupStage(capacity=50)

    for index in range(3 * TURNS):
        assert (await stage.run(_dedup_ctx(f"m{index}"))).halt is False

    assert len(stage._seen) == 50, "the dedup ring grew past its capacity"

    # The oldest ids are gone; the most recent one is still remembered.
    assert (await stage.run(_dedup_ctx("m0"))).halt is False
    assert (await stage.run(_dedup_ctx(f"m{3 * TURNS - 1}"))).halt is True


def test_rate_limit_window_keeps_sliding_after_a_thousand_seconds() -> None:
    limiter = SlidingWindowLimiter(limit=5, window_seconds=60.0)
    allowed = 0

    # One request per second for 1000 seconds: a 60 s window with a budget of 5 can
    # admit at most 5 per minute, no matter how many turns have already happened.
    for second in range(TURNS):
        verdict = limiter.check("caller", now=1_000_000.0 + second)
        if verdict.allowed:
            allowed += 1

    assert allowed == pytest.approx(TURNS * 5 / 60, abs=6)
    assert allowed < TURNS / 10

    # A longer silence fully restores the budget, even after all those hits.
    verdict = limiter.check("caller", now=1_000_000.0 + TURNS + 61)
    assert verdict.allowed is True
    assert verdict.remaining == 4


def test_trace_ring_stays_at_its_capacity() -> None:
    store = TraceStore(capacity=40)

    for index in range(4 * TURNS):
        store.on_processed(_trace_ctx(f"t{index}"))

    traces = store.recent(limit=4 * TURNS)
    assert len(traces) == 40, "the trace ring grew past its capacity"
    # The latest trace survived; the earliest did not.
    assert traces[0].trace_id == f"t{4 * TURNS - 1}"
    assert all(trace.trace_id != "t0" for trace in traces)

    summary = store.summary()
    assert summary["historical"] is False
    assert summary["recoverable"] is False


def test_budget_period_keeps_rolling_over_a_thousand_days() -> None:
    policy = BudgetPolicy(period="month")
    base = 1_700_000_000.0  # a fixed instant; only the date arithmetic matters

    keys = [policy.period_key(now=base + day * 86_400) for day in range(TURNS)]
    months = {key[:7] for key in keys}

    # Three years of days must produce distinct months, not one frozen bucket.
    assert len(months) >= 30
    assert len(keys) == TURNS
    # Ordering is monotonic: a period key never goes backwards as time advances.
    assert keys == sorted(keys)
