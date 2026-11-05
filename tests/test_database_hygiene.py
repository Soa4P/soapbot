"""Database/ORM hygiene: what was actually broken, and what was not.

Twelve issues were reported against this layer. Several are real and are fixed here;
several do not hold against this codebase and are pinned as assertions so the same
review cannot keep landing. This project has repeatedly been bitten by protections
that existed but were not on the execution path, so each test targets behaviour.
"""

from __future__ import annotations

import asyncio
from pathlib import Path

import pytest
from sqlalchemy import event, inspect, select, text
from sqlalchemy.orm import configure_mappers
from sqlalchemy.pool import NullPool

from soapbot.budget.policy import BudgetPolicy
from soapbot.budget.store import BudgetStore
from soapbot.memory import migrations
from soapbot.memory.db import (
    SCHEMA_VERSION,
    Base,
    Database,
    MemoryRow,
    MessageRow,
    SpendRequestRow,
)
from soapbot.memory.store import KnowledgeBase, MemoryStore, _fts_index_many


@pytest.fixture
async def db(tmp_path):
    instance = Database(f"sqlite+aiosqlite:///{tmp_path / 'hygiene.db'}")
    await instance.init()
    yield instance
    await instance.close()


def _sessions(db):
    """The factory returns a sessionmaker, so it needs a second call."""
    return db.session_factory()()


# ----------------------------------------------------------------- real: the UoW


@pytest.mark.asyncio
async def test_write_commits_even_without_an_explicit_commit(db) -> None:
    """The regression the UoW fixes.

    ``write()`` used to yield a session and nothing else. A new store method that
    forgot ``await session.commit()`` lost its write silently: ``AsyncSession.__aexit__``
    closes the session and rolls back, with no exception and no log line. The
    transaction boundary now belongs to the context manager, not to each caller.
    """
    async with db.write() as session:
        session.add(
            MessageRow(session_key="s1", message_id="m1", content="hello", created_at=1.0)
        )

    async with _sessions(db) as check:
        rows = (await check.execute(select(MessageRow))).scalars().all()
    assert [row.content for row in rows] == ["hello"]


@pytest.mark.asyncio
async def test_write_rolls_back_on_exception(db) -> None:
    """A failure after the insert must not leave a half-written row behind."""
    with pytest.raises(RuntimeError, match="boom"):
        async with db.write() as session:
            session.add(
                MessageRow(session_key="s1", message_id="m1", content="hello", created_at=1.0)
            )
            raise RuntimeError("boom")

    async with _sessions(db) as check:
        rows = (await check.execute(select(MessageRow))).scalars().all()
    assert rows == []


@pytest.mark.asyncio
async def test_write_rolls_back_on_cancellation(db) -> None:
    """CancelledError is a BaseException: an ``except Exception`` would miss it.

    A cancelled archive must not leave an open transaction for the next writer to
    inherit on the same connection.
    """
    with pytest.raises(asyncio.CancelledError):
        async with db.write() as session:
            session.add(
                MessageRow(session_key="s1", message_id="m1", content="hello", created_at=1.0)
            )
            raise asyncio.CancelledError

    async with _sessions(db) as check:
        rows = (await check.execute(select(MessageRow))).scalars().all()
    assert rows == []


@pytest.mark.asyncio
async def test_each_write_gets_its_own_session(db) -> None:
    """Session objects are never shared across tasks or requests.

    The Database singleton holds an *engine*, a session *factory* and a lock; it does
    not hold a Session. Asserting distinct objects makes any future "reuse one session"
    optimisation fail here instead of surfacing as a race in production.
    """
    seen: list[int] = []
    for _ in range(2):
        async with db.write() as session:
            seen.append(id(session))
    assert len(set(seen)) == 2


# ------------------------------------------ real: the write that skipped the lock


@pytest.mark.asyncio
async def test_snapshot_with_nothing_expired_issues_no_write(tmp_path) -> None:
    """``snapshot`` used to be the one write path bypassing ``Database.write``.

    Its expiry sweep is an UPDATE committed on a plain session, so a quota read could
    collide with a reserve. The fast path must be genuinely read-only.
    """
    db = Database(f"sqlite+aiosqlite:///{tmp_path / 'snap.db'}")
    await db.init()
    statements: list[str] = []

    @event.listens_for(db.engine.sync_engine, "before_cursor_execute")
    def _capture(_conn, _cursor, statement, _params, _context, _many):
        statements.append(statement.strip().upper())

    try:
        store = BudgetStore(db=db, policy=BudgetPolicy())
        await store.snapshot(session_key="s1")
        writes = [s for s in statements if s.startswith(("UPDATE", "INSERT", "DELETE"))]
        assert writes == [], f"a read-only snapshot must not write: {writes}"
    finally:
        await db.close()


