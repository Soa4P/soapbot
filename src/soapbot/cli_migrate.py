"""``soapbot migrate`` — the upgrade step ``UPDATING.md`` tells operators to run.

Why a command and not "startup does it"
---------------------------------------
Startup *does* migrate (``Database.init`` runs ``migrate`` in the same transaction as
``create_all``). The command exists for the moment an operator wants the upgrade to be a
separate, observable step: before starting the new binary, after restoring a backup, or
while diagnosing why a boot failed. ``UPDATING.md`` has promised it since the first
release; until now the argument parser had no such subcommand, so following the guide
printed the help text and exited 1.

The state that makes this subtle
--------------------------------
``migrations.migrate()`` treats "no version row" as "a database ``create_all`` has just
built", and stamps it at the target version without running any step. That is correct at
startup, where ``create_all`` has just produced the target schema. It is catastrophic for
a database that predates versioning and holds real conversation history: stamping it at 5
would skip the v2..v5 indexes and tables, and the new code would fail on the first query
naming a column that was never added.

So this module distinguishes five states, and only one of them may be stamped:

===================  ==========================================  =======================
state                how it is recognised                        what happens
===================  ==========================================  =======================
``missing``          no file                                     refuse (exit 1)
``empty``            zero bytes, or no tables at all             refuse (exit 1)
``unreadable``       exists but ``sqlite3`` cannot open it       refuse (exit 1)
``legacy``           has ``messages``/``memories``/... but no    stamp 1, then run 2..N
                     ``schema_version`` row
``versioned``        ``schema_version.version`` reads back       compare, then run
===================  ==========================================  =======================

``unreadable`` is kept apart from ``empty`` on purpose: the advice differs. An empty file
wants "start the service once so it builds the schema"; a truncated or corrupt file wants
"check the path, then restore from backup" — and telling the operator to start the service
would both mislead and risk writing over evidence.

``missing`` and ``empty`` are refused rather than initialised because this command's
contract is "migrate an existing database", not "create one". Creating one here would
leave a file containing only ``schema_version`` and no business tables — it opens, it
reports version 5, and every query fails. The fix for that state is to start the service
once, which is what builds the schema.

Read-only means read-only
-------------------------
``--status`` and ``--dry-run`` must not write. That rules out
``migrations.current_version()``, which calls ``_ensure_version_table()`` — a
``CREATE TABLE``. They use a plain ``sqlite3`` connection opened with ``mode=ro``
instead, the same approach ``scripts/backup.py`` uses to read a version without
touching the file.
"""

from __future__ import annotations

import sqlite3
import sys
from pathlib import Path
from typing import Any

#: Exit codes. 2 is reserved for "the database is newer than this build", matching
#: ``doctor --strict``: a script can then tell "upgrade the application" apart from
#: "the migration failed".
EXIT_OK = 0
EXIT_FAILED = 1
EXIT_TOO_NEW = 2

#: Tables that only exist once the service has actually run. Their presence is what
#: separates "a database from before versioning" from "an empty file": the former must be
#: stamped at 1 and migrated forward, the latter must be refused.
LEGACY_TABLES = frozenset({"messages", "memories", "knowledge", "summaries"})

_SQLITE_PREFIX = "sqlite+aiosqlite:///"


def _reconfigure_streams() -> None:
    """Windows consoles default to cp936; a Chinese hint would raise or mojibake.

    Same reason as ``_run_token`` and ``_run_doctor`` in ``cli.py``: a command that dies
    on its own output looks like a defect in whatever it was inspecting.
    """
    for stream in (sys.stdout, sys.stderr):
        if hasattr(stream, "reconfigure"):
            stream.reconfigure(encoding="utf-8", errors="replace")


def sqlite_path(url: str) -> Path | None:
    """The file behind a ``sqlite+aiosqlite`` URL, or ``None`` for anything else.

    Only SQLite is supported: the read-only probe below is ``sqlite3``, and pretending
    to support a server database with a file check would be worse than refusing.
    """
    if not url.startswith(_SQLITE_PREFIX):
        return None
    return Path(url[len(_SQLITE_PREFIX) :])


