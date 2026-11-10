"""Batched cosine ranking must be both fast *and* indistinguishable from the old loop.

Why this exists
---------------
The optimisation is only safe if the ranking did not move. A stable sort, a
``cosine <= 0`` cutoff and a per-row finite check are easy to lose when a Python
loop becomes a matrix multiply, and each one changes which memories reach the
prompt: NaN used to make the whole ordering arbitrary, and a truncated blob used
to raise rather than be skipped.

The two call sites are pinned separately. ``tests/test_embedding_robustness.py``
covers MemoryStore end to end; the knowledge-base path had no finite guard at
all, so the shared scorer is what fixes it — a test that only asserted the
function's behaviour would not notice a caller quietly going back to its own
loop.
"""

from __future__ import annotations

import inspect
from collections.abc import AsyncIterator

import numpy as np
import pytest

from soapbot.memory.db import Database, MemoryRow, reset_database, vector_to_blob
from soapbot.memory.store import KnowledgeBase, MemoryStore
from soapbot.memory.vectors import VectorCandidate, rank_by_cosine

QUERY = [1.0, 0.0, 0.0]


def _candidate(
    row_id: int,
    vec: list[float] | None,
    *,
    dim: int | None = None,
    raw: bytes | None = None,
) -> VectorCandidate:
    if raw is not None:
        return VectorCandidate(row_id, raw, dim if dim is not None else 3)
    if vec is None:
        return VectorCandidate(row_id, None, dim or 0)
    return VectorCandidate(
        row_id, vector_to_blob(vec), dim if dim is not None else len(vec)
    )


def _naive(candidates: list[VectorCandidate], query: list[float], limit: int):
    """The pre-optimisation loop, kept as an oracle rather than a description."""
    q = np.asarray(query, dtype=np.float32)
    qn = np.linalg.norm(q)
    scored: list[tuple[float, int]] = []
    for candidate in candidates:
        if (
            not candidate.blob
            or candidate.dim != len(query)
            or len(candidate.blob) != candidate.dim * 4
        ):
            continue
        v = np.frombuffer(candidate.blob, dtype=np.float32)
        if not np.all(np.isfinite(v)):
            continue
        vn = np.linalg.norm(v)
        if vn == 0 or not np.isfinite(vn):
            continue
        cosine = float(np.dot(q, v) / (qn * vn))
        if not np.isfinite(cosine) or cosine <= 0:
            continue
        scored.append((cosine, candidate.id))
    scored.sort(key=lambda pair: pair[0], reverse=True)
    return scored[:limit]


def test_batched_ranking_matches_the_old_loop() -> None:
    candidates = [
        _candidate(1, [1.0, 0.0, 0.0]),
        _candidate(2, [1.0, 1.0, 0.0]),
        _candidate(3, [1.0, 0.5, 0.0]),
        _candidate(4, [0.0, 1.0, 0.0]),
        _candidate(5, [-1.0, 0.0, 0.0]),
        _candidate(6, [0.2, 0.1, 0.0]),
    ]
    expected = _naive(candidates, QUERY, 4)

    ranking = rank_by_cosine(candidates, QUERY, limit=4)
    assert ranking.query_usable
    # Zero and negative cosines are excluded by both implementations, so the
    # rankings agree. They are *not* corrupt rows: only bad vectors count as
    # dropped, otherwise a normal corpus floods the log on every recall.
    assert ranking.dropped == 0
    assert ranking.non_positive == 2
    assert len(ranking.hits) == len(expected)
    for (actual_score, actual_id), (expected_score, expected_id) in zip(
        ranking.hits, expected, strict=True
    ):
        assert actual_id == expected_id
        assert actual_score == pytest.approx(expected_score, abs=1e-6)


def test_ties_keep_scan_order() -> None:
    candidates = [_candidate(i, [1.0, 0.0, 0.0]) for i in (7, 3, 9, 1)]

    ranking = rank_by_cosine(candidates, QUERY, limit=4)
    assert [row_id for _, row_id in ranking.hits] == [7, 3, 9, 1]


