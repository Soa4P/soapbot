"""Counters must not fan out, and file work must not block the loop.

Both defects were structural rather than visible: `memory_stats` returned the right
numbers while issuing one query per layer, and the skill endpoints returned the right
files while holding the event loop for the whole directory walk. Neither shows up in a
response assertion, so these tests assert on *how many* reads happen and *which thread*
does the file work.

The static half is deliberate. A future edit that reinstates the loop would still pass
every behavioural test — the numbers would be correct — so the shape has to be pinned
separately.
"""

from __future__ import annotations

import pathlib

import pytest

from soapbot.memory.db import Database, reset_database
from soapbot.memory.store import MemoryLayer, MemoryStore

ROOT = pathlib.Path(__file__).resolve().parents[1]
ADMIN = ROOT / "src" / "soapbot" / "api" / "admin.py"


@pytest.fixture
async def store(tmp_path):
    await reset_database()
    database = Database(f"sqlite+aiosqlite:///{(tmp_path / 'counts.db').as_posix()}")
    await database.init()
    try:
        yield MemoryStore(database)
    finally:
        await database.close()
        await reset_database()


async def test_count_by_layer_answers_every_layer_in_one_read(store: MemoryStore) -> None:
    await store.add_memory(
        content="a", layer=MemoryLayer.EPISODIC, scope="s", embed=False
    )
    await store.add_memory(
        content="b", layer=MemoryLayer.EPISODIC, scope="s", embed=False
    )
    await store.add_memory(
        content="c", layer=MemoryLayer.SEMANTIC, scope="s", embed=False
    )

    counts = await store.count_by_layer()

    assert counts == {"episodic": 2, "semantic": 1}


async def test_an_empty_store_reports_no_layers(store: MemoryStore) -> None:
    """A missing key, not a zero: the API layer decides how to render an absent layer."""
    assert await store.count_by_layer() == {}


def test_memory_stats_does_not_query_once_per_layer() -> None:
    source = ADMIN.read_text(encoding="utf-8")
    handler = source.split("async def memory_stats", 1)[1].split("@router.", 1)[0]

    assert "count_by_layer()" in handler
    assert "count_memories(" not in handler, (
        "memory_stats is looping per layer again; one GROUP BY answers the same question"
    )


def test_skill_endpoints_keep_file_work_off_the_event_loop() -> None:
    source = ADMIN.read_text(encoding="utf-8")

    assert "await asyncio.to_thread(forge.load, scope)" in source
    assert "await asyncio.to_thread(forge.save, skill)" in source
    # The synchronous forms must not come back alongside them.
    assert "= forge.load(scope)" not in source
    assert "= forge.save(skill)" not in source
