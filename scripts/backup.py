"""Back up the writable state of a running soapbot into one archive.

What is included, and why each one
-----------------------------------
* ``soapbot.db`` — messages, memory, knowledge, budget reservations, approvals.
* ``config/`` — providers, adapters, personas, MCP servers. Configuration lives
  outside ``data/`` precisely so a compromised plugin cannot rewrite it, which also
  means a backup of ``data/`` alone restores a bot that points at whatever config it
  happens to find.
* a manifest — schema version, file list, per-file sha256, read by ``restore.py``
  before it touches anything.

How the database is copied
--------------------------
``sqlite3.Connection.backup`` rather than ``shutil.copy``. The service keeps the
database open in WAL mode, so a plain file copy can capture a database whose -wal
still holds committed pages: it opens cleanly and is silently missing the last
messages. The backup API takes a consistent snapshot while writers continue.

This is the *only* backup implementation. ``deploy/backup.sh`` (the systemd timer)
runs this same file inside the app image against the same volume, because the timer
used to produce a ``tar.gz`` of the live files with no manifest: a different format,
a different restore entry point, and the WAL problem above. "Two backup scripts that
agree today" is a bug waiting for the first schema change.

The archive is written to a temporary file and renamed at the end, so a backup that
fails halfway does not leave something that looks like a backup.

This module imports only the standard library. It has to run where the app image has
no repository checkout — ``--data-dir``/``--config-dir`` are explicit, and only the
defaults come from ``soapbot.config``.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import sqlite3
import sys
import tempfile
import time
import zipfile
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent

#: Bumped when a reader could get the manifest wrong. ``restore.py`` refuses an archive
#: from the future rather than guessing what a missing key means.
ARCHIVE_FORMAT = 2


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


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1 << 20), b""):
            digest.update(chunk)
    return digest.hexdigest()


def build(data_dir: Path, config_dir: Path, out_path: Path) -> dict:
    tmp_fd, tmp_name = tempfile.mkstemp(suffix=".zip", dir=str(out_path.parent))
    os.close(tmp_fd)
    tmp_path = Path(tmp_name)

    files: list[str] = []
    checksums: dict[str, str] = {}
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
                    # Hashed from the snapshot, not the live file: the live file keeps
                    # changing, so hashing it would certify bytes that are not in the
                    # archive.
                    checksums["data/soapbot.db"] = _sha256(snapshot)
                finally:
                    snapshot.unlink(missing_ok=True)

            # Key material and .env travel with the database, because a database alone
            # is not a restore. Every `enc:` value in soapbot.db is encrypted with
            # data/secret.key; restore the DB without the key and those values are
            # permanently unreadable — the archive looks complete and the damage only
            # appears when a plugin asks for its token. Same for .env, which is where
            # the master key reference and the panel's saved settings live.
            #
            # This makes the archive itself a secret: build() tightens the file mode
            # below, and backup.sh writes it 0600.
            for name in ("secret.key", "jwt.key", ".env"):
                source = data_dir / name
                if not source.is_file():
                    continue
                arcname = f"data/{name}"
                body = source.read_bytes()
                archive.writestr(arcname, body)
                files.append(arcname)
                checksums[arcname] = hashlib.sha256(body).hexdigest()

            for path in sorted(config_dir.rglob("*")):
                if not path.is_file() or path.name.startswith("."):
                    continue
                arcname = f"config/{path.relative_to(config_dir).as_posix()}"
                body = path.read_bytes()
                archive.writestr(arcname, body)
                files.append(arcname)
                checksums[arcname] = hashlib.sha256(body).hexdigest()

            manifest = {
                "tool": "soapbot-backup",
                "format": ARCHIVE_FORMAT,
                "created_at": time.time(),
                "schema_version": schema_version,
                "files": files,
                # Why hashes in a backup: a zip's own CRC only catches corruption, not
                # substitution. Restore is the moment a wrong file becomes the running
                # configuration, so the manifest has to be able to name what it expects.
                "checksums": checksums,
            }
            archive.writestr("manifest.json", json.dumps(manifest, indent=2))

        # The archive now carries key material (see above), so it is not a normal file.
        # mkstemp already created it 0600; the explicit chmod survives a umask that
        # would otherwise widen it, and it is applied before the file has a useful name.
        os.chmod(tmp_path, 0o600)
        tmp_path.replace(out_path)
    except BaseException:
        tmp_path.unlink(missing_ok=True)
        raise

    return {"path": str(out_path), "files": len(files), "schema_version": schema_version}


def main(argv: list[str] | None = None) -> int:
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")

    parser = argparse.ArgumentParser(description="备份 data/ 与 config/ 到一个 zip")
    parser.add_argument(
        "--out",
        default="",
        help="输出文件（默认 soapbot-backup-<时间戳>.zip）",
    )
    parser.add_argument("--data-dir", default="", help="默认取 SOAPBOT_DATA_DIR")
    parser.add_argument("--config-dir", default="", help="默认取 SOAPBOT_CONFIG_DIR")
    args = parser.parse_args(argv)

    data_arg, config_arg = args.data_dir, args.config_dir
    if not data_arg or not config_arg:
        # Only reached when a directory was not given. The timer always passes both,
        # which is what lets this file run inside the app image where the repository
        # (and its settings) is not present.
        from soapbot.config import settings

        data_arg = data_arg or str(settings.data_dir)
        config_arg = config_arg or str(settings.config_dir)

    data_dir = Path(data_arg)
    config_dir = Path(config_arg)
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