@pytest.mark.asyncio
async def test_snapshot_sweep_goes_through_the_write_lock(tmp_path) -> None:
    """When a sweep is really needed, it must be serialised with other writers."""
    db = Database(f"sqlite+aiosqlite:///{tmp_path / 'snap2.db'}")
    await db.init()
    try:
        store = BudgetStore(db=db, policy=BudgetPolicy())
        async with db.write() as session:
            session.add(
                SpendRequestRow(
                    session_key="s1",
                    amount_minor=100,
                    currency="CNY",
                    purpose="test",
                    status="pending",
                    period="p1",
                    created_at=0.0,
                    expires_at=1.0,
                )
            )

        locked = 0
        original_write = db.write

        def counted_write():
            nonlocal locked
            locked += 1
            return original_write()

        db.write = counted_write  # type: ignore[method-assign]
        await store.snapshot(session_key="s1", period="p1", now=2.0)
        assert locked == 1, "expiry sweep must go through Database.write"
    finally:
        await db.close()


# ------------------------------------------------- real: schema version + index


@pytest.mark.asyncio
async def test_an_existing_v1_database_gets_the_new_index(tmp_path) -> None:
    """``create_all`` does not add indexes to tables that already exist.

    A declarative ``Index`` alone fixes fresh installs and silently leaves every
    existing database doing a full session scan. Version 2 must close that gap.
    """
    url = f"sqlite+aiosqlite:///{tmp_path / 'old.db'}"
    first = Database(url)
    await first.init()
    async with first.engine.begin() as conn:
        await conn.execute(text("DROP INDEX IF EXISTS ix_messages_session_message"))
        await migrations._set_version(conn, 1)
    await first.close()

    second = Database(url)
    await second.init()
    try:
        async with second.engine.begin() as conn:
            assert await migrations.current_version(conn) == SCHEMA_VERSION
            names = (
                await conn.execute(
                    text(
                        "SELECT name FROM sqlite_master WHERE type = 'index' "
                        "AND name = 'ix_messages_session_message'"
                    )
                )
            ).scalars().all()
        assert names == ["ix_messages_session_message"]
    finally:
        await second.close()


@pytest.mark.asyncio
async def test_message_lookup_is_indexed(db) -> None:
    """The index must be on the path the query takes, not merely declared."""
    async with db.engine.begin() as conn:
        plan = (
            await conn.execute(
                text(
                    "EXPLAIN QUERY PLAN SELECT id FROM messages "
                    "WHERE session_key = 's' AND message_id = 'm' ORDER BY id DESC LIMIT 1"
                )
            )
        ).all()
    detail = " ".join(str(row[-1]) for row in plan)
    assert "ix_messages_session_message" in detail, detail


# ------------------------------------------------------------- real: N+1 / loops


@pytest.mark.asyncio
async def test_touch_uses_one_statement_not_one_per_memory(db) -> None:
    """The old loop did a SELECT + UPDATE for every recalled id while holding the lock."""
    store = MemoryStore(db)
    async with db.write() as session:
        for i in range(5):
            session.add(
                MemoryRow(
                    layer="semantic",
                    content=f"m{i}",
                    scope="s1",
                    created_at=float(i),
                    access_count=0,
                )
            )
    async with _sessions(db) as session:
        ids = (await session.execute(select(MemoryRow.id))).scalars().all()

    statements: list[str] = []

    @event.listens_for(db.engine.sync_engine, "before_cursor_execute")
    def _capture(_conn, _cursor, statement, _params, _context, _many):
        statements.append(statement.strip().upper())

    await store._touch(list(ids))

    assert len(statements) == 1, f"expected a single UPDATE, got {statements}"
    assert statements[0].startswith("UPDATE")

    async with _sessions(db) as session:
        counts = (await session.execute(select(MemoryRow.access_count))).scalars().all()
    assert counts == [1] * 5


