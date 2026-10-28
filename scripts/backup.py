"""Back up the writable state of a running soapbot into one archive.

What is included, and why each one
-----------------------------------
* ``soapbot.db`` — messages, memory, knowledge, budget reservations, approvals.
* ``config/`` — providers, adapters, personas, MCP servers. Configuration lives
  outside ``data/`` precisely so a compromised plugin cannot rewrite it, which also
  means a backup of ``data/`` alone restores a bot that points at whatever config it
  happens to find.
* a manifest — schema version and file list, read by ``restore.py`` before it touches
  anything.

How the database is copied
--------------------------
``sqlite3.Connection.backup`` rather than ``shutil.copy``. The service keeps the
database open in WAL mode, so a plain file copy can capture a database whose -wal
still holds committed pages: it opens cleanly and is silently missing the last
messages. The backup API takes a consistent snapshot while writers continue.

The archive is written to a temporary file and renamed at the end, so a backup that
fails halfway does not leave something that looks like a backup.
"""

from __future__ import annotations

import argparse
import json
import os
import sqlite3
import sys
import tempfile
import time
import zipfile
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent


def _schema_version(db_path: Path) -> int:
    """Return the DB's schema version, or 0 for a database without one.

    Closed explicitly: ``with sqlite3.connect(...)`` commits on exit but does **not**
    close, and on Windows an open handle makes the following ``unlink`` of the
    snapshot fail with "file is in use by another process".
    """
    conn = None
    try:
        conn = sqlite3.connect(f"file:{db_path}?mode=ro", uri=True)
        row = conn.execute("SELECT version FROM schema_version LIMIT 1").fetchone()
        return int(row[0]) if row else 0
    except sqlite3.Error:
        return 0
    finally:
        if conn is not None:
            conn.close()


def _snapshot_database(source: Path, destination: Path) -> None:
    """Consistent copy of a live SQLite database."""
    src = sqlite3.connect(f"file:{source}?mode=ro", uri=True)
    try:
        dst = sqlite3.connect(destination)
        try:
            src.backup(dst)
        finally:
            dst.close()
    finally:
        src.close()


def build(data_dir: Path, config_dir: Path, out_path: Path) -> dict:
    tmp_fd, tmp_name = tempfile.mkstemp(suffix=".zip", dir=str(out_path.parent))
    os.close(tmp_fd)
    tmp_path = Path(tmp_name)

    files: list[str] = []
    db_path = data_dir / "soapbot.db"
    schema_version = 0

    try:
        with zipfile.ZipFile(tmp_path, "w", zipfile.ZIP_DEFLATED) as archive:
            if db_path.is_file():
                snapshot = Path(tmp_name + ".db")
                try:
                    _snapshot_database(db_path, snapshot)
                    schema_version = _schema_version(snapshot)
                    archive.write(snapshot, "data/soapbot.db")
                    files.append("data/soapbot.db")
                finally:
                    snapshot.unlink(missing_ok=True)

            for path in sorted(config_dir.rglob("*")):
                if not path.is_file() or path.name.startswith("."):
                    continue
                arcname = f"config/{path.relative_to(config_dir).as_posix()}"
                archive.writestr(arcname, path.read_bytes())
                files.append(arcname)

            manifest = {
                "tool": "soapbot-backup",
                "created_at": time.time(),
                "schema_version": schema_version,
                "files": files,
            }
            archive.writestr("manifest.json", json.dumps(manifest, indent=2))

        tmp_path.replace(out_path)
    except BaseException:
        tmp_path.unlink(missing_ok=True)
        raise

    return {"path": str(out_path), "files": len(files), "schema_version": schema_version}


def main(argv: list[str] | None = None) -> int:
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")

    from soapbot.config import settings

    parser = argparse.ArgumentParser(description="备份 data/ 与 config/ 到一个 zip")
    parser.add_argument(
        "--out",
        default="",
        help="输出文件（默认 soapbot-backup-<时间戳>.zip）",
    )
    parser.add_argument("--data-dir", default=str(settings.data_dir))
    parser.add_argument("--config-dir", default=str(settings.config_dir))
    args = parser.parse_args(argv)

    data_dir = Path(args.data_dir)
    config_dir = Path(args.config_dir)
    if not data_dir.is_dir():
        print(f"数据目录不存在：{data_dir}")
        return 2

    stamp = time.strftime("%Y%m%d-%H%M%S")
    out = Path(args.out or f"soapbot-backup-{stamp}.zip")
    result = build(data_dir, config_dir, out)

    print(f"备份完成：{result['path']}")
    print(f"文件数：{result['files']}  schema_version={result['schema_version']}")
    if result["schema_version"] == 0:
        print("提示：数据库没有 schema_version 记录（可能是空库或首次启动前）")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
