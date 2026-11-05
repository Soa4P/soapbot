"""Database layer: async SQLAlchemy + SQLite (FTS5 + vector BLOBs).

Design decisions worth stating:

* **SQLite, not Postgres.** Single-process bot; a file DB means zero ops. FTS5
  ships compiled into the standard Python SQLite build, so BM25 search needs no
  extra service.
* **Vectors as BLOB + numpy cosine.** For a single group bot the corpus is
  thousands of rows, not millions. Brute-force cosine in numpy is faster than
  the overhead of any vector DB, and it removes a dependency.
* **Append-only message archive.** Conversation history is never mutated; the
  compressed view is derived. That is what makes "回溯" (recall) actually work:
  the original turns are still there even after compression folded them.
* **Version table instead of Alembic.** The migration surface is small and this
  keeps startup deterministic without a CLI step.
"""

from __future__ import annotations

import asyncio
import logging
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager, suppress
from datetime import UTC, datetime
from typing import Any

from sqlalchemy import (
    BLOB,
    Float,
    Index,
    Integer,
    String,
    Text,
    text,
)
from sqlalchemy.ext.asyncio import (
    AsyncEngine,
    AsyncSession,
    async_sessionmaker,
    create_async_engine,
)
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column
from sqlalchemy.pool import NullPool

logger = logging.getLogger(__name__)

SCHEMA_VERSION = 3

#: How long SQLite waits for a competing writer before giving up, in seconds.
#:
#: Five seconds is generous for a bot whose writes are single-row inserts, and it is
#: the difference between "the second writer retries and succeeds" and "the second
#: writer raises immediately". Applied per connection — see ``Database.__init__``.
_BUSY_TIMEOUT_S = 5.0


class Base(DeclarativeBase):
    pass


def _utcnow() -> datetime:
    return datetime.now(UTC)


class MessageRow(Base):
    """Raw inbound/outbound archive. Append-only."""

    __tablename__ = "messages"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    session_key: Mapped[str] = mapped_column(String(128), index=True)
    adapter: Mapped[str] = mapped_column(String(32), default="")
    scene: Mapped[str] = mapped_column(String(16), default="group")
    group_id: Mapped[str] = mapped_column(String(64), default="")
    user_id: Mapped[str] = mapped_column(String(64), default="")
    user_name: Mapped[str] = mapped_column(String(128), default="")
    role: Mapped[str] = mapped_column(String(16), default="user")
    content: Mapped[str] = mapped_column(Text, default="")
    image_desc: Mapped[str] = mapped_column(Text, default="")
    message_id: Mapped[str] = mapped_column(String(64), default="")
    # Deliberately not indexed: no DB query filters on it (traces live in an in-memory
    # ring, ``core/trace.py``). An index here would cost a write on every archived
    # message and never be read.
    trace_id: Mapped[str] = mapped_column(String(32), default="")
    created_at: Mapped[float] = mapped_column(Float, default=0.0, index=True)

    __table_args__ = (
        Index("ix_messages_session_time", "session_key", "created_at"),
        # ``MemoryStore.find_message`` filters on exactly this pair and orders by id;
        # without it the lookup used ``ix_messages_session_key`` and then scanned every
        # message in that session to match message_id. Added in schema version 2, so
        # ``migrations`` must create it for databases that already exist.
        Index("ix_messages_session_message", "session_key", "message_id"),
    )


class MemoryRow(Base):
    """Long-term memory units.

    ``layer`` distinguishes the three stores:
      * ``episodic`` — "on 2026-10-20 in group X, Y said Z"
      * ``semantic`` — distilled facts/preferences ("小明喜欢猫")
      * ``working``  — short-lived scratch state (also mirrored in SessionStore)
    """

    __tablename__ = "memories"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    layer: Mapped[str] = mapped_column(String(16), default="semantic", index=True)
    scope: Mapped[str] = mapped_column(String(128), default="", index=True)
    """Session key or group id the memory belongs to; '' = global."""
    subject: Mapped[str] = mapped_column(String(128), default="")
    """Who/what the memory is about (user id, topic)."""
    content: Mapped[str] = mapped_column(Text, default="")
    keywords: Mapped[str] = mapped_column(Text, default="")
    importance: Mapped[float] = mapped_column(Float, default=0.5, index=True)
    embedding: Mapped[bytes | None] = mapped_column(BLOB, nullable=True)
    embedding_dim: Mapped[int] = mapped_column(Integer, default=0)
    source_message_id: Mapped[str] = mapped_column(String(64), default="")
    created_at: Mapped[float] = mapped_column(Float, default=0.0, index=True)
    accessed_at: Mapped[float] = mapped_column(Float, default=0.0)
    access_count: Mapped[int] = mapped_column(Integer, default=0)


