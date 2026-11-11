"""The committed panel build is an artifact, so its integrity is checkable.

CI already verifies the wheel contains a self-consistent panel. These cases run that
same idea locally, in pytest, where a broken rebuild is caught before it is committed:
a dangling asset reference, a truncated bundle, or an encoding-damaged title.

The last one is here because a console once displayed ``soapbot 鎺у埗鍙?`` and looked
like a corrupted file when it was only a terminal code page. Pinning the exact UTF-8
title keeps those two situations distinguishable.
"""

from __future__ import annotations

import re
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
DIST = ROOT / "src" / "soapbot" / "webui" / "dist"
INDEX = DIST / "index.html"
ASSET = re.compile(r'(?:src|href)="(/assets/[^"]+)"')


def test_index_references_only_existing_assets() -> None:
    html = INDEX.read_text(encoding="utf-8")
    references = ASSET.findall(html)
    assert references, "the built index must reference at least one bundle"
    missing = [ref for ref in references if not (DIST / ref.lstrip("/")).is_file()]
    assert not missing, f"built index points at missing assets: {missing}"


def test_index_title_is_intact_utf8() -> None:
    html = INDEX.read_text(encoding="utf-8")
    assert "<title>soapbot 控制台</title>" in html
    assert "鎺" not in html and "鈥" not in html


def test_no_asset_in_the_build_is_empty() -> None:
    assets = sorted((DIST / "assets").glob("*"))
    assert assets, "a build with no assets is a failed build, not a small one"
    empty = [path.name for path in assets if path.stat().st_size == 0]
    assert not empty, f"zero-byte bundle(s): {empty}"