def probe(db_path: Path) -> tuple[str, int | None]:
    """Classify the database without writing to it.

    Returns ``(state, version)`` where ``state`` is one of ``missing``, ``empty``,
    ``unreadable``, ``legacy`` or ``versioned``. ``version`` is only meaningful for
    ``versioned``.

    The connection is closed explicitly: ``with sqlite3.connect(...)`` commits on exit
    but does not close, and on Windows a lingering handle makes the next operation on
    that file fail with "file is in use by another process".
    """
    if not db_path.is_file():
        return "missing", None
    if db_path.stat().st_size == 0:
        # A zero-byte file is what a failed ``touch`` or an interrupted create leaves
        # behind. It has no tables either, but reporting it as "file not found" sends
        # the operator looking for the wrong problem.
        return "empty", None

    conn = None
    try:
        conn = sqlite3.connect(f"file:{db_path}?mode=ro", uri=True)
        try:
            row = conn.execute("SELECT version FROM schema_version WHERE id = 1").fetchone()
        except sqlite3.Error:
            # No version table at all: either pre-versioning or an empty file. The table
            # list below decides which.
            row = None
        if row is not None:
            return "versioned", int(row[0])

        names = {
            str(record[0])
            for record in conn.execute("SELECT name FROM sqlite_master WHERE type = 'table'")
        }
        if names & LEGACY_TABLES:
            return "legacy", None
        return "empty", None
    except sqlite3.Error:
        # Not "empty": a file that cannot be opened is a different problem with a
        # different fix. Reporting it as empty would send the operator to "start the
        # service once so it builds the schema", which is the wrong advice for a
        # truncated or corrupt file and may overwrite evidence worth keeping.
        return "unreadable", None
    finally:
        if conn is not None:
            conn.close()


def _steps(start: int, target: int, migrations: dict[int, Any]) -> list[tuple[int, int, str]]:
    """``(from, to, name)`` for every step between ``start`` and ``target``."""
    out: list[tuple[int, int, str]] = []
    for version in range(start + 1, target + 1):
        step = migrations.get(version)
        out.append((version - 1, version, getattr(step, "__name__", "<missing>")))
    return out


def _describe(state: str, found: int | None, target: int, db_path: Path) -> str:
    """The one-line machine-readable summary ``--status`` prints to stdout."""
    if state == "versioned":
        return f"schema_version: {found} -> {target}"
    if state == "legacy":
        return f"schema_version: 1 -> {target} (unversioned database, treated as v1)"
    return f"schema_version: ? -> {target} ({state})"


def _apply(url: str, start: int, target: int, *, stamp: bool) -> int:
    """Run the migration chain and return the version it ends at.

    ``Database.init()`` is deliberately not used: it runs ``create_all`` first, which
    would add the very tables and columns the migration is supposed to add, turning a
    real upgrade into a silent no-op that reports success.
    """
    import asyncio

    from soapbot.memory.db import Database
    from soapbot.memory.migrations import _set_version, current_version, migrate

    async def _run() -> int:
        db = Database(url)
        try:
            async with db.engine.begin() as conn:
                if stamp:
                    # ``current_version`` creates the version table as a side effect,
                    # which is what makes the stamp possible on a legacy file.
                    await current_version(conn)
                    await _set_version(conn, start)
                return await migrate(conn, target=target)
        finally:
            await db.engine.dispose()

    return asyncio.run(_run())


