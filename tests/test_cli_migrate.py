"""``soapbot migrate``: the upgrade step ``UPDATING.md`` has always promised.

The command is small; the states it must not confuse are not. Every test here is about a
way the command could destroy or misreport a database:

* a missing file must not be created — ``engine.begin()`` on a missing SQLite path makes
  an empty database, and stamping that leaves a file that claims version 5 and has no
  tables;
* ``--status`` and ``--dry-run`` must not write, which rules out
  ``migrations.current_version()`` (it runs ``CREATE TABLE``);
* a database from before versioning must actually run steps 2..5, not be stamped at 5 —
  stamping skips the tables the new code queries on the first turn;
* a newer database must be refused, never migrated down;
* a failure must leave the version untouched, and must report where it really is.

The tests drive ``soapbot.cli.main`` rather than ``cli_migrate.run`` so the flags are
exercised as documented, the same choice ``test_cli_setup.py`` makes.
"""

from __future__ import annotations

import sqlite3
from pathlib import Path

import pytest

import soapbot.cli_migrate as cli_migrate
from soapbot import cli
from soapbot.config import settings
from soapbot.memory.db import SCHEMA_VERSION, Database
from soapbot.memory.migrations import MIGRATIONS

#: Tables added by steps 3, 4 and 5. Dropping them (plus the version row) turns a
#: current-schema file into what a pre-versioning database looked like.
LATER_TABLES = (
    "scene_cards",
    "scene_portraits",
    "scene_links",
    "memory_self_notes",
    "memory_timeline",
    "memory_artifacts",
)


