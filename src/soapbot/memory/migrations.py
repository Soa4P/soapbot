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


#: ``{target_version: step}``. The step moves the database *to* ``target_version``.
#:
#: Version 1 was the first schema and needed no step. Version 2 adds the index above.
#: ``tests/test_migrations.py`` monkeypatches this table to exercise the loop, the gap
#: check and rollback independently of the real step.
MIGRATIONS: dict[int, MigrationStep] = {2: _v2_message_lookup_index}


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