class SceneCardRow(Base):
    """The per-scene index card: a bounded, always-injectable map of a conversation.

    One row per scope, replaced rather than appended. A card is a *view* of the memories
    in its scope, so keeping history would mean keeping stale maps and having to decide
    which one is current — a decision with no right answer and a wrong one that is easy
    to make.
    """

    __tablename__ = "scene_cards"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    scope: Mapped[str] = mapped_column(String(128), unique=True, index=True)
    title: Mapped[str] = mapped_column(String(256), default="")
    summary: Mapped[str] = mapped_column(Text, default="")
    topics: Mapped[str] = mapped_column(Text, default="")
    """Newline-joined. A separate table would be normalised and pointless: the list is
    read whole, written whole, and never queried by element."""
    people: Mapped[str] = mapped_column(Text, default="")
    memory_count: Mapped[int] = mapped_column(Integer, default=0)
    updated_at: Mapped[float] = mapped_column(Float, default=0.0, index=True)


class ScenePortraitRow(Base):
    """The per-scene portrait: slow-changing, evidence-derived understanding.

    Separate from :class:`SceneCardRow` because the lifetimes differ. The card changes
    every turn and is always injected; the portrait changes rarely, costs more to build,
    and is injected only when relevant.
    """

    __tablename__ = "scene_portraits"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    scope: Mapped[str] = mapped_column(String(128), unique=True, index=True)
    headline: Mapped[str] = mapped_column(Text, default="")
    themes: Mapped[str] = mapped_column(Text, default="")
    tone: Mapped[str] = mapped_column(String(64), default="")
    recurring_questions: Mapped[str] = mapped_column(Text, default="")
    memory_count: Mapped[int] = mapped_column(Integer, default=0)
    confidence: Mapped[float] = mapped_column(Float, default=0.0)
    """0..1, from how much evidence the portrait rests on. Stored rather than recomputed
    so a reader can decide whether to trust the portrait without re-reading its inputs."""
    updated_at: Mapped[float] = mapped_column(Float, default=0.0, index=True)


class SceneLinkRow(Base):
    """A typed, directed edge between two memories — the ``[[wikilink]]``.

    ``kind`` is a string column holding a value from a closed set
    (:data:`soapbot.memory.scene.LINK_KINDS`). Not an enum column because SQLite has no
    native enum and a CHECK constraint would need a migration to extend; the validation
    lives where the vocabulary is defined.
    """

    __tablename__ = "scene_links"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    source_id: Mapped[int] = mapped_column(Integer, index=True)
    target_id: Mapped[int] = mapped_column(Integer, index=True)
    kind: Mapped[str] = mapped_column(String(32), default="same_topic", index=True)
    weight: Mapped[float] = mapped_column(Float, default=1.0)
    created_at: Mapped[float] = mapped_column(Float, default=0.0)

    __table_args__ = (
        # The pair plus kind is the identity of an edge. Without the constraint, repeated
        # extraction of the same fact would add a new row each time and ``neighbours``
        # would return the same id many times over.
        Index("uq_scene_link", "source_id", "target_id", "kind", unique=True),
    )


class KnowledgeRow(Base):
    """RAG document chunks."""

    __tablename__ = "knowledge"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    doc_id: Mapped[str] = mapped_column(String(64), index=True)
    title: Mapped[str] = mapped_column(String(256), default="")
    chunk_index: Mapped[int] = mapped_column(Integer, default=0)
    content: Mapped[str] = mapped_column(Text, default="")
    embedding: Mapped[bytes | None] = mapped_column(BLOB, nullable=True)
    embedding_dim: Mapped[int] = mapped_column(Integer, default=0)
    created_at: Mapped[float] = mapped_column(Float, default=0.0)


class SummaryRow(Base):
    """Rolling conversation summaries, so compression survives restarts."""

    __tablename__ = "summaries"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    session_key: Mapped[str] = mapped_column(String(128), index=True)
    summary: Mapped[str] = mapped_column(Text, default="")
    folded_message_count: Mapped[int] = mapped_column(Integer, default=0)
    created_at: Mapped[float] = mapped_column(Float, default=0.0)


