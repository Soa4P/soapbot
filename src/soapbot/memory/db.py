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

import logging
from collections.abc import AsyncIterator
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

SCHEMA_VERSION = 1


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
    trace_id: Mapped[str] = mapped_column(String(32), default="")
    created_at: Mapped[float] = mapped_column(Float, default=0.0, index=True)

    __table_args__ = (Index("ix_messages_session_time", "session_key", "created_at"),)


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
            url, echo=False, future=True, poolclass=NullPool
        )
        self._session_factory = async_sessionmaker(self.engine, expire_on_commit=False)

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
        await self._record_version()
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

    async def _record_version(self) -> None:
        import time

        async with self._session_factory() as session:
            existing = await session.get(SchemaVersion, 1)
            if existing is None:
                session.add(
                    SchemaVersion(id=1, version=SCHEMA_VERSION, applied_at=time.time())
                )
                await session.commit()

    async def session(self) -> AsyncIterator[AsyncSession]:
        async with self._session_factory() as session:
            yield session

    def session_factory(self) -> async_sessionmaker[AsyncSession]:
        return self._session_factory

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
