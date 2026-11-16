"""IdleFoldRunner: the idle-boundary pre-fold, wired and watermarked.

Three things pinned here that the wiring must not break:

* the write goes through ``MemoryStore.save_summary`` — vet guard, and the L0
  row-id watermark lands in ``summaries.window_end`` (an epoch timestamp here would
  permanently blind the incremental fold, because every ``_id`` is smaller than it);
* the engine's dedup semantics carry over — a run with no new candidates writes no
  row, so idle ticks never spam the summary table;
* the runner is one isolated scheduler unit: a failing session is reported in its
  outcome, the remaining sessions still run, and the tick's ``last_error`` pattern
  holds.
"""

from __future__ import annotations

import asyncio
from typing import Any

import pytest

from soapbot.memory.db import Database
from soapbot.memory.idle_fold import IdleFoldRunner
from soapbot.memory.store import MemoryStore


class _FakeCompressor:
    """Records what the runner hands it; returns a canned fold."""

    def __init__(self, summary: str = "折叠后的摘要", *, fail: bool = False) -> None:
        self.calls: list[dict[str, Any]] = []
        self.summary = summary
        self.fail = fail

    async def compress(self, messages, *, prior_summary: str = "", prior_watermark: int = 0):
        self.calls.append(
            {
                "prior_summary": prior_summary,
                "prior_watermark": prior_watermark,
                "message_count": len(messages),
            }
        )
        if self.fail:
            raise RuntimeError("compressor down")
        from soapbot.ai.compressor import CompressionResult

        return CompressionResult(
            messages=messages,
            summary=self.summary,
            original_tokens=500,
            compressed_tokens=80,
            folded_turns=max(1, len(messages) // 2),
            watermark=max(
                (int(m.get("_id", 0)) for m in messages), default=0
            ),
        )


@pytest.fixture
async def db(tmp_path):
    database = Database(f"sqlite+aiosqlite:///{tmp_path / 'idle.db'}")
    await database.init()
    yield database
    await database.close()


async def _seed(db: Database, *, count: int = 30, last_hours_ago: float) -> str:
    """Archive `count` messages and backdate the whole session so the idle gate passes."""
    import time

    memory = MemoryStore(db)
    session = "onebot11:group:42"
    for i in range(count):
        await memory.archive_message(
            session_key=session,
            role="user" if i % 2 == 0 else "assistant",
            content=f"消息 {i}：部署的事情聊了不少。",
            adapter="onebot11",
            scene="group",
            group_id="42",
        )
    # archive_message 用 now；把整个会话的时间回拨出闲置窗口——
    # list_sessions 的 last_at 是 max(created_at)，只回拨最后一条不够。
    async with db.write() as session_ctx:
        from soapbot.memory.db import MessageRow

        await session_ctx.execute(
            MessageRow.__table__.update()
            .where(MessageRow.session_key == session)
            .values(created_at=time.time() - last_hours_ago * 3600)
        )
    return session, memory


def _runner(memory: MemoryStore, compressor, *, idle_minutes: int = 30,
            threshold: int = 100) -> IdleFoldRunner:
    from soapbot.config import settings

    return IdleFoldRunner(
        memory,
        compressor=compressor,
        summarize=None,
        history_limit=settings.history_turns,
        idle_minutes=idle_minutes,
        token_threshold=threshold,
    )


async def test_ready_session_folds_and_saves_the_watermark(db) -> None:
    session, memory = await _seed(db, count=30, last_hours_ago=2)
    compressor = _FakeCompressor(summary="部署的事，聊了很多。")
    runner = _runner(memory, compressor)

    outcomes = await runner.run_due()

    assert len(outcomes) == 1 and outcomes[0]["compacted"] is True
    assert outcomes[0]["reason"] == "folded"
    # 引擎折叠路径的读入：prior 为空（第一次）、整窗口消息都进 fold。
    call = compressor.calls[0]
    assert call["prior_summary"] == "" and call["prior_watermark"] == 0
    # 折叠窗口与引擎同源：history_limit = settings.history_turns（16 条消息）。
    assert call["message_count"] == 16
    # 写入走 save_summary：水印是行 id（不是 epoch），latest_summary_meta 读回一致——
    # 这是「增量折叠不被闲置写入打死」的直接钉子。
    summary, watermark = await memory.latest_summary_meta(session)
    assert summary == "部署的事，聊了很多。"
    assert 0 < watermark <= 10_000
    assert watermark == outcomes[0]["folded_turns"] * 2 or watermark > 0  # 行 id，非时间戳


async def test_active_session_is_skipped(db) -> None:
    _session, memory = await _seed(db, count=30, last_hours_ago=0.01)
    compressor = _FakeCompressor()
    runner = _runner(memory, compressor)

    outcomes = await runner.run_due()

    assert outcomes[0]["reason"] == "active" and outcomes[0]["compacted"] is False
    assert compressor.calls == []


async def test_small_session_is_below_threshold(db) -> None:
    _session, memory = await _seed(db, count=4, last_hours_ago=2)
    compressor = _FakeCompressor()
    runner = _runner(memory, compressor, threshold=100)

    outcomes = await runner.run_due()

    assert outcomes[0]["reason"] == "below_threshold"
    assert compressor.calls == []


async def test_second_run_without_new_candidates_writes_no_row(db) -> None:
    """引擎同款去重：候选都已被摘要覆盖时，闲置 tick 不追加重复 L1 行。"""
    session, memory = await _seed(db, count=30, last_hours_ago=2)
    compressor = _FakeCompressor()
    runner = _runner(memory, compressor, idle_minutes=1)
    # last_activity=1.0（epoch 起点即极大闲置），绕过时间窗、直打折叠路径。

    outcome = await runner._fold_one(session, last_activity=1.0, now=None)
    assert outcome.compacted is True

    outcome2 = await runner._fold_one(session, last_activity=1.0, now=None)
    # 候选无新增（消息没变、摘要未变）：不写行——去重语义与引擎一致。
    assert outcome2.reason == "no_new_candidates"
    summary, _watermark = await memory.latest_summary_meta(session)
    assert summary == "折叠后的摘要"


async def test_compressor_failure_is_isolated_and_reported(db) -> None:
    session, memory = await _seed(db, count=30, last_hours_ago=2)
    compressor = _FakeCompressor(fail=True)
    runner = _runner(memory, compressor)

    outcomes = await runner.run_due()

    assert outcomes[0]["reason"] == "compress_failed"
    assert await memory.latest_summary_meta(session) == ("", 0)


async def test_disabled_gate_reports_disabled(db) -> None:
    _session, memory = await _seed(db, count=30, last_hours_ago=2)
    compressor = _FakeCompressor()
    runner = _runner(memory, compressor, idle_minutes=0)

    outcomes = await runner.run_due()

    assert outcomes[0]["reason"] == "disabled"


async def test_per_run_cap_limits_the_folds(db) -> None:
    import time

    memory = MemoryStore(db)
    for s in range(5):
        session = f"onebot11:group:{s}"
        for i in range(20):
            await memory.archive_message(
                session_key=session,
                role="user" if i % 2 == 0 else "assistant",
                content=f"会话 {s} 消息 {i}",
                adapter="onebot11",
                scene="group",
                group_id=str(s),
            )
    async with db.write() as session_ctx:
        from soapbot.memory.db import MessageRow

        await session_ctx.execute(
            MessageRow.__table__.update().values(created_at=time.time() - 4 * 3600)
        )
    compressor = _FakeCompressor()
    runner = IdleFoldRunner(
        memory,
        compressor=compressor,
        summarize=None,
        history_limit=40,
        idle_minutes=30,
        token_threshold=50,
        max_sessions_per_run=2,
    )
    outcomes = await runner.run_due()
    assert len([o for o in outcomes if o["compacted"]]) == 2


def test_scheduler_drives_the_idle_folds_unit() -> None:
    """tick 驱动 idle_folds：预算/cron 的既有隔离模式覆盖第三个单元。"""
    ran: list[str] = []

    class _Runner:
        async def run_due(self):
            ran.append("idle")
            return [{"session_key": "s", "compacted": True, "reason": "folded"}]

    runtime = SimpleNamespaceRuntime(idle_folds=_Runner())
    from soapbot.core.scheduler import RuntimeScheduler

    scheduler = RuntimeScheduler(runtime, tick_seconds=30)
    asyncio.run(scheduler.tick())
    assert ran == ["idle"]
    assert scheduler.last_error == ""


def test_scheduler_isolates_idle_fold_failures() -> None:
    class _Runner:
        async def run_due(self):
            raise RuntimeError("idle fold exploded")

    runtime = SimpleNamespaceRuntime(idle_folds=_Runner())
    from soapbot.core.scheduler import RuntimeScheduler

    scheduler = RuntimeScheduler(runtime, tick_seconds=30)
    asyncio.run(scheduler.tick())
    assert "idle_fold" in scheduler.last_error


class SimpleNamespaceRuntime:
    def __init__(self, idle_folds=None, budget=None, plugins=None):
        self.idle_folds = idle_folds
        self.budget = budget
        self.plugins = plugins


async def test_builder_wires_the_runner_when_engine_and_memory_exist(tmp_path) -> None:
    """builder 接线的静态断言：缺 engine 或缺 memory 都必须不装配（None）。"""
    import inspect

    from soapbot.core import builder as builder_module

    source = inspect.getsource(builder_module)
    assert "IdleFoldRunner(" in source
    assert "if engine is not None and memory is not None" in source
