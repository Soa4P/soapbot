"""Ordered schema migrations on top of SQLAlchemy's ``create_all``.

Why this exists at all
----------------------
``create_all`` is idempotent for *creating* missing tables, which is why the first
version of this project could claim "startup is deterministic without a CLI step".
That claim stops being true the moment a column has to be added or an index changed:
``create_all`` will happily skip an existing table, so an upgraded binary would run
against the old columns and fail at the first query that names the new one. The
failure would appear in production, on a database that contains real conversation
history, with no recorded version to reason from.

So: ``create_all`` keeps doing what it is good at (a fresh database is created at the
current schema in one step), and this module carries every *change* to an existing
database, in order, with the applied version recorded.

The three rules this module enforces
------------------------------------
1. **Forward only, one step at a time.** A database at version 1 migrates via the
   ``1 -> 2`` step. There is no "jump to latest" path that could skip a data fix.
2. **A newer database is a hard stop.** If the file says version 5 and this build only
   knows 3, startup fails with a message naming both numbers. Continuing would mean
   writing an old schema's assumptions into newer rows — silent corruption, discovered
   later, unrecoverable without a backup.
3. **Each step is atomic and recorded in the same transaction as its changes.** A
   migration that half-applies and then crashes leaves the version untouched, so the
   next start retries the whole step instead of skipping it.
"""

from __future__ import annotations

import logging
import time
from collections.abc import Awaitable, Callable
from typing import Any

from sqlalchemy import text

logger = logging.getLogger(__name__)

#: A single migration step. Receives the open connection; must be idempotent in the
#: sense that re-running it after a crash mid-transaction is safe (the transaction
#: rolls back, so it re-runs from the version's starting state).
MigrationStep = Callable[[Any], Awaitable[None]]

async def _v2_message_lookup_index(conn: Any) -> None:
    """Add the composite index used by ``MemoryStore.find_message``.

    ``create_all`` only builds indexes when it *creates* the table. A database that
    already has ``messages`` from version 1 keeps its old index set forever, no matter
    how many times startup runs — so a declarative ``Index(...)`` alone would fix fresh
    installs and quietly leave every existing installation doing a full session scan.
    This is the first real step precisely because that gap is otherwise invisible.

    ``IF NOT EXISTS`` makes re-running harmless. The table guard covers databases that
    predate the messages table entirely; their next ``create_all`` builds it with the
    index already declared.
    """
    exists = await conn.execute(
        text("SELECT 1 FROM sqlite_master WHERE type = 'table' AND name = 'messages'")
    )
    if exists.first() is None:
        return
    await conn.execute(
        text(
            "CREATE INDEX IF NOT EXISTS ix_messages_session_message "
            "ON messages (session_key, message_id)"
        )
    )