class SpendRequestRow(Base):
    """Spend authorisation requests (Wave 5).

    Note what is *absent*: no payee account, no card token, no payment
    credential, no "executed" flag. This table records that a human asked and
    another human agreed. Nothing here can move money, and no column was added
    "for later" — a dormant ``paid_at`` column is how a ledger gradually becomes
    a payment system without anyone deciding to build one.

    ``amount_minor`` is an integer count of minor units (fen/cents). Storing money
    as ``Float`` would let the sum of approved rows drift from the recorded total.
    """

    __tablename__ = "spend_requests"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    amount_minor: Mapped[int] = mapped_column(Integer, default=0)
    currency: Mapped[str] = mapped_column(String(8), default="CNY")
    purpose: Mapped[str] = mapped_column(Text, default="")
    session_key: Mapped[str] = mapped_column(String(128), index=True)
    """Scope the request belongs to; requests are never readable across scopes."""
    requester_id: Mapped[str] = mapped_column(String(64), default="")
    requester_name: Mapped[str] = mapped_column(String(128), default="")
    status: Mapped[str] = mapped_column(String(16), default="pending", index=True)
    period: Mapped[str] = mapped_column(String(16), default="", index=True)
    created_at: Mapped[float] = mapped_column(Float, default=0.0, index=True)
    expires_at: Mapped[float] = mapped_column(Float, default=0.0, index=True)
    decided_at: Mapped[float] = mapped_column(Float, default=0.0)
    decided_by: Mapped[str] = mapped_column(String(64), default="")
    decision_note: Mapped[str] = mapped_column(Text, default="")
    idempotency_key: Mapped[str | None] = mapped_column(String(64), nullable=True)
    trace_id: Mapped[str] = mapped_column(String(32), default="")

    __table_args__ = (
        Index("ix_spend_scope_period", "session_key", "period", "status"),
        Index("ix_spend_pending_expiry", "status", "expires_at"),
        # Replay protection at the storage layer, not just in Python. A retried
        # command (user double-taps, adapter resends, operator re-runs) must map to
        # the same request instead of creating a second reservation. SQLite treats
        # NULLs as distinct in a UNIQUE index, so requests without a key are
        # unaffected.
        Index("uq_spend_idempotency", "session_key", "idempotency_key", unique=True),
    )


class SchemaVersion(Base):
    __tablename__ = "schema_version"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    version: Mapped[int] = mapped_column(Integer, default=0)
    applied_at: Mapped[float] = mapped_column(Float, default=0.0)