def run(args: Any) -> int:
    """Entry point for ``soapbot migrate``. See the module docstring for the states."""
    _reconfigure_streams()

    from soapbot.config import settings
    from soapbot.memory.db import SCHEMA_VERSION
    from soapbot.memory.migrations import MIGRATIONS, SchemaTooNewError

    url = settings.resolved_db_url
    db_path = sqlite_path(url)
    if db_path is None:
        print(
            f"soapbot migrate 只支持 SQLite（当前 SOAPBOT_DB_URL={url}）。\n"
            "服务端数据库请用它自己的迁移工具。",
            file=sys.stderr,
        )
        return EXIT_FAILED

    target = SCHEMA_VERSION if args.target is None else int(args.target)
    if target < 1:
        print(f"--target 必须 >= 1（收到 {target}）", file=sys.stderr)
        return EXIT_FAILED
    if target > SCHEMA_VERSION:
        print(
            f"--target {target} 超出本版本支持的范围：SCHEMA_VERSION={SCHEMA_VERSION}。\n"
            "迁移只前进，且只能到达本程序认识的版本；升级程序后再试。",
            file=sys.stderr,
        )
        return EXIT_FAILED

    state, found = probe(db_path)

    if state == "unreadable":
        print(
            f"数据库无法读取：{db_path}。\n"
            "\n"
            "文件存在但不是可用的 SQLite 库（可能被截断或损坏）。本命令不会尝试修复，\n"
            "也不会覆盖它——先确认路径是否正确，再从备份恢复。",
            file=sys.stderr,
        )
        return EXIT_FAILED

    if state in {"missing", "empty"}:
        # Never create the file here. ``engine.begin()`` on a missing SQLite path creates
        # an empty database, and stamping it would leave a file that reports version 5
        # while containing no business tables.
        reason = "文件不存在" if state == "missing" else "文件存在但没有任何表（空库）"
        print(
            f"没有可迁移的数据库：{db_path}（{reason}）。\n"
            "\n"
            "本命令只迁移已存在的库，不会创建新库——那样只会留下一个只有版本号、\n"
            "没有任何业务表的文件。请先启动一次服务让它建表，或检查 SOAPBOT_DATA_DIR\n"
            "是否指向了正确的目录。",
            file=sys.stderr,
        )
        return EXIT_FAILED

    start = 1 if state == "legacy" else int(found or 0)

    if start > target:
        error = SchemaTooNewError(start, target)
        print(f"{error}", file=sys.stderr)
        print(
            "\n数据库比程序新。升级程序，或从升级前的备份恢复；不提供降级。",
            file=sys.stderr,
        )
        return EXIT_TOO_NEW

    if getattr(args, "status", False):
        print(_describe(state, found, target, db_path))
        if state == "legacy":
            print(
                "该库早于版本控制（有业务表、无版本记录），将按 v1 处理并顺序补齐。",
                file=sys.stderr,
            )
        if start == target:
            print("已是最新，无需迁移。", file=sys.stderr)
        return EXIT_OK

    if getattr(args, "dry_run", False):
        print(_describe(state, found, target, db_path))
        steps = _steps(start, target, MIGRATIONS)
        if not steps:
            print("已是最新，没有要执行的步骤。", file=sys.stderr)
            return EXIT_OK
        for before, after, name in steps:
            print(f"  {before} -> {after}  {name}")
        missing = [f"{b} -> {a}" for b, a, name in steps if name == "<missing>"]
        if missing:
            print(
                f"\n本程序缺少步骤：{', '.join(missing)}。构建不一致，不会执行。",
                file=sys.stderr,
            )
            return EXIT_FAILED
        print("\n--dry-run：以上步骤均未执行，数据库没有任何改动。", file=sys.stderr)
        return EXIT_OK

    if start == target:
        print(f"数据库已在 schema version {target}，无需迁移。")
        return EXIT_OK

    steps = _steps(start, target, MIGRATIONS)
    missing = [f"{b} -> {a}" for b, a, name in steps if name == "<missing>"]
    if missing:
        print(
            f"迁移链缺少步骤：{', '.join(missing)}。\n"
            "这通常意味着安装的代码不完整；不会带着缺口执行。",
            file=sys.stderr,
        )
        return EXIT_FAILED

    print(f"正在迁移 {db_path}：{start} -> {target}")
    if state == "legacy":
        print("  检测到早于版本控制的库，先记为 v1 再顺序补齐。", file=sys.stderr)

    try:
        ended = _apply(url, start, target, stamp=state == "legacy")
    except SchemaTooNewError as exc:
        print(f"{exc}", file=sys.stderr)
        return EXIT_TOO_NEW
    except Exception as exc:
        # The step ran inside a transaction, so the version is untouched and the next
        # attempt retries the whole step. Say that, because "it failed" alone invites
        # restoring a backup that is not needed.
        #
        # The version is re-read rather than assumed to be ``start``: a legacy database
        # is stamped inside the *same* transaction as the first step, so a failure rolls
        # the stamp back too and leaves no version row at all. Reporting "still at
        # version 1" there would be a lie about a file that has no version table.
        after_state, after_version = probe(db_path)
        if after_state == "versioned":
            where = f"数据库仍停在 version {after_version}"
        elif after_state == "legacy":
            where = "数据库仍没有版本记录（盖章与首个步骤在同一事务内，已一并回滚）"
        else:
            where = f"数据库当前状态为 {after_state}"
        print(
            f"迁移失败：{exc}\n"
            f"事务已回滚，{where}。修复后重跑本命令即可。",
            file=sys.stderr,
        )
        return EXIT_FAILED

    print(f"完成：schema version {ended}")
    return EXIT_OK
