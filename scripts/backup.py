#!/usr/bin/env python3
"""Deployment entry point — a shim over ``soapbot.backup``.

Why this file still exists
--------------------------
``deploy/backup.sh`` runs it inside the app image with an explicit
``--data-dir/--config-dir/--out`` command line, and that deployment script is not
something to rewrite for a refactor. The implementation lives in the package
(``soapbot.backup``), which the image has installed, so there is still exactly one
backup code path (audit S-DEP-12).

Behaviour preserved from the pre-convergence version:

* ``--out`` is a **file path** here (the timer names the archive); the CLI's
  ``--out`` is a directory. Retention is the timer's job, so this shim never rotates.
* the archive is the same zip + ``manifest.json`` format the restore path reads.
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from soapbot.backup import ARCHIVE_FORMAT, BackupError, create_backup

#: Re-exported for callers that read the format constant off this module.
__all__ = ["ARCHIVE_FORMAT", "BackupError", "build", "main"]


def build(data_dir: Path, config_dir: Path, out_path: Path) -> dict:
    """Compatibility wrapper: the pre-convergence entry point, same arguments.

    Kept because the ops-readiness suite and operator muscle memory call
    ``build(data, config, out)``; it maps onto the single implementation instead of
    being a second one.
    """
    report = create_backup(
        Path(data_dir), config_dir=Path(config_dir), archive_path=Path(out_path), keep=0
    )
    return {
        "path": str(report.path),
        "files": report.files,
        "schema_version": report.schema_version,
    }


def main(argv: list[str] | None = None) -> int:
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")

    parser = argparse.ArgumentParser(description="备份 data/ 与 config/ 到一个 zip")
    parser.add_argument("--out", default="", help="输出文件（默认 soapbot-backup-<时间戳>.zip）")
    parser.add_argument("--data-dir", default="", help="默认取 SOAPBOT_DATA_DIR")
    parser.add_argument("--config-dir", default="", help="默认取 SOAPBOT_CONFIG_DIR")
    args = parser.parse_args(argv)

    data_arg, config_arg = args.data_dir, args.config_dir
    if not data_arg or not config_arg:
        # Only reached when a directory was not given. The timer always passes both,
        # which is what lets this run inside the app image where there is no checkout.
        from soapbot.config import settings

        data_arg = data_arg or str(settings.data_dir)
        config_arg = config_arg or str(settings.config_dir)

    data_dir = Path(data_arg)
    config_dir = Path(config_arg)
    if not data_dir.is_dir():
        print(f"数据目录不存在：{data_dir}")
        return 2

    try:
        report = create_backup(
            data_dir,
            config_dir=config_dir if config_dir.is_dir() else None,
            archive_path=Path(args.out) if args.out else None,
            keep=0,  # retention belongs to deploy/backup.sh
        )
    except BackupError as exc:
        print(f"备份失败：{exc}")
        return 1

    print(f"备份完成：{report.path}")
    print(f"文件数：{report.files}  schema_version={report.schema_version}")
    if report.schema_version == 0:
        print("提示：数据库没有 schema_version 记录（可能是空库或首次启动前）")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