@pytest.mark.asyncio
async def test_add_document_does_not_flush_once_per_chunk(db) -> None:
    """A long document must not hold the write lock for N round trips."""
    kb = KnowledgeBase(db)
    chunks = [f"chunk {i} content" for i in range(12)]
    kb.chunk = lambda _content: chunks  # type: ignore[method-assign]

    statements: list[str] = []

    @event.listens_for(db.engine.sync_engine, "before_cursor_execute")
    def _capture(_conn, _cursor, statement, _params, _context, _many):
        statements.append(statement.strip().upper())

    assert await kb.add_document("doc1", "Doc", "ignored") == 12

    # SQLAlchemy still needs one INSERT per row to collect autoincrement ids — that is
    # unavoidable. What changed is the *awaited* work: one FTS executemany instead of
    # 12 separate INSERTs, and one SAVEPOINT instead of 12 nested transactions. That
    # is what used to hold the write lock for the whole document.
    fts_inserts = [s for s in statements if s.startswith("INSERT INTO KNOWLEDGE_FTS")]
    savepoints = [s for s in statements if s.startswith("SAVEPOINT")]
    assert len(fts_inserts) == 1, f"expected one FTS batch, got {len(fts_inserts)}"
    assert len(savepoints) == 1, f"expected one SAVEPOINT, got {len(savepoints)}"


@pytest.mark.asyncio
async def test_delete_document_does_not_delete_fts_rows_one_by_one(db) -> None:
    kb = KnowledgeBase(db)
    chunks = ["alpha", "beta", "gamma", "delta"]
    kb.chunk = lambda _content: chunks  # type: ignore[method-assign]
    await kb.add_document("doc1", "Doc", "ignored")

    deletes: list[str] = []

    @event.listens_for(db.engine.sync_engine, "before_cursor_execute")
    def _capture(_conn, _cursor, statement, _params, _context, _many):
        if "DELETE FROM knowledge_fts" in statement:
            deletes.append(statement)

    assert await kb.delete_document("doc1") == 4
    assert len(deletes) == 1, f"expected one FTS delete, got {len(deletes)}"


# ------------------------------------------------ claims that do not hold, pinned


def test_pool_is_nullpool_on_purpose() -> None:
    """Claim: "connection pool is unconfigured".

    It is configured to NullPool deliberately: with QueuePool, SQLAlchemy may hand the
    same aiosqlite connection to two concurrent sessions and aiosqlite's single
    background thread raises "close() can't be called here". pool_size/max_overflow are
    meaningless (and rejected) under NullPool. Pinning it stops a well-meaning
    "optimisation" from reintroducing that crash.
    """
    db = Database("sqlite+aiosqlite:///C:/tmp/soapbot-hygiene-pool.db")
    assert isinstance(db.engine.pool, NullPool)


def test_models_have_no_relationships() -> None:
    """Claim: "async code accesses unloaded relationships".

    There are no relationship attributes anywhere — every model is a flat single
    table. Asserting it means a future relationship must be added with an explicit
    loading strategy rather than slipping in and raising MissingGreenlet at runtime.
    """
    configure_mappers()
    for mapper in Base.registry.mappers:
        assert list(inspect(mapper.class_).relationships) == [], mapper.class_.__name__


@pytest.mark.asyncio
async def test_native_sql_never_interpolates_user_input(db) -> None:
    """Claim: "``text()`` builds SQL from user input".

    Only identifier-shaped *constants* are interpolated (FTS table names). They are
    allow-listed and the helper refuses anything else; all values are bound.
    """
    with pytest.raises(ValueError, match="unknown FTS table"):
        await _fts_index_many(None, "messages; DROP TABLE users--", [("x", 1)])

    store = MemoryStore(db)
    malicious = "x' OR 1=1; DROP TABLE messages;--"
    seen: list[str] = []

    @event.listens_for(db.engine.sync_engine, "before_cursor_execute")
    def _capture(_conn, _cursor, statement, _params, _context, _many):
        seen.append(statement)

    await store.recall(malicious, scope="s1")
    assert not any("DROP TABLE" in s for s in seen)


def test_api_never_returns_orm_rows_and_has_no_response_model() -> None:
    """Claim: "ORM objects are returned directly as ``response_model``".

    No route declares ``response_model`` and no API module imports a Row class; stores
    convert to dict/dataclass at the boundary. Asserted over source so a future route
    that starts leaking a live AsyncSession-bound object fails here.
    """
    api_dir = Path(__file__).resolve().parents[1] / "src" / "soapbot" / "api"
    joined = "\n".join(p.read_text(encoding="utf-8") for p in api_dir.glob("*.py"))
    assert "response_model" not in joined
    for row in ("MessageRow", "MemoryRow", "KnowledgeRow", "SpendRequestRow"):
        assert row not in joined


def test_migration_chain_has_a_real_step() -> None:
    """An empty MIGRATIONS table would make the mechanism untested and old DBs static."""
    assert SCHEMA_VERSION >= 2
    assert 2 in migrations.MIGRATIONS
    assert callable(migrations.MIGRATIONS[2])