@pytest.fixture
def db_path(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Path:
    """Point ``settings`` at a temporary database file that does not exist yet."""
    path = tmp_path / "soapbot.db"
    monkeypatch.setattr(settings, "data_dir", tmp_path, raising=False)
    monkeypatch.setattr(settings, "db_url", "", raising=False)
    return path


def _run(*argv: str) -> int:
    return cli.main(["migrate", *argv])


def _tables(path: Path) -> set[str]:
    conn = sqlite3.connect(f"file:{path}?mode=ro", uri=True)
    try:
        return {str(r[0]) for r in conn.execute("SELECT name FROM sqlite_master WHERE type='table'")}
    finally:
        conn.close()


def _version(path: Path) -> int | None:
    conn = sqlite3.connect(f"file:{path}?mode=ro", uri=True)
    try:
        row = conn.execute("SELECT version FROM schema_version WHERE id = 1").fetchone()
        return None if row is None else int(row[0])
    except sqlite3.Error:
        return None
    finally:
        conn.close()


async def _build_current_schema(path: Path) -> None:
    db = Database(f"sqlite+aiosqlite:///{path.as_posix()}")
    try:
        await db.init()
    finally:
        await db.engine.dispose()


async def _make_legacy(path: Path) -> None:
    """A database with real history and no version record — the dangerous case.

    Built by creating the current schema and then removing what versions 3-5 add, which
    is the closest thing to a genuine v1 file that does not require keeping a copy of the
    old schema around.
    """
    await _build_current_schema(path)
    conn = sqlite3.connect(path)
    try:
        for table in LATER_TABLES:
            conn.execute(f"DROP TABLE IF EXISTS {table}")
        conn.execute("DROP TABLE IF EXISTS schema_version")
        conn.execute(
            "INSERT INTO messages (session_key, adapter, scene, group_id, user_id, "
            "user_name, role, content, image_desc, message_id, trace_id, created_at) "
            "VALUES ('g1', 'onebot11', 'group', 'g1', 'u1', 'alice', 'user', "
            "'history that must survive', '', 'm1', '', 0.0)"
        )
        conn.commit()
    finally:
        conn.close()


# --------------------------------------------------------------- never create a file
def test_a_missing_database_is_refused_and_not_created(
    db_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    """The file must not appear. A created file would be an empty database.

    ``engine.begin()`` on a missing SQLite path creates it. If the command then stamped
    the version, the operator would end up with a file that opens, reports version 5, and
    fails every query — strictly worse than the "no database" they started with.
    """
    assert _run() == cli_migrate.EXIT_FAILED
    assert not db_path.exists(), "the command created a database it was told to migrate"
    err = capsys.readouterr().err
    assert "没有可迁移的数据库" in err
    assert "不会创建新库" in err


def test_a_zero_byte_file_is_reported_as_empty_not_missing(
    db_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    """A 0-byte file is a different problem from a missing one, and says so."""
    db_path.write_bytes(b"")
    assert _run("--status") == cli_migrate.EXIT_FAILED
    err = capsys.readouterr().err
    assert "空库" in err
    assert "文件不存在" not in err


def test_a_corrupt_file_is_not_reported_as_empty(
    db_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    """A truncated file is a different problem from an empty one, and needs different advice.

    ``probe()`` used to fold every ``sqlite3.Error`` into ``"empty"``, which sent the
    operator to "start the service once so it builds the schema" — wrong for a corrupt
    file, and it invites the service to write over whatever was left.
    """
    db_path.write_bytes(b"SQLite format 3\x00" + b"\x00" * 100)  # valid magic, garbage body
    assert _run("--status") == cli_migrate.EXIT_FAILED
    err = capsys.readouterr().err
    assert "无法读取" in err
    assert "空库" not in err
    assert "启动一次服务" not in err, "corrupt file was given the empty-file advice"
    assert db_path.read_bytes().startswith(b"SQLite format 3"), "the file was overwritten"


# ------------------------------------------------------------ read-only really is
def test_status_does_not_write_to_the_database(
    db_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    """``--status`` must not create ``schema_version``.

    ``migrations.current_version()`` would: it calls ``_ensure_version_table()``, a
    ``CREATE TABLE``. Asking "what version is this?" must not change the answer.
    """
    db_path.write_bytes(b"")  # exists, so the "missing" branch is not what refuses it
    before = db_path.stat().st_size
    _run("--status")
    assert db_path.stat().st_size == before
    assert "schema_version" not in _tables(db_path)


def test_dry_run_lists_steps_without_touching_the_database(
    db_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    """Every step appears, and the file is byte-identical afterwards."""
    import asyncio

    asyncio.run(_make_legacy(db_path))
    before = db_path.read_bytes()

    assert _run("--dry-run") == cli_migrate.EXIT_OK
    captured = capsys.readouterr()

    assert db_path.read_bytes() == before, "--dry-run wrote to the database"
    assert "schema_version: 1 ->" in captured.out
    for version in range(2, SCHEMA_VERSION + 1):
        assert f"{version - 1} -> {version}" in captured.out
    assert "未执行" in captured.err


def test_status_prints_one_machine_readable_line(
    db_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    """stdout stays greppable; the explanation goes to stderr.

    Same contract as ``soapbot token``: stdout is the value, stderr is the commentary, so
    ``soapbot migrate --status | cut -d' ' -f2`` keeps working.
    """
    import asyncio

    asyncio.run(_build_current_schema(db_path))
    assert _run("--status") == cli_migrate.EXIT_OK
    out = capsys.readouterr().out
    assert len(out.splitlines()) == 1
    assert out.startswith("schema_version: ")
    assert f"-> {SCHEMA_VERSION}" in out


# ------------------------------------------------------- a legacy database is migrated
def test_a_legacy_database_runs_every_step_and_keeps_its_rows(
    db_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    """The case the whole command exists for.

    Stamping a pre-versioning database at the target would skip v3-v5, and the new code
    queries ``scene_cards`` on the first turn. So the tables must actually appear, and the
    history must still be there afterwards.
    """
    import asyncio

    asyncio.run(_make_legacy(db_path))
    assert _version(db_path) is None, "fixture should have no version record"

    assert _run() == cli_migrate.EXIT_OK
    out = capsys.readouterr().out

    assert _version(db_path) == SCHEMA_VERSION
    tables = _tables(db_path)
    for table in LATER_TABLES:
        assert table in tables, f"{table} was not created — the step was skipped"

    conn = sqlite3.connect(f"file:{db_path}?mode=ro", uri=True)
    try:
        rows = conn.execute("SELECT content FROM messages").fetchall()
    finally:
        conn.close()
    assert rows == [("history that must survive",)]
    assert f"完成：schema version {SCHEMA_VERSION}" in out


def test_a_legacy_database_is_announced_before_it_is_touched(
    db_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    """An operator should learn that this file predates versioning, not discover it."""
    import asyncio

    asyncio.run(_make_legacy(db_path))
    _run("--status")
    err = capsys.readouterr().err
    assert "早于版本控制" in err


# ------------------------------------------------------------------- never go backwards
def test_a_newer_database_is_refused_with_both_versions(
    db_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    """Downgrading is data loss with extra steps, so it is not offered."""
    import asyncio

    asyncio.run(_build_current_schema(db_path))
    conn = sqlite3.connect(db_path)
    try:
        conn.execute("UPDATE schema_version SET version = ? WHERE id = 1", (SCHEMA_VERSION + 1,))
        conn.commit()
    finally:
        conn.close()

    assert _run() == cli_migrate.EXIT_TOO_NEW
    err = capsys.readouterr().err
    assert str(SCHEMA_VERSION + 1) in err
    assert str(SCHEMA_VERSION) in err
    assert _version(db_path) == SCHEMA_VERSION + 1, "the refused database was modified"


def test_a_target_below_the_current_version_is_refused(
    db_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    """``--target`` is a ceiling, not a downgrade switch."""
    import asyncio

    asyncio.run(_build_current_schema(db_path))
    assert _run("--target", "2") == cli_migrate.EXIT_TOO_NEW
    assert _version(db_path) == SCHEMA_VERSION
    assert "不提供降级" in capsys.readouterr().err


def test_a_target_above_this_build_is_refused(
    db_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    """Claiming a version this build has no step for would be a lie in the file."""
    import asyncio

    asyncio.run(_make_legacy(db_path))
    assert _run("--target", str(SCHEMA_VERSION + 1)) == cli_migrate.EXIT_FAILED
    assert _version(db_path) is None, "the refused database was modified"
    assert "超出本版本支持的范围" in capsys.readouterr().err


# ------------------------------------------------------------------- already up to date
def test_a_current_database_is_left_alone(
    db_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    """Running it twice is safe, and the second run says so instead of redoing work."""
    import asyncio

    asyncio.run(_build_current_schema(db_path))
    before = db_path.read_bytes()

    assert _run() == cli_migrate.EXIT_OK
    assert "无需迁移" in capsys.readouterr().out
    assert db_path.read_bytes() == before


# -------------------------------------------------------------- a gap is not papered over
def test_a_gap_in_the_migration_chain_is_refused_before_anything_runs(
    db_path: Path, capsys: pytest.CaptureFixture[str], monkeypatch: pytest.MonkeyPatch
) -> None:
    """A missing step means the build is inconsistent; stop rather than arrive at a
    version number nothing applied."""
    import asyncio

    asyncio.run(_make_legacy(db_path))
    before = db_path.read_bytes()

    broken = {k: v for k, v in MIGRATIONS.items() if k != 3}
    monkeypatch.setattr("soapbot.memory.migrations.MIGRATIONS", broken)

    assert _run() == cli_migrate.EXIT_FAILED
    assert "缺少步骤" in capsys.readouterr().err
    assert db_path.read_bytes() == before, "a build with a gap still wrote to the database"


def test_a_failing_step_reports_the_real_version_after_rollback(
    db_path: Path, capsys: pytest.CaptureFixture[str], monkeypatch: pytest.MonkeyPatch
) -> None:
    """The stamp and the first step share a transaction, so a failure rolls back both.

    Reporting "still at version 1" here would describe a file that has no version table at
    all — the operator would go looking for a row that is not there.
    """
    import asyncio

    async def _boom(conn) -> None:
        raise RuntimeError("simulated step failure")

    asyncio.run(_make_legacy(db_path))
    monkeypatch.setitem(MIGRATIONS, 2, _boom)

    assert _run() == cli_migrate.EXIT_FAILED
    err = capsys.readouterr().err
    assert "迁移失败" in err
    assert "回滚" in err
    assert _version(db_path) is None
    assert "仍停在 version 1" not in err, "the message claims a version row that was rolled back"


# --------------------------------------------------------------------------- encoding
def test_chinese_output_survives_a_cp936_console(monkeypatch: pytest.MonkeyPatch) -> None:
    """The hints are Chinese; a Windows console defaults to cp936.

    ``check_console_encoding.py`` only scans ``scripts/``, so ``src/`` has to reconfigure
    its own streams. Without it the command dies on its own error message, which looks
    like a defect in whatever it was inspecting.
    """
    calls: list[dict[str, object]] = []

    class _Stream:
        def reconfigure(self, **kwargs: object) -> None:
            calls.append(kwargs)

    monkeypatch.setattr(cli_migrate.sys, "stdout", _Stream())
    monkeypatch.setattr(cli_migrate.sys, "stderr", _Stream())
    cli_migrate._reconfigure_streams()

    assert len(calls) == 2
    assert all(c["encoding"] == "utf-8" for c in calls)
    assert all(c["errors"] == "replace" for c in calls)
