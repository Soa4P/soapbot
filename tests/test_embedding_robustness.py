"""Embedding vectors are external input, and NaN is the failure that hides.

``nan`` propagates through ``norm`` and ``dot``, and every comparison against it is false.
So ``cosine <= 0`` never fires, NaN sorts unpredictably, and the recall result becomes
arbitrary rather than empty — the worst of the three, because nothing looks broken. A
provider that returns a broken row, or a stored vector written by an older bug, is enough
to trigger it.

The other half is cost: every recalled item is re-sent on every later turn, and every
embedded character is billed. Both are bounded here rather than at the call sites.
"""

from __future__ import annotations

import pytest

from soapbot.memory.db import Database, reset_database
from soapbot.memory.store import MemoryLayer, MemoryStore


class _ScriptedEmbedder:
    """Returns the vectors it is told to, so a bad one can be injected deliberately."""

    def __init__(self, vectors: list[list[float]]) -> None:
        self.vectors = vectors
        self.seen: list[list[str]] = []

    async def embed(self, texts: list[str]) -> list[list[float]]:
        self.seen.append(list(texts))
        return self.vectors


@pytest.fixture
async def db(tmp_path):
    await reset_database()
    database = Database(f"sqlite+aiosqlite:///{(tmp_path / 'vec.db').as_posix()}")
    await database.init()
    yield database
    await database.close()
    await reset_database()


@pytest.mark.asyncio
async def test_a_non_finite_query_vector_yields_no_vector_hits(db: Database) -> None:
    """A broken query must degrade to keyword search, not poison the ranking.

    The candidate row carries a *real* embedding on purpose. With no vectorised row the
    search returns nothing whatever the query contains, so the assertion would hold even
    with every guard deleted — the test would be decorative, which is exactly the failure
    mode this suite keeps finding elsewhere.
    """
    store = MemoryStore(db, embedder=_ScriptedEmbedder([[1.0, 0.0, 0.0]]))
    await store.add_memory(
        content="小明喜欢猫", layer=MemoryLayer.SEMANTIC, scope="s1", embed=True
    )

    # Same store, now answering the query with NaN.
    store._embedder = _ScriptedEmbedder([[float("nan"), 0.5, 0.5]])

    result = await store.recall("小明喜欢什么", scope="s1", limit=5)

    assert result.vector_hits == 0, "NaN produced comparison results"


@pytest.mark.asyncio
async def test_infinite_values_are_rejected_too(db: Database) -> None:
    store = MemoryStore(db, embedder=_ScriptedEmbedder([[float("inf"), 0.0, 0.0]]))
    result = await store.recall("任何问题", scope="s1", limit=5)
    assert result.vector_hits == 0


@pytest.mark.asyncio
async def test_a_stored_row_with_a_broken_vector_is_skipped_not_ranked(
    db: Database,
) -> None:
    """The row side is the more likely source: it was written once and stays."""
    store = MemoryStore(db, embedder=None)
    await store.add_memory(
        content="损坏的向量", layer=MemoryLayer.SEMANTIC, scope="s1", embed=True
    )

    # Now give the store a query embedder and break the stored row on purpose.
    store._embedder = _ScriptedEmbedder([[1.0, 0.0, 0.0]])
    async with db.write() as session:
        from soapbot.memory.db import MemoryRow

        rows = (await session.execute(__import__("sqlalchemy").select(MemoryRow))).scalars().all()
        assert rows, "the fixture stored nothing"
        rows[0].embedding = __import__("numpy").asarray(
            [float("nan")] * 3, dtype="float32"
        ).tobytes()
        rows[0].embedding_dim = 3
        await session.commit()

    result = await store.recall("随便问问", scope="s1", limit=5)
    assert result.vector_hits == 0, "a NaN row was ranked"


@pytest.mark.asyncio
async def test_a_healthy_vector_still_matches(db: Database) -> None:
    """The paired case: the guards must not disable retrieval altogether."""
    store = MemoryStore(db, embedder=None)
    await store.add_memory(
        content="今天下雨了", layer=MemoryLayer.SEMANTIC, scope="s1", embed=False
    )
    store._embedder = _ScriptedEmbedder([[1.0, 0.0, 0.0, 0.0]])

    async with db.write() as session:
        from soapbot.memory.db import MemoryRow

        rows = (await session.execute(__import__("sqlalchemy").select(MemoryRow))).scalars().all()
        rows[0].embedding = __import__("numpy").asarray(
            [1.0, 0.0, 0.0, 0.0], dtype="float32"
        ).tobytes()
        rows[0].embedding_dim = 4
        await session.commit()

    result = await store.recall("下雨", scope="s1", limit=5)
    assert result.vector_hits == 1


# --------------------------------------------------------------------- bounds
@pytest.mark.asyncio
async def test_recall_is_clamped_to_the_configured_ceiling(
    db: Database, monkeypatch: pytest.MonkeyPatch
) -> None:
    """A caller asking for thousands must not get thousands into the prompt."""
    from soapbot.config import settings

    monkeypatch.setattr(settings, "max_recall_items", 3)

    store = MemoryStore(db, embedder=None)
    for index in range(10):
        await store.add_memory(
            content=f"第{index}条记忆内容",
            layer=MemoryLayer.SEMANTIC,
            scope="s1",
            embed=False,
        )

    result = await store.recall("记忆", scope="s1", limit=10_000)
    assert len(result.items) <= 3, f"clamp ignored: {len(result.items)} items"


@pytest.mark.asyncio
async def test_embedding_input_is_truncated(db: Database, monkeypatch: pytest.MonkeyPatch) -> None:
    """Billing and provider limits are both decided by what we send, not by the model."""
    from soapbot.config import settings

    monkeypatch.setattr(settings, "max_embedding_chars", 100)

    embedder = _ScriptedEmbedder([[0.1] * 4])
    store = MemoryStore(db, embedder=embedder)
    await store.add_memory(content="长" * 5000, layer=MemoryLayer.SEMANTIC, scope="s1")

    sent = embedder.seen[0][0]
    assert len(sent) <= 100, f"sent {len(sent)} chars to the provider"


@pytest.mark.asyncio
async def test_the_query_is_truncated_the_same_way(db: Database, monkeypatch) -> None:
    """Mismatched truncation would compare a short vector against a long text."""
    from soapbot.config import settings

    monkeypatch.setattr(settings, "max_embedding_chars", 50)

    embedder = _ScriptedEmbedder([[0.1] * 4])
    store = MemoryStore(db, embedder=embedder)
    await store.recall("问" * 1000, scope="s1", limit=3)

    sent = embedder.seen[0][0]
    assert len(sent) <= 50
