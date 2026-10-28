#!/usr/bin/env python
"""Fail if ``requirements.txt`` and ``pyproject.toml`` describe different runtime sets.

Two files listing the same dependencies is a standing invitation to drift. The
failure is quiet and late: `pip install -r requirements.txt` succeeds, the service
starts, and behaves differently from the wheel CI built — usually because one file
gained a pin the other did not.

Scope is deliberately the *runtime* set only. Dev and optional dependencies live in
pyproject alone; comparing them would force requirements.txt to carry test tooling
that a deployment should not install.
"""

from __future__ import annotations

import re
import sys
import tomllib
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
_NAME_RE = re.compile(r"^([A-Za-z0-9_.\-]+)")


def _name(spec: str) -> str:
    match = _NAME_RE.match(spec.strip())
    if not match:
        raise ValueError(f"cannot parse requirement: {spec!r}")
    return match.group(1).lower().replace("_", "-")


def _versions(specs: list[str]) -> dict[str, str]:
    out: dict[str, str] = {}
    for spec in specs:
        name = _name(spec)
        _, _, pin = spec.partition("==")
        out[name] = pin.strip() if pin else ""
    return out


def main() -> int:
    pyproject = tomllib.loads((ROOT / "pyproject.toml").read_text(encoding="utf-8"))
    declared = pyproject["project"]["dependencies"]

    lines = (ROOT / "requirements.txt").read_text(encoding="utf-8").splitlines()
    flat = [line.strip() for line in lines if line.strip() and not line.strip().startswith("#")]

    expected = _versions(declared)
    actual = _versions(flat)

    problems: list[str] = []
    for name in sorted(expected.keys() - actual.keys()):
        problems.append(f"requirements.txt 缺少 {name}（pyproject 中有）")
    for name in sorted(actual.keys() - expected.keys()):
        problems.append(f"requirements.txt 多出 {name}（pyproject 中没有）")
    for name in sorted(expected.keys() & actual.keys()):
        if expected[name] != actual[name]:
            problems.append(
                f"{name} 版本不一致：pyproject={expected[name] or '未固定'} "
                f"requirements={actual[name] or '未固定'}"
            )

    if problems:
        print("依赖清单不一致：", file=sys.stderr)
        for problem in problems:
            print(f"  - {problem}", file=sys.stderr)
        return 1

    print(f"依赖清单一致：{len(expected)} 个运行时依赖")
    return 0


if __name__ == "__main__":
    sys.exit(main())
