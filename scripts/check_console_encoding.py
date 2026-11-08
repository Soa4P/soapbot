#!/usr/bin/env python3
"""Fail a script that prints Chinese without forcing UTF-8 first.

This has now cost two red builds. `verify_restart.py --help` died with
`UnicodeEncodeError: 'charmap' codec can't encode characters` because `argparse` writes
straight to a cp1252 stdout; `check_version_consistency.py` died the same way on the same
runner one commit later. Both scripts are fine on the maintainer's UTF-8 machine and on
ubuntu, so the only place the bug shows up is the Windows matrix — after a full CI cycle.

The rule is mechanical: if a script can print a string containing CJK characters, it must
call `reconfigure(encoding="utf-8")` on its streams somewhere. Docstrings and comments are
excluded, because neither reaches stdout.

Usage: python scripts/check_console_encoding.py
"""

from __future__ import annotations

import ast
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SCRIPT_DIR = ROOT / "scripts"


def has_cjk(text: str) -> bool:
    return any("\u4e00" <= char <= "\u9fff" for char in text)


def _docstring_nodes(tree: ast.AST) -> set[int]:
    """Identities of string constants used as docstrings, which never reach stdout."""
    found: set[int] = set()
    for node in ast.walk(tree):
        if not isinstance(node, ast.Module | ast.FunctionDef | ast.AsyncFunctionDef | ast.ClassDef):
            continue
        body = getattr(node, "body", [])
        if (
            body
            and isinstance(body[0], ast.Expr)
            and isinstance(body[0].value, ast.Constant)
            and isinstance(body[0].value.value, str)
        ):
            found.add(id(body[0].value))
    return found


def printing_strings(tree: ast.AST) -> list[str]:
    """String constants that are not docstrings — the ones that can be printed."""
    skip = _docstring_nodes(tree)
    result: list[str] = []
    for node in ast.walk(tree):
        if isinstance(node, ast.Constant) and isinstance(node.value, str) and id(node) not in skip:
            result.append(node.value)
    return result


def main() -> int:
    for stream in (sys.stdout, sys.stderr):
        if hasattr(stream, "reconfigure"):
            stream.reconfigure(encoding="utf-8", errors="replace")

    # `--dir` exists so the test can point the gate at a temporary directory; argparse
    # is avoided on purpose, because its help text is the codec hazard this file guards.
    target = SCRIPT_DIR
    if "--dir" in sys.argv:
        index = sys.argv.index("--dir")
        if index + 1 >= len(sys.argv):
            print("--dir 需要参数", file=sys.stderr)
            return 2
        target = Path(sys.argv[index + 1])
    if not target.is_dir():
        print(f"目录不存在：{target}", file=sys.stderr)
        return 2

    problems: list[str] = []
    checked = 0
    for path in sorted(target.glob("*.py")):
        checked += 1
        source = path.read_text(encoding="utf-8", errors="replace")
        try:
            tree = ast.parse(source)
        except SyntaxError as exc:
            problems.append(f"{path.name}: 无法解析（{exc.msg}）")
            continue
        if "reconfigure" in source:
            continue
        chinese = [text for text in printing_strings(tree) if has_cjk(text)]
        if chinese:
            sample = chinese[0].replace("\n", " ")[:40]
            problems.append(
                f"{path.name}: 会打印中文但没有 reconfigure(encoding=\"utf-8\")，"
                f"Windows 控制台会 UnicodeEncodeError（例：{sample!r}）"
            )

    for problem in problems:
        print(f"[FAIL] {problem}")
    if problems:
        print(f"\n{len(problems)} 个脚本在 cp1252 控制台上会崩")
        return 1
    print(f"\n{checked} 个脚本的输出编码安全")
    return 0


if __name__ == "__main__":
    sys.exit(main())
