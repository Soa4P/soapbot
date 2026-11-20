#!/usr/bin/env python
"""Fail when a relative link in the docs points at nothing.

Splitting `README.md` into `docs/*.md` moved a link from the repository root into a
subdirectory, so `](scripts/foo.ps1)` quietly became a dead end. Nothing caught it —
a broken link looks exactly like a working one until someone clicks it.

Only relative targets are checked; external URLs are somebody else's uptime.
"""

from __future__ import annotations

import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
LINK = re.compile(r"\[[^\]]*\]\(([^)]+)\)")
SKIP_PREFIXES = ("http://", "https://", "mailto:", "#")

#: 数据快照不是手写文档：逐插件目录的表格单元格是 3483 条**第三方描述**原文，
#: 里面的 markdown 形状文本会被当成链接目标去解析（长文件名 Errno 36）。
#: 与 JSON 同等对待——数据文件不进链接门禁。
DATA_SNAPSHOTS = {"reference-batch12b-plugin-catalogue.md"}


def documents() -> list[Path]:
    found = [ROOT / "README.md", ROOT / "SECURITY.md"]
    found.extend(sorted((ROOT / "docs").glob("*.md")))
    return [path for path in found
            if path.is_file() and path.name not in DATA_SNAPSHOTS]


def main() -> int:
    broken: list[str] = []
    checked = 0
    for path in documents():
        text = path.read_text(encoding="utf-8")
        for match in LINK.finditer(text):
            link = match.group(1).strip()
            if link.startswith(SKIP_PREFIXES):
                continue
            target_part = link.split("#")[0]
            if not target_part:
                continue
            checked += 1
            if not (path.parent / target_part).resolve().exists():
                broken.append(f"{path.relative_to(ROOT)}: {link}")

    if broken:
        print(f"{len(broken)} broken relative link(s):")
        for item in broken:
            print(f"  - {item}")
        return 1
    print(f"doc links ok: {checked} relative link(s) in {len(documents())} file(s)")
    return 0


if __name__ == "__main__":
    sys.exit(main())
