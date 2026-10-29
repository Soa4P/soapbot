"""Schema migrations: the three states a database can be in, and what each does.

The interesting part is not "a migration runs" — it is what happens in the states an
operator actually hits: a brand-new file, an older file from a previous release, and a
file written by a *newer* release (someone downgraded the package, or restored the
wrong backup). The last one is the dangerous case, and the only acceptable behaviour is
refusing to start.
"""

from __future__ import annotations

import pytest
import pytest_asyncio
from sqlalchemy import text
from sqlalchemy.ext.asyncio import create_async_engine

from soapbot.memory import migrations
from soapbot.memory.db import SCHEMA_VERSION, Database


@pytest_asyncio.fixture
async def engine(tmp_path):
    eng = create_async_engine(f"sqlite+aiosqlite:///{tmp_path / 'm.db'}", future=True)
    yield eng
    await eng.dispose()


async def test_fresh_database_is_stamped_at_the_current_version(engine) -> None:
    """``create_all`` built the target schema, so no step should run."""
    async with engine.begin() as conn:
        assert await migrations.current_version(conn) is None
        ended = await migrations.migrate(conn, target=SCHEMA_VERSION)
        assert ended == SCHEMA_VERSION
        assert await migrations.current_version(conn) == SCHEMA_VERSION


async def test_a_registered_step_runs_once_and_records_its_version(engine, monkeypatch) -> None:
    """Exercises the machinery, not just the empty-table case.

    Without this, ``MIGRATIONS`` being empty would make every other test pass while
    the loop that applies steps was never executed — the classic "untested because
    nothing uses it yet" gap that turns into a bug on the first real migration.
    """
    calls: list[int] = []

    async def step(conn) -> None:
        calls.append(1)
        await conn.execute(text("CREATE TABLE IF NOT EXISTS probe_v2 (id INTEGER)"))

    monkeypatch.setitem(migrations.MIGRATIONS, 2, step)

    async with engine.begin() as conn:
        await migrations.current_version(conn)  # create the version table
        await migrations._set_version(conn, 1)

    async with engine.begin() as conn:
        ended = await migrations.migrate(conn, target=2)
        assert ended == 2
        assert calls == [1]
        assert await migrations.current_version(conn) == 2

    # Running again must be a no-op: the version already matches the target.
    async with engine.begin() as conn:
        assert await migrations.migrate(conn, target=2) == 2
        assert calls == [1], "a completed migration must not run twice"


async def test_a_newer_database_refuses_to_start(engine) -> None:
    """Downgrading the package must not silently write an old schema.

    The message names both numbers, because the operator's next question is always
    "which version am I on, and which does this build want?".
    """
    async with engine.begin() as conn:
        await migrations.current_version(conn)
        await migrations._set_version(conn, 99)

    async with engine.begin() as conn:
        with pytest.raises(migrations.SchemaTooNewError) as excinfo:
            await migrations.migrate(conn, target=SCHEMA_VERSION)

    assert excinfo.value.found == 99
    assert excinfo.value.supported == SCHEMA_VERSION
    assert "99" in str(excinfo.value) and str(SCHEMA_VERSION) in str(excinfo.value)


async def test_a_gap_in_the_chain_is_an_error_not_a_silent_skip(engine) -> None:
    """A missing step means the build is inconsistent; arriving at the target version
    with nothing applied would be worse than failing."""
    async with engine.begin() as conn:
        await migrations.current_version(conn)
        await migrations._set_version(conn, 1)

    async with engine.begin() as conn:
        with pytest.raises(RuntimeError, match="no migration registered"):
            await migrations.migrate(conn, target=5)


async def test_a_failing_step_leaves_the_version_untouched(engine, monkeypatch) -> None:
    """Half-applied migrations must be retried, not skipped.

    The step runs inside the caller's transaction; a raise rolls back both the DDL and
    the version bump, so the next start re-runs the whole step from the old version.
    """

    async def boom(conn) -> None:
        raise RuntimeError("mid-migration failure")

    monkeypatch.setitem(migrations.MIGRATIONS, 2, boom)

    async with engine.begin() as conn:
        await migrations.current_version(conn)
        await migrations._set_version(conn, 1)

    async with engine.begin() as conn:
        with pytest.raises(RuntimeError, match="mid-migration failure"):
            await migrations.migrate(conn, target=2)

    async with engine.begin() as conn:
        assert await migrations.current_version(conn) == 1


async def test_the_real_database_reports_its_version(tmp_path) -> None:
    """End-to-end through ``Database``, which is what startup actually calls.

    A migration layer that works in isolation but is not wired into ``init`` would
    keep every test above green and change nothing in production.
    """
    db = Database(f"sqlite+aiosqlite:///{tmp_path / 'real.db'}")
    try:
        await db.init()
        assert await db.schema_version() == SCHEMA_VERSION
    finally:
        await db.engine.dispose()


async def test_reopening_a_database_does_not_re_migrate(tmp_path) -> None:
    """Startup runs on every boot; it must be cheap and non-destructive after the first."""
    url = f"sqlite+aiosqlite:///{tmp_path / 'twice.db'}"
    first = Database(url)
    try:
        await first.init()
    finally:
        await first.engine.dispose()

    second = Database(url)
    try:
        await second.init()
        assert await second.schema_version() == SCHEMA_VERSION
    finally:
        await second.engine.dispose()