async def _v3_scene_layer(conn: Any) -> None:
    """Add the scene layer: cards, portraits and links.

    ``create_all`` builds these on a fresh database, so this step exists for the
    databases that already hold conversation history — which is every database that
    matters. Without it, an upgraded binary would query ``scene_cards`` on a database
    that has no such table and fail at the first turn.

    The tables are created empty rather than backfilled. A card is derived from memories,
    and the first ``refresh`` after startup builds it; backfilling here would mean running
    the derivation inside a migration transaction, which is the one place a slow query is
    least affordable.
    """
    await conn.execute(
        text(
            "CREATE TABLE IF NOT EXISTS scene_cards ("
            "id INTEGER PRIMARY KEY AUTOINCREMENT, "
            "scope VARCHAR(128) NOT NULL UNIQUE, "
            "title VARCHAR(256) NOT NULL DEFAULT '', "
            "summary TEXT NOT NULL DEFAULT '', "
            "topics TEXT NOT NULL DEFAULT '', "
            "people TEXT NOT NULL DEFAULT '', "
            "memory_count INTEGER NOT NULL DEFAULT 0, "
            "updated_at FLOAT NOT NULL DEFAULT 0)"
        )
    )
    await conn.execute(
        text("CREATE INDEX IF NOT EXISTS ix_scene_cards_scope ON scene_cards (scope)")
    )
    await conn.execute(
        text("CREATE INDEX IF NOT EXISTS ix_scene_cards_updated ON scene_cards (updated_at)")
    )
    await conn.execute(
        text(
            "CREATE TABLE IF NOT EXISTS scene_portraits ("
            "id INTEGER PRIMARY KEY AUTOINCREMENT, "
            "scope VARCHAR(128) NOT NULL UNIQUE, "
            "headline TEXT NOT NULL DEFAULT '', "
            "themes TEXT NOT NULL DEFAULT '', "
            "tone VARCHAR(64) NOT NULL DEFAULT '', "
            "recurring_questions TEXT NOT NULL DEFAULT '', "
            "memory_count INTEGER NOT NULL DEFAULT 0, "
            "confidence FLOAT NOT NULL DEFAULT 0, "
            "updated_at FLOAT NOT NULL DEFAULT 0)"
        )
    )
    await conn.execute(
        text(
            "CREATE INDEX IF NOT EXISTS ix_scene_portraits_scope "
            "ON scene_portraits (scope)"
        )
    )
    await conn.execute(
        text(
            "CREATE INDEX IF NOT EXISTS ix_scene_portraits_updated "
            "ON scene_portraits (updated_at)"
        )
    )
    await conn.execute(
        text(
            "CREATE TABLE IF NOT EXISTS scene_links ("
            "id INTEGER PRIMARY KEY AUTOINCREMENT, "
            "source_id INTEGER NOT NULL, "
            "target_id INTEGER NOT NULL, "
            "kind VARCHAR(32) NOT NULL DEFAULT 'same_topic', "
            "weight FLOAT NOT NULL DEFAULT 1, "
            "created_at FLOAT NOT NULL DEFAULT 0)"
        )
    )
    await conn.execute(
        text("CREATE INDEX IF NOT EXISTS ix_scene_links_source ON scene_links (source_id)")
    )
    await conn.execute(
        text("CREATE INDEX IF NOT EXISTS ix_scene_links_target ON scene_links (target_id)")
    )
    await conn.execute(
        text("CREATE INDEX IF NOT EXISTS ix_scene_links_kind ON scene_links (kind)")
    )
    await conn.execute(
        text(
            "CREATE UNIQUE INDEX IF NOT EXISTS uq_scene_link "
            "ON scene_links (source_id, target_id, kind)"
        )
    )


async def _column_exists(conn: Any, table: str, column: str) -> bool:
    rows = (await conn.execute(text(f"PRAGMA table_info({table})"))).fetchall()
    return any(str(row[1]) == column for row in rows)


async def _add_column(conn: Any, table: str, column: str, ddl: str) -> None:
    """SQLite has no ``ADD COLUMN IF NOT EXISTS``; a re-run must not fail."""
    if await _column_exists(conn, table, column):
        return
    await conn.execute(text(f"ALTER TABLE {table} ADD COLUMN {column} {ddl}"))


async def _table_exists(conn: Any, table: str) -> bool:
    row = await conn.execute(
        text("SELECT 1 FROM sqlite_master WHERE type = 'table' AND name = :n"),
        {"n": table},
    )
    return row.first() is not None


