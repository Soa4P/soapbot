"""Restore a backup produced by ``scripts/backup.py``.

Order of operations matters and is the whole point of this script:

1. Read and validate ``manifest.json`` **before** touching the target. A backup made
   by a newer version can contain a schema this build cannot read; restoring it and
   starting the service would migrate-or-crash against real data, which is the one
   moment you cannot afford to improvise.
2. Verify every file against the sha256 in the manifest. A zip's own CRC catches a
   flipped bit; it does not catch a file that was replaced with a different valid one.
3. Refuse entries that resolve outside the target directory. A backup is a file that
   arrives from somewhere else, and zip entries are attacker-influenced input exactly
   like an uploaded plugin package.
4. Extract into a staging directory and prove the database opens — ``PRAGMA
   integrity_check``, not just "the bytes are there". Only then replace anything.
   A restore that writes half an archive over a working install is worse than a
   failed restore: the install was working.
5. Move the current database aside rather than overwriting it, so a restore that
   turns out to be the wrong backup is reversible with one rename.

The same file is what the Docker deployment runs (``deploy/backup.sh`` writes with
``backup.py``, ``deploy/restore.sh`` reads with this script, both inside the app
image). One format, one implementation — the timer used to produce a ``tar.gz`` that
this script could not read.
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
from pathlib import Path, PurePosixPath

ROOT = Path(__file__).resolve().parent.parent


class RestoreError(RuntimeError):
    pass


#: Files that sit beside the database and must come back with it. ``secret.key`` is the
#: one that matters: every ``enc:`` value inside soapbot.db was encrypted with it, so
#: restoring the database alone yields a file that opens and cannot be read.
_DATA_SIBLINGS = {("data", "secret.key"), ("data", "jwt.key"), ("data", ".env")}


def _read_manifest(archive: zipfile.ZipFile) -> dict:
    try:
        raw = archive.read("manifest.json")
    except KeyError as exc:
        raise RestoreError("归档里没有 manifest.json，可能不是 soapbot 备份") from exc
    try:
        return json.loads(raw.decode("utf-8"))
    except (UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise RestoreError(f"manifest.json 无法解析：{exc}") from exc


def _safe_member(name: str) -> PurePosixPath:
    path = PurePosixPath(name.replace("\\", "/"))
    if path.is_absolute() or any(part == ".." for part in path.parts):
        raise RestoreError(f"归档内路径越界：{name}")
    return path


def _verify_checksums(archive: zipfile.ZipFile, manifest: dict) -> bool:
    """Return True when the archive carried hashes and they all matched.

    A v1 archive has no ``checksums`` key. It still restores — refusing outright would
    strand every existing backup — but the caller says so out loud, because "we verify
    before restoring" must not quietly mean "we verify when the file happens to say so".
    """
    expected = manifest.get("checksums")
    if not expected:
        return False

    for name, digest in expected.items():
        try:
            body = archive.read(name)
        except KeyError as exc:
            raise RestoreError(f"归档缺少清单里列出的文件：{name}") from exc
        actual = hashlib.sha256(body).hexdigest()
        if actual != digest:
            raise RestoreError(
                f"文件校验失败：{name} 的内容与清单不一致（备份被修改或损坏）"
            )
    return True


def _assert_sqlite_ok(path: Path) -> None:
    """Prove the staged database opens and is internally consistent.

    ``backup.py`` snapshots with the SQLite backup API precisely so the archive holds a
    consistent database; this check is the other half of that promise. A truncated or
    hand-edited file passes every byte-level test and only fails at startup, after the
    working database has already been moved aside.
    """
    conn = None
    try:
        conn = sqlite3.connect(f"file:{path}?mode=ro", uri=True)
        row = conn.execute("PRAGMA integrity_check").fetchone()
    except sqlite3.Error as exc:
        raise RestoreError(f"备份中的数据库无法打开：{exc}") from exc
    finally:
        if conn is not None:
            conn.close()
    result = row[0] if row else "no result"
    if result != "ok":
        raise RestoreError(f"备份中的数据库完整性检查失败：{result}")


def _install(staged: Path, target: Path) -> None:
    """Copy into place via a sibling temp file, so a rename is the only visible step."""
    target.parent.mkdir(parents=True, exist_ok=True)
    tmp = target.with_name(f".{target.name}.restore-tmp")
    tmp.write_bytes(staged.read_bytes())
    os.replace(tmp, target)


def restore(archive_path: Path, *, data_dir: Path, config_dir: Path, with_config: bool = True) -> dict:
    if not archive_path.is_file():
        raise RestoreError(f"备份文件不存在：{archive_path}")

    restored: list[str] = []
    stamp = time.strftime("%Y%m%d-%H%M%S")

    with zipfile.ZipFile(archive_path) as archive:
        manifest = _read_manifest(archive)

        from soapbot.memory.db import SCHEMA_VERSION

        backup_format = int(manifest.get("format") or 1)
        if backup_format > 2:
            raise RestoreError(
                f"备份格式 version={backup_format} 高于当前程序支持的 2；请先升级程序再恢复"
            )

        backup_version = int(manifest.get("schema_version") or 0)
        if backup_version > SCHEMA_VERSION:
            raise RestoreError(
                f"备份的 schema_version={backup_version} 高于当前程序支持的 "
                f"{SCHEMA_VERSION}；请先升级程序再恢复"
            )

        verified = _verify_checksums(archive, manifest)

        # Everything is unpacked and checked here, before a single byte of the live
        # install is touched. `data_dir` is not even created until the loop succeeds.
        with tempfile.TemporaryDirectory(prefix="soapbot-restore-") as stage_name:
            stage = Path(stage_name)
            plan: list[tuple[Path, Path, bool]] = []  # (staged, target, is_database)

            for name in archive.namelist():
                if name.endswith("/"):
                    continue
                member = _safe_member(name)
                if member.name == "manifest.json":
                    continue

                if member.parts[:2] == ("data", "soapbot.db"):
                    target = data_dir / "soapbot.db"
                    staged = stage / "soapbot.db"
                    is_db = True
                elif member.parts[:2] in _DATA_SIBLINGS:
                    # Allowlist, not `data/*`: the archive decides these names, and an
                    # archive that could write any path under data/ could plant a file
                    # the service later executes.
                    filename = member.parts[1]
                    target = data_dir / filename
                    staged = stage / "data" / filename
                    is_db = False
                elif member.parts[0] == "config" and with_config:
                    target = config_dir.joinpath(*member.parts[1:])
                    staged = stage / "config" / Path(*member.parts[1:])
                    is_db = False
                else:
                    continue

                staged.parent.mkdir(parents=True, exist_ok=True)
                staged.write_bytes(archive.read(name))
                plan.append((staged, target, is_db))

            for staged, _target, is_db in plan:
                if is_db:
                    _assert_sqlite_ok(staged)

            data_dir.mkdir(parents=True, exist_ok=True)
            for staged, target, is_db in plan:
                if is_db and target.exists():
                    # with_name, not with_suffix: the latter *replaces* ".db", so the
                    # previous copy would land next to the database as "soapbot.pre-..."
                    # and nobody would find it.
                    target.replace(target.with_name(f"{target.name}.pre-restore-{stamp}"))
                _install(staged, target)
                if target.name in {"secret.key", "jwt.key", ".env"}:
                    # A restored key must not inherit a permissive mode from an archive
                    # written on a machine with a looser umask.
                    os.chmod(target, 0o600)
                restored.append(str(target))

    return {
        "files": len(restored),
        "schema_version": backup_version,
        "created_at": manifest.get("created_at"),
        "verified": verified,
    }


def main(argv: list[str] | None = None) -> int:
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")

    parser = argparse.ArgumentParser(description="从备份恢复 data/ 与 config/")
    parser.add_argument("archive", help="backup.py 生成的 zip")
    parser.add_argument("--data-dir", default="", help="默认取 SOAPBOT_DATA_DIR")
    parser.add_argument("--config-dir", default="", help="默认取 SOAPBOT_CONFIG_DIR")
    parser.add_argument(
        "--no-config",
        action="store_true",
        help="只恢复数据库，不动配置文件（配置由部署系统管理时使用）",
    )
    args = parser.parse_args(argv)

    data_arg, config_arg = args.data_dir, args.config_dir
    if not data_arg or not config_arg:
        # Same as backup.py: only imported when a directory was not supplied, so this
        # runs inside the app image where there is no checkout and no `.env` to parse.
        from soapbot.config import settings

        data_arg = data_arg or str(settings.data_dir)
        config_arg = config_arg or str(settings.config_dir)

    try:
        result = restore(
            Path(args.archive),
            data_dir=Path(data_arg),
            config_dir=Path(config_arg),
            with_config=not args.no_config,
        )
    except RestoreError as exc:
        print(f"恢复失败：{exc}")
        print("没有替换任何文件；原数据库与配置保持原样。")
        return 1

    print(f"恢复完成：{result['files']} 个文件，schema_version={result['schema_version']}")
    if not result["verified"]:
        print("注意：该备份没有 checksums（旧格式），本次未做逐文件完整性校验。")
    print("原数据库已重命名为 soapbot.db.pre-restore-<时间戳>，确认无误后可删除。")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
