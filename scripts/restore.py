#!/usr/bin/env python3
"""Deployment entry point — a shim over ``soapbot.backup``.

``deploy/restore.sh`` runs this inside the app image with ``--data-dir/--config-dir``
and reads its exit code plus its two-line summary. The verification order that makes
this safe (manifest → per-file digests → staging → ``PRAGMA integrity_check`` → move
the old database aside) lives in ``soapbot.backup.restore_backup``; this file only
maps arguments and prints the operator-facing result (audit S-DEP-12).

``--no-config`` is kept because the deployment documents it: when configuration is
managed outside the volume, restoring it would overwrite the deploy system's files.
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from soapbot.backup import BackupError, restore_backup

#: Re-exported for callers that catch this module's own error name.
__all__ = ["BackupError", "RestoreError", "main", "restore"]

#: The pre-convergence name. Callers (and tests) catch ``RestoreError``; mapping it to
#: the package's type keeps one exception vocabulary for one operation.
RestoreError = BackupError


def restore(
    archive: Path,
    *,
    data_dir: Path,
    config_dir: Path,
    with_config: bool = True,
) -> dict:
    """Compatibility wrapper: the pre-convergence entry point, same arguments.

    Returns the old report shape (``files``/``schema_version``/``verified``), which is a
    subset of what the package returns — the extra keys are additive.
    """
    report = restore_backup(
        Path(archive),
        Path(data_dir),
        config_dir=Path(config_dir),
        with_config=with_config,
    )
    return {
        "files": report["files"],
        "schema_version": report["schema_version"],
        "verified": report["verified"],
        "created_at": None,
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
        result = restore_backup(
            Path(args.archive),
            Path(data_arg),
            config_dir=Path(config_arg),
            with_config=not args.no_config,
        )
    except BackupError as exc:
        print(f"恢复失败：{exc}")
        print("没有替换任何文件；原数据库与配置保持原样。")
        return 1

    print(f"恢复完成：{result['files']} 个文件，schema_version={result['schema_version']}")
    if not result.get("verified", False):
        print("注意：本次未做逐文件完整性校验。")
    print("原数据库已重命名为 soapbot.db.pre-restore-<时间戳>，确认无误后可删除。")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
