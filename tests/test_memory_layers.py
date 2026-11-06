"""Memory layers: L1/L3/L4, the shared timeline, and the compaction gate."""

from __future__ import annotations

from pathlib import Path

import pytest

from soapbot.memory.compaction import compact_if_idle, should_compact
from soapbot.memory.db import SCHEMA_VERSION, Database
from soapbot.memory.layers import MemoryLayers


@pytest.fixture
async def db(tmp_path: Path):
    database = Database(f"sqlite+aiosqlite:///{(tmp_path / 'layers.db').as_posix()}")
    await database.init()
    yield database
    await database.close()


@pytest.fixture
def layers(db: Database, tmp_path: Path) -> MemoryLayers:
    return MemoryLayers(db, artifacts_dir=tmp_path / "artifacts", self_note_limit=3)


async def test_schema_reaches_the_layers_version(db: Database) -> None:
    assert await db.schema_version() == SCHEMA_VERSION


async def test_summary_keeps_the_window_it_describes(layers: MemoryLayers) -> None:
    await layers.add_summary(
        "session:a",
        "他们在聊部署。",
        window_start=100.0,
        window_end=200.0,
        folded_message_count=12,
        model="test-model",
    )

    latest = await layers.latest_summary("session:a")

    assert latest is not None
    assert latest["summary"] == "他们在聊部署。"
    assert latest["window_start"] == 100.0
    assert latest["window_end"] == 200.0
    assert latest["model"] == "test-model"


async def test_summaries_are_scoped_per_session(layers: MemoryLayers) -> None:
    await layers.add_summary("session:a", "A")
    await layers.add_summary("session:b", "B")

    assert (await layers.latest_summary("session:a"))["summary"] == "A"
    assert (await layers.latest_summary("session:c")) is None


async def test_self_notes_dedupe_and_evict_the_oldest(layers: MemoryLayers) -> None:
    assert await layers.add_self_note("不要抢话") is True
    assert await layers.add_self_note("  不要抢话  ") is False, "same sentence must refresh, not duplicate"
    await layers.add_self_note("回答短一点")
    await layers.add_self_note("别用感叹号")
    await layers.add_self_note("记住对方的名字")

    notes = await layers.self_notes()
    contents = [note["content"] for note in notes]

    assert len(notes) == 3
    assert "不要抢话" not in contents, "the oldest note is the one evicted"
    assert "记住对方的名字" in contents


async def test_artifacts_are_verified_by_digest(layers: MemoryLayers) -> None:
    stored = await layers.add_artifact(
        session_key="session:a", title="周报", data=b"hello artifact", suffix=".md"
    )

    assert layers.read_artifact(stored["sha256"]) == b"hello artifact"

    Path(stored["path"]).write_bytes(b"tampered")
    assert layers.read_artifact(stored["sha256"]) is None


async def test_artifact_index_lists_newest_first(layers: MemoryLayers) -> None:
    await layers.add_artifact(session_key="s", title="first", data=b"1")
    await layers.add_artifact(session_key="s", title="second", data=b"2")

    rows = await layers.artifacts("s")

    assert [row["title"] for row in rows] == ["second", "first"]


async def test_timeline_orders_newest_first_and_scopes(layers: MemoryLayers) -> None:
    await layers.record_event("chat", "收到 1 条消息", ref="m1", session_key="s")
    await layers.record_event("tool", "调用了搜索", ref="t1", session_key="s")
    await layers.record_event("chat", "别处", ref="m2", session_key="other")

    rows = await layers.recent_events("s", limit=5)

    assert [row["kind"] for row in rows] == ["tool", "chat"]


def test_compaction_needs_both_gates() -> None:
    active = should_compact(
        now=1000, last_activity=1000, idle_minutes=30, tokens=99_999, token_threshold=6000
    )
    small = should_compact(
        now=99_999, last_activity=0, idle_minutes=30, tokens=10, token_threshold=6000
    )
    ready = should_compact(
        now=99_999, last_activity=0, idle_minutes=30, tokens=99_999, token_threshold=6000
    )

    assert active.reason == "active"
    assert small.reason == "below_threshold"
    assert ready.compacted is True


async def test_compaction_writes_l1_and_an_optional_note(layers: MemoryLayers) -> None:
    async def summarise() -> tuple[str, str | None]:
        return "这段在讨论部署。", "少用术语"

    outcome = await compact_if_idle(
        layers,
        "session:a",
        now=10_000,
        last_activity=0,
        idle_minutes=30,
        tokens=99_999,
        token_threshold=6000,
        summarize=summarise,
    )

    assert outcome.compacted is True
    assert (await layers.latest_summary("session:a"))["summary"] == "这段在讨论部署。"
    assert [n["content"] for n in await layers.self_notes()] == ["少用术语"]


async def test_a_failed_summary_changes_nothing(layers: MemoryLayers) -> None:
    async def boom() -> tuple[str, str | None]:
        raise RuntimeError("provider down")

    outcome = await compact_if_idle(
        layers,
        "session:a",
        now=10_000,
        last_activity=0,
        idle_minutes=30,
        tokens=99_999,
        token_threshold=6000,
        summarize=boom,
    )

    assert outcome.reason == "summarise_failed"
    assert await layers.latest_summary("session:a") is None
    assert await layers.self_notes() == []


async def test_an_empty_summary_is_not_stored(layers: MemoryLayers) -> None:
    async def blank() -> tuple[str, str | None]:
        return "   ", None

    outcome = await compact_if_idle(
        layers,
        "session:a",
        now=10_000,
        last_activity=0,
        idle_minutes=30,
        tokens=99_999,
        token_threshold=6000,
        summarize=blank,
    )

    assert outcome.reason == "empty_summary"
    assert await layers.latest_summary("session:a") is None