async def _v4_memory_layers(conn: Any) -> None:
    """L1 window metadata, L2 archive flag, L4 self-notes and the shared timeline.

    ``summaries`` already existed for the compressor; this step adds the slice and
    model it describes. Without them a summary cannot be rebuilt from L0 or compared
    against a different model's output, which makes "the bot remembered something
    wrong" impossible to investigate.

    Both ``ALTER`` candidates are guarded: a migration test can drive this step over a
    database that never ran ``create_all``, and ``ALTER TABLE`` on a missing table is a
    hard error rather than a no-op.
    """
    if await _table_exists(conn, "summaries"):
        await _add_column(conn, "summaries", "window_start", "FLOAT NOT NULL DEFAULT 0")
        await _add_column(conn, "summaries", "window_end", "FLOAT NOT NULL DEFAULT 0")
        await _add_column(conn, "summaries", "model", "VARCHAR(64) NOT NULL DEFAULT ''")
    if await _table_exists(conn, "memories"):
        await _add_column(conn, "memories", "archived", "INTEGER NOT NULL DEFAULT 0")
        await conn.execute(
            text("CREATE INDEX IF NOT EXISTS ix_memories_archived ON memories (archived)")
        )
    await conn.execute(
        text(
            "CREATE TABLE IF NOT EXISTS memory_self_notes ("
            "id INTEGER PRIMARY KEY AUTOINCREMENT, "
            "content TEXT NOT NULL DEFAULT '', "
            "norm VARCHAR(256) NOT NULL DEFAULT '', "
            "source_session VARCHAR(128) NOT NULL DEFAULT '', "
            "created_at FLOAT NOT NULL DEFAULT 0, "
            "updated_at FLOAT NOT NULL DEFAULT 0)"
        )
    )
    await conn.execute(
        text(
            "CREATE UNIQUE INDEX IF NOT EXISTS uq_self_note_norm "
            "ON memory_self_notes (norm)"
        )
    )
    await conn.execute(
        text(
            "CREATE INDEX IF NOT EXISTS ix_self_notes_updated "
            "ON memory_self_notes (updated_at)"
        )
    )
    await conn.execute(
        text(
            "CREATE TABLE IF NOT EXISTS memory_timeline ("
            "id INTEGER PRIMARY KEY AUTOINCREMENT, "
            "kind VARCHAR(24) NOT NULL DEFAULT 'chat', "
            "ref VARCHAR(128) NOT NULL DEFAULT '', "
            "summary TEXT NOT NULL DEFAULT '', "
            "session_key VARCHAR(128) NOT NULL DEFAULT '', "
            "created_at FLOAT NOT NULL DEFAULT 0)"
        )
    )
    for statement in (
        "CREATE INDEX IF NOT EXISTS ix_memory_timeline_kind ON memory_timeline (kind)",
        "CREATE INDEX IF NOT EXISTS ix_memory_timeline_created ON memory_timeline (created_at)",
        "CREATE INDEX IF NOT EXISTS ix_timeline_session_time "
        "ON memory_timeline (session_key, created_at)",
    ):
        await conn.execute(text(statement))


async def _v5_artifact_index(conn: Any) -> None:
    """L3: index rows for produced artifacts; bodies stay in ``data/artifacts``."""
    await conn.execute(
        text(
            "CREATE TABLE IF NOT EXISTS memory_artifacts ("
            "id INTEGER PRIMARY KEY AUTOINCREMENT, "
            "session_key VARCHAR(128) NOT NULL DEFAULT '', "
            "title VARCHAR(256) NOT NULL DEFAULT '', "
            "sha256 VARCHAR(64) NOT NULL DEFAULT '', "
            "path VARCHAR(512) NOT NULL DEFAULT '', "
            "size INTEGER NOT NULL DEFAULT 0, "
            "created_at FLOAT NOT NULL DEFAULT 0)"
        )
    )
    for statement in (
        "CREATE INDEX IF NOT EXISTS ix_memory_artifacts_session "
        "ON memory_artifacts (session_key)",
        "CREATE INDEX IF NOT EXISTS ix_memory_artifacts_sha "
        "ON memory_artifacts (sha256)",
        "CREATE INDEX IF NOT EXISTS ix_memory_artifacts_created "
        "ON memory_artifacts (created_at)",
    ):
        await conn.execute(text(statement))


async def _v6_message_state_and_binding(conn: Any) -> None:
    """Delivery state on messages; QQ-user binding on accounts (unified chat).

    Two columns on ``messages`` (``state`` / ``reason``) make delivery outcomes
    visible to every client: a send failure used to be indistinguishable from "no
    reply", and a pipeline refusal before the persist stage left no row at all.
    ``accounts.qq_user_id`` is the owner-set trust link that lets one QQ private
    conversation join the account's unified session. Both are nullable: legacy rows
    read as ``ok``, unbound accounts read as unbound.
    """
    await _add_column(conn, "messages", "state", "VARCHAR(16)")
    await _add_column(conn, "messages", "reason", "VARCHAR(64)")
    if await _table_exists(conn, "accounts"):
        await _add_column(conn, "accounts", "qq_user_id", "VARCHAR(32)")
        await conn.execute(
            text("CREATE UNIQUE INDEX IF NOT EXISTS uq_accounts_qq_user ON accounts (qq_user_id)")
        )


