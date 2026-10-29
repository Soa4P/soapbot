"""Restore a backup produced by ``scripts/backup.py``.

Order of operations matters and is the whole point of this script:

1. Read and validate ``manifest.json`` **before** touching the target. A backup made
   by a newer version can contain a schema this build cannot read; restoring it and
   starting the service would migrate-or-crash against real data, which is the one
   moment you cannot afford to improvise.
2. Refuse entries that resolve outside the target directory. A backup is a file that
   arrives from somewhere else, and zip entries are attacker-influenced input exactly
   like an uploaded plugin package.
3. Move the current database aside rather than overwriting it, so a restore that
   turns out to be the wrong backup is reversible with one rename.
"""

from __future__ import annotations

import argparse
import json
import sys
import time
import zipfile
from pathlib import Path, PurePosixPath

ROOT = Path(__file__).resolve().parent.parent


class RestoreError(RuntimeError):
    pass


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


def restore(archive_path: Path, *, data_dir: Path, config_dir: Path, with_config: bool = True) -> dict:
    if not archive_path.is_file():
        raise RestoreError(f"备份文件不存在：{archive_path}")

    restored: list[str] = []
    stamp = time.strftime("%Y%m%d-%H%M%S")

    with zipfile.ZipFile(archive_path) as archive:
        manifest = _read_manifest(archive)

        from soapbot.memory.db import SCHEMA_VERSION

        backup_version = int(manifest.get("schema_version") or 0)
        if backup_version > SCHEMA_VERSION:
            raise RestoreError(
                f"备份的 schema_version={backup_version} 高于当前程序支持的 "
                f"{SCHEMA_VERSION}；请先升级程序再恢复"
            )

        data_dir.mkdir(parents=True, exist_ok=True)
        for name in archive.namelist():
            if name.endswith("/"):
                continue
            member = _safe_member(name)
            if member.name == "manifest.json":
                continue

            if member.parts[:2] == ("data", "soapbot.db"):
                target = data_dir / "soapbot.db"
                if target.exists():
                    # with_name, not with_suffix: the latter *replaces* ".db", so the
                    # previous copy would land next to the database as "soapbot.pre-..."
                    # and nobody would find it.
                    target.replace(target.with_name(f"{target.name}.pre-restore-{stamp}"))
                target.write_bytes(archive.read(name))
                restored.append(str(target))
            elif member.parts[0] == "config" and with_config:
                target = config_dir.joinpath(*member.parts[1:])
                target.parent.mkdir(parents=True, exist_ok=True)
                target.write_bytes(archive.read(name))
                restored.append(str(target))

    return {
        "files": len(restored),
        "schema_version": backup_version,
        "created_at": manifest.get("created_at"),
    }


def main(argv: list[str] | None = None) -> int:
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")

    from soapbot.config import settings

    parser = argparse.ArgumentParser(description="从备份恢复 data/ 与 config/")
    parser.add_argument("archive", help="backup.py 生成的 zip")
    parser.add_argument("--data-dir", default=str(settings.data_dir))
    parser.add_argument("--config-dir", default=str(settings.config_dir))
    parser.add_argument(
        "--no-config",
        action="store_true",
        help="只恢复数据库，不动配置文件（配置由部署系统管理时使用）",
    )
    args = parser.parse_args(argv)

    try:
        result = restore(
            Path(args.archive),
            data_dir=Path(args.data_dir),
            config_dir=Path(args.config_dir),
            with_config=not args.no_config,
        )
    except RestoreError as exc:
        print(f"恢复失败：{exc}")
        return 1

    print(f"恢复完成：{result['files']} 个文件，schema_version={result['schema_version']}")
    print("原数据库已重命名为 soapbot.db.pre-restore-<时间戳>，确认无误后可删除。")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