class Database:
    def __init__(self, url: str) -> None:
        self.url = url
        # NullPool is mandatory here, not an optimisation. With the default
        # QueuePool, SQLAlchemy may hand the *same* aiosqlite connection to two
        # concurrent sessions; because aiosqlite multiplexes every statement
        # through one background thread, that surfaces as
        #   "Method 'close()' can't be called here; method '_prepare_impl()' is
        #    already in progress"
        # A fresh connection per checkout plus WAL (readers don't block the
        # writer) makes concurrent pipeline writes and WebUI reads safe.
        self.engine: AsyncEngine = create_async_engine(
            url,
            echo=False,
            future=True,
            poolclass=NullPool,
            # ``busy_timeout`` and ``journal_mode`` are *per connection* pragmas, and
            # ``init()`` only ever ran them on one connection. With NullPool every
            # checkout is a brand-new connection, so the timeout was back to SQLite's
            # default of zero and a second writer failed instantly with
            # "database is locked" — which is exactly what passive mode produced, since
            # it archives on the same path the answering write runs on. Setting them on
            # connect applies them to every connection, which is what the comment above
            # already claimed WAL was doing.
            connect_args={"timeout": _BUSY_TIMEOUT_S},
        )
        self._session_factory = async_sessionmaker(self.engine, expire_on_commit=False)
        self._write_lock = asyncio.Lock()
        """Serialises transactions that write. See :meth:`write`."""

        from sqlalchemy import event

        @event.listens_for(self.engine.sync_engine, "connect")
        def _per_connection_pragmas(dbapi_conn, _record) -> None:  # pragma: no cover
            cursor = dbapi_conn.cursor()
            try:
                cursor.execute(f"PRAGMA busy_timeout={int(_BUSY_TIMEOUT_S * 1000)}")
                cursor.execute("PRAGMA journal_mode=WAL")
                cursor.execute("PRAGMA synchronous=NORMAL")
                cursor.execute("PRAGMA foreign_keys=ON")
            finally:
                cursor.close()

    async def init(self) -> None:
        async with self.engine.begin() as conn:
            for pragma in (
                "PRAGMA journal_mode=WAL",
                "PRAGMA synchronous=NORMAL",
                "PRAGMA busy_timeout=5000",
                "PRAGMA foreign_keys=ON",
            ):
                try:
                    await conn.execute(text(pragma))
                except Exception as exc:
                    logger.debug("pragma skipped (%s): %s", pragma, exc)
            await conn.run_sync(Base.metadata.create_all)
            await self._create_fts(conn)
            # Migrations run inside the same transaction as create_all, so a database
            # that fails halfway through an upgrade is left at its previous version
            # rather than at a mixture of two schemas.
            from soapbot.memory.migrations import migrate

            await migrate(conn, target=SCHEMA_VERSION)
        logger.info("database ready: %s", self.url)

    async def _create_fts(self, conn) -> None:
        """FTS5 virtual tables for BM25 keyword search.

        Uses ``content=''`` (contentless) tables: we store the text in our own
        tables and only mirror it for indexing, so there is a single source of
        truth for the content and no duplication drift.
        """
        for name, table in (
            ("messages_fts", "messages"),
            ("memories_fts", "memories"),
            ("knowledge_fts", "knowledge"),
        ):
            try:
                await conn.execute(
                    text(
                        f"CREATE VIRTUAL TABLE IF NOT EXISTS {name} USING fts5("
                        "content, row_id UNINDEXED, tokenize='unicode61')"
                    )
                )
            except Exception as exc:
                # FTS5 should always be available in CPython's bundled SQLite,
                # but degrade to vector-only search rather than refusing to boot.
                logger.error("FTS5 unavailable for %s (%s); keyword search disabled", table, exc)

    async def schema_version(self) -> int:
        """The recorded schema version, for the settings page and health output.

        Read back from the table rather than reported from ``SCHEMA_VERSION``: the
        interesting number is what the *file* contains, not what this build wants.
        A mismatch is precisely the state an operator needs to see.
        """
        from soapbot.memory.migrations import current_version

        async with self.engine.begin() as conn:
            found = await current_version(conn)
        return int(found or 0)

    async def session(self) -> AsyncIterator[AsyncSession]:
        """A read-only session for callers that only query.

        Writes MUST go through :meth:`write`: this generator does not commit, so an
        insert made here is rolled back by ``AsyncSession.__aexit__`` with no error —
        exactly the silent-loss failure that ``write`` was changed to prevent. Kept as
        a dependency-shaped helper for embedders, not used by the stores.
        """
        async with self._session_factory() as session:
            yield session

    def session_factory(self) -> async_sessionmaker[AsyncSession]:
        return self._session_factory

    @asynccontextmanager
    async def write(self) -> AsyncIterator[AsyncSession]:
        """One unit of work: a serialised session that commits or rolls back itself.

        SQLite admits exactly one writer. ``busy_timeout`` makes the *loser* wait, but
        under aiosqlite that wait happens on the connection's background thread while
        the event loop keeps starting more writers — so a burst turns into a queue of
        threads all polling the same lock, and the ones that time out raise
        ``database is locked``. Measured: 150 concurrent archives produced 14–17
        failures even with ``busy_timeout=5000`` in force.

        One asyncio lock in front of the write path removes the contention instead of
        negotiating it. Readers are untouched and still run concurrently under WAL.

        The transaction boundary is here, not in each caller. Previously every store
        method had to remember ``await session.commit()``; forgetting it was silent —
        ``AsyncSession.__aexit__`` closes the session and rolls the transaction back,
        so the write simply vanished with no exception and no log line. Committing
        centrally makes "a write happened" a property of the context manager rather
        than of whichever method happened to be edited last. On any exception the
        same boundary rolls back explicitly instead of relying on ``close()`` to do
        it as a side effect.
        """
        async with self._write_lock, self._session_factory() as session:
            try:
                yield session
                await session.commit()
            except BaseException:
                # BaseException, not Exception: a cancelled archive must not leave a
                # half-written transaction behind for the next writer to inherit.
                # A rollback that itself fails (lost connection, cancellation already
                # delivered) must not replace the original error with a confusing one.
                with suppress(Exception):
                    await session.rollback()
                raise

    async def close(self) -> None:
        await self.engine.dispose()


_db: Database | None = None


async def get_database(url: str | None = None) -> Database:
    global _db
    if _db is None:
        from soapbot.config import settings

        _db = Database(url or settings.resolved_db_url)
        await _db.init()
    return _db


async def reset_database() -> None:
    """Test helper: drop the singleton so a fresh temp DB can be created."""
    global _db
    if _db is not None:
        await _db.close()
    _db = None


def vector_to_blob(vec: list[float]) -> bytes:
    import numpy as np

    return np.asarray(vec, dtype=np.float32).tobytes()


def blob_to_vector(blob: bytes | None, dim: int = 0) -> list[float]:
    if not blob:
        return []
    import numpy as np

    return np.frombuffer(blob, dtype=np.float32).tolist()


def row_to_dict(row: Any) -> dict[str, Any]:
    return {c.name: getattr(row, c.name) for c in row.__table__.columns}