#: ``{target_version: step}``. The step moves the database *to* ``target_version``.
#:
#: Version 1 was the first schema and needed no step. Version 2 adds the index above.
#: Version 3 adds the scene layer (cards, portraits, links). Version 4 adds the memory
#: layer metadata (summary windows, archive flag, self-notes, timeline). Version 5 adds
#: the artifact index. Version 6 adds message delivery state and the QQ binding.
#: ``tests/test_migrations.py`` monkeypatches this table to exercise the loop, the gap
#: check and rollback independently of the real step.
MIGRATIONS: dict[int, MigrationStep] = {
    2: _v2_message_lookup_index,
    3: _v3_scene_layer,
    4: _v4_memory_layers,
    5: _v5_artifact_index,
    6: _v6_message_state_and_binding,
}


class SchemaTooNewError(RuntimeError):
    """The database was written by a newer build than this one.

    Raised instead of migrating down, because a downgrade is not a schema operation —
    it is a data loss operation with extra steps.
    """

    def __init__(self, found: int, supported: int) -> None:
        super().__init__(
            f"database schema version {found} is newer than this build supports "
            f"({supported}). Upgrade the application, or restore a backup taken "
            f"before the upgrade."
        )
        self.found = found
        self.supported = supported


async def _ensure_version_table(conn: Any) -> None:
    await conn.execute(
        text(
            "CREATE TABLE IF NOT EXISTS schema_version ("
            "id INTEGER PRIMARY KEY, version INTEGER NOT NULL DEFAULT 0, "
            "applied_at REAL NOT NULL DEFAULT 0)"
        )
    )


async def current_version(conn: Any) -> int | None:
    """The recorded version, or ``None`` when the table has no row yet.

    ``None`` is meaningfully different from ``0``: no row means a database
    ``create_all`` has just built (already at the latest schema), while ``0`` would
    mean "this database predates versioning". Treating the two the same would run
    every migration against a brand-new database.
    """
    await _ensure_version_table(conn)
    row = (await conn.execute(text("SELECT version FROM schema_version WHERE id = 1"))).first()
    return None if row is None else int(row[0])


async def _set_version(conn: Any, version: int) -> None:
    await conn.execute(
        text(
            "INSERT INTO schema_version (id, version, applied_at) VALUES (1, :v, :t) "
            "ON CONFLICT(id) DO UPDATE SET version = :v, applied_at = :t"
        ),
        {"v": version, "t": time.time()},
    )


async def migrate(conn: Any, *, target: int) -> int:
    """Bring the database to ``target``. Returns the version it ends at.

    ``conn`` is an open connection inside a transaction the caller controls, so a
    failure rolls back every statement of the current step together with its version
    bump.
    """
    found = await current_version(conn)

    if found is None:
        # A fresh database: ``create_all`` already built the target schema, so there
        # is nothing to migrate. Record it so the next start has a version to read.
        await _set_version(conn, target)
        logger.info("database initialised at schema version %s", target)
        return target

    if found > target:
        raise SchemaTooNewError(found, target)

    if found == target:
        return target

    version = found
    while version < target:
        step = MIGRATIONS.get(version + 1)
        if step is None:
            # A gap in the table means the build is internally inconsistent. Failing
            # loudly beats arriving at a version number nothing actually applied.
            raise RuntimeError(
                f"no migration registered for schema version {version + 1} "
                f"(database is at {version}, this build wants {target})"
            )
        logger.info("applying schema migration %s -> %s", version, version + 1)
        await step(conn)
        version += 1
        await _set_version(conn, version)

    return version