@pytest.mark.parametrize(
    "query",
    [
        [float("nan"), 0.5, 0.5],
        [float("inf"), 0.0, 0.0],
        [0.0, 0.0, 0.0],
        [],
    ],
)
def test_a_broken_query_is_reported_instead_of_ranking(query: list[float]) -> None:
    ranking = rank_by_cosine([_candidate(1, QUERY)], query, limit=3)
    assert ranking.query_usable is False
    assert ranking.hits == []


def test_broken_rows_are_dropped_and_counted() -> None:
    candidates = [
        _candidate(1, [1.0, 0.0, 0.0]),          # good
        _candidate(2, [1.0, 0.0]),               # wrong dim
        _candidate(3, None),                      # no blob
        _candidate(4, [1.0, 0.0, 0.0], raw=b"\x00\x00"),  # truncated blob
        _candidate(5, [float("nan"), 1.0, 0.0]),  # non-finite row
        _candidate(6, [0.0, 0.0, 0.0]),          # zero norm
        _candidate(7, [-1.0, 0.0, 0.0]),         # negative cosine
        _candidate(8, [1.0, 0.5, 0.0]),          # good
    ]

    ranking = rank_by_cosine(candidates, QUERY, limit=8)
    assert ranking.query_usable
    assert [row_id for _, row_id in ranking.hits] == [1, 8]
    # Five unusable rows; the negative cosine is merely irrelevant, not broken.
    assert ranking.dropped == 5
    assert ranking.non_positive == 1


def test_limit_is_honoured_and_a_negative_one_is_safe() -> None:
    candidates = [_candidate(i, [1.0, i / 10, 0.0]) for i in range(1, 6)]

    assert len(rank_by_cosine(candidates, QUERY, limit=2).hits) == 2
    assert rank_by_cosine(candidates, QUERY, limit=-1).hits == []


def test_both_recall_channels_use_the_shared_scorer() -> None:
    """A fast function nobody calls is not an optimisation."""
    for fn in (MemoryStore._vector_search, KnowledgeBase.search):
        source = inspect.getsource(fn)
        assert "rank_by_cosine" in source, f"{fn.__qualname__} went back to its own loop"
        assert "np.dot" not in source
        assert "np.linalg.norm" not in source
    assert "top_ids" in inspect.getsource(MemoryStore._vector_search), (
        "phase two (fetching display columns only for the winners) disappeared"
    )


class _FixedEmbedder:
    def __init__(self, vector: list[float]) -> None:
        self.vector = vector

    async def embed(self, texts: list[str]) -> list[list[float]]:
        return [self.vector for _ in texts]


@pytest.fixture
async def db(tmp_path) -> AsyncIterator[Database]:
    await reset_database()
    database = Database(f"sqlite+aiosqlite:///{(tmp_path / 'rank.db').as_posix()}")
    await database.init()
    yield database
    await database.close()
    await reset_database()


@pytest.mark.asyncio
async def test_two_stage_lookup_returns_complete_rows_in_cosine_order(db: Database) -> None:
    """Phase one must not lose the fields phase two is supposed to fetch."""
    vectors = [
        [1.0, 0.0, 0.0],           # 1.000
        [1.0, 1.0, 0.0],           # 0.707
        [0.0, 1.0, 0.0],           # 0 -> dropped
        [-1.0, 0.0, 0.0],          # negative -> dropped
        [1.0, 0.5, 0.0],           # 0.894
        [float("nan"), 1.0, 0.0],  # broken -> dropped
    ]
    async with db.write() as session:
        session.add_all(
            [
                MemoryRow(
                    content=f"row-{i}",
                    layer="semantic",
                    scope="s1",
                    subject=f"subject-{i}",
                    importance=0.5,
                    embedding=vector_to_blob(vec),
                    embedding_dim=len(vec),
                    created_at=float(i),
                )
                for i, vec in enumerate(vectors)
            ]
        )

    store = MemoryStore(db, embedder=_FixedEmbedder(QUERY))
    items = await store._vector_search("q", scope="s1", limit=3, layers=None)

    assert [item.content for item in items] == ["row-0", "row-4", "row-1"]
    assert all(item.layer == "semantic" and item.scope == "s1" for item in items)
    assert all(item.subject.startswith("subject-") for item in items)
    assert all(item.importance == 0.5 for item in items)
