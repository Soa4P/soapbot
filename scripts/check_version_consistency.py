#!/usr/bin/env python3
"""Fail when the files that spell the product version disagree.

The version is written in six places that no build tool reconciles: ``pyproject.toml``,
``src/soapbot/__init__.py``, ``webui/package.json``, ``desktop/package.json``,
``desktop/src-tauri/tauri.conf.json`` and ``desktop/src-tauri/Cargo.toml``. A release
that bumps five of them ships a wheel reporting one version, a panel reporting another,
and a desktop shell reporting a third — which stays invisible until someone files a bug
against the wrong number.

Runtime code is not allowed to restate the version at all: it imports ``__version__``.
A literal in a module is precisely how two copies start to drift.
"""

from __future__ import annotations

import json
import re
import sys
import tomllib
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
INIT = ROOT / "src" / "soapbot" / "__init__.py"
_VERSION_LINE = re.compile(r'^__version__\s*=\s*"([^"]+)"', re.M)


def _toml(path: Path) -> dict:
    with path.open("rb") as handle:
        return tomllib.load(handle)


def _json(path: Path) -> dict:
    return json.loads(path.read_text(encoding="utf-8"))


def sources() -> dict[str, str]:
    """Every file that declares the product version, in review order."""
    match = _VERSION_LINE.search(INIT.read_text(encoding="utf-8"))
    return {
        "pyproject.toml": _toml(ROOT / "pyproject.toml")["project"]["version"],
        "src/soapbot/__init__.py": match.group(1) if match else "<missing>",
        "webui/package.json": _json(ROOT / "webui" / "package.json")["version"],
        "desktop/package.json": _json(ROOT / "desktop" / "package.json")["version"],
        "desktop/src-tauri/tauri.conf.json": _json(
            ROOT / "desktop" / "src-tauri" / "tauri.conf.json"
        )["version"],
        "desktop/src-tauri/Cargo.toml": _toml(ROOT / "desktop" / "src-tauri" / "Cargo.toml")[
            "package"
        ]["version"],
    }


def hardcoded(version: str) -> list[str]:
    """Runtime modules that restate the version instead of importing it.

    Only quoted literals count. A version mentioned in prose is documentation, and
    flagging it would make the gate noisy enough to be disabled.
    """
    offenders: list[str] = []
    literal = f'"{version}"'
    for path in sorted((ROOT / "src" / "soapbot").rglob("*.py")):
        if path == INIT:
            continue
        for number, line in enumerate(path.read_text(encoding="utf-8").splitlines(), 1):
            if literal in line and "__version__" not in line:
                offenders.append(f"{path.relative_to(ROOT).as_posix()}:{number}")
    return offenders


def main() -> int:
    found = sources()
    values = set(found.values())
    if len(values) != 1:
        print("版本号不一致：", file=sys.stderr)
        for name, value in found.items():
            print(f"  {name}: {value}", file=sys.stderr)
        return 1

    version = values.pop()
    if version == "<missing>":
        print("src/soapbot/__init__.py 里没有 __version__", file=sys.stderr)
        return 1

    offenders = hardcoded(version)
    if offenders:
        print(
            f"运行时代码硬编码了版本 {version}，应改为 `from soapbot import __version__`：",
            file=sys.stderr,
        )
        for item in offenders:
            print(f"  {item}", file=sys.stderr)
        return 1

    print(f"版本一致：{version}（{len(found)} 个声明点，0 处运行时硬编码）")
    return 0


if __name__ == "__main__":
    sys.exit(main())
