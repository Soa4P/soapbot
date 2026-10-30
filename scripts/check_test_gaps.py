"""The gap between "there is code" and "there is a test that knows it exists".

Why not coverage
----------------
``coverage`` is not installed, and adding it would break the rule that requirements are
an audit surface (``scripts/check_deps.py``). So neither rule below runs the suite.

What this finds is not "uncovered lines". It is the shape of the bug that motivated the
file: ``MessageTrace.extras`` was declared in TypeScript, never serialised by
``to_dict``, read by the page — and every test passed. Nothing was uncovered. A field
simply had a reader and no writer, and no test ever named the module on both sides.

Two rules, both cheap and both checkable:

1. **Orphan modules** — a file under ``src/soapbot`` that no test names anywhere. Not
   proof it is untested (a test may reach it through a higher-level import), but every
   entry is a place where "nobody looked" is the default.
2. **Stale totals in prose** — a "N passed" in a *live* document that disagrees with
   ``docs/progress/progress.json``. It cannot know the true number without running the
   suite, so it enforces the weaker but checkable property: the number a new reader sees
   matches the board, and the board is separately dated by ``tests/test_progress_board.py``.

   Scope matters. A round report ("那一轮 435 passed") is a record of a day, and pinning
   every record to today's count would forbid writing history. Only documents that are
   read as *the current state* are checked; the list is explicit rather than inferred.

Usage::

    python scripts/check_test_gaps.py                 # report only
    python scripts/check_test_gaps.py --strict        # exit 1 when the orphan set drifts
    python scripts/check_test_gaps.py --write-baseline  # accept today's orphans
"""

from __future__ import annotations

import json
import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SRC = ROOT / "src" / "soapbot"
TESTS = ROOT / "tests"
BOARD = ROOT / "docs" / "progress" / "progress.json"
BASELINE = Path(__file__).with_name("test_gaps_baseline.txt")

#: Both spellings appear in this repo: `pytest` prints "N passed" and the Chinese prose
#: says "N 项通过". A rule that only knew one of them would have missed the README line
#: that sat at "800 项通过" for several rounds.
PASSED = re.compile(r"(\d+)\s+(?:passed|项通过)")

#: Documents a newcomer reads as "what is true today". Everything else under ``docs/``
#: is a snapshot of a round and keeps its own numbers.
LIVE_DOCUMENTS = ("README.md", "docs/verification-matrix.md")

#: Modules that exist to be executed rather than imported (an entry point, a script), or
#: that only a subprocess can reach. Named here instead of guessed by regex, so the
#: exception is visible and reviewable.
BY_DESIGN_UNREFERENCED = {
    "soapbot.__main__",
}


def modules() -> dict[str, Path]:
    out: dict[str, Path] = {}
    for path in sorted(SRC.rglob("*.py")):
        if path.name == "__init__.py":
            continue
        dotted = ".".join(path.relative_to(ROOT / "src").with_suffix("").parts)
        out[dotted] = path
    return out


def orphan_modules() -> list[str]:
    """Modules whose dotted path appears in no test file.

    Textual on purpose: a test that imports ``soapbot.app`` has not thereby named
    ``soapbot.mcp.client``, and transitive reachability is exactly the thing that looks
    like coverage. Loose in the other direction — a comment that mentions the path
    counts — because a false negative costs a missed hint, a false positive costs
    someone's afternoon.
    """
    text = "\n".join(
        path.read_text(encoding="utf-8", errors="replace") for path in sorted(TESTS.rglob("*.py"))
    )
    return [
        name
        for name in modules()
        if name not in text and name not in BY_DESIGN_UNREFERENCED
    ]


def stale_totals() -> list[str]:
    """Documents whose "N passed" disagrees with the board's recorded total."""
    try:
        board = json.loads(BOARD.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        return [f"{BOARD.relative_to(ROOT)} 读不出来：{exc}"]

    recorded = str(board.get("verification", {}).get("pytest", ""))
    match = PASSED.search(recorded)
    if not match:
        return [f"{BOARD.relative_to(ROOT)} 的 verification.pytest 里没有总数：{recorded!r}"]

    expected = match.group(1)
    problems: list[str] = []
    for relative in LIVE_DOCUMENTS:
        path = ROOT / relative
        if not path.is_file():
            continue
        for lineno, line in enumerate(
            path.read_text(encoding="utf-8", errors="replace").splitlines(), 1
        ):
            found = PASSED.search(line)
            if found and found.group(1) != expected:
                problems.append(
                    f"{path.relative_to(ROOT)}:{lineno} 写着 {found.group(1)} passed，"
                    f"看板是 {expected}"
                )
    return problems


def read_baseline() -> set[str]:
    if not BASELINE.is_file():
        return set()
    entries = set()
    for line in BASELINE.read_text(encoding="utf-8").splitlines():
        line = line.split("#", 1)[0].strip()
        if line:
            entries.add(line)
    return entries


def write_baseline(names: list[str]) -> None:
    body = [
        "# Modules no test names. Shrink this file when a test starts naming one;",
        "# adding a line here means accepting that nobody looks at that module.",
        "",
        *names,
        "",
    ]
    BASELINE.write_text("\n".join(body), encoding="utf-8")


def main(argv: list[str]) -> int:
    # Same reason as every other check_*.py: cp1252 stdout would raise on the first
    # Chinese character, and a gate that dies on its own output looks like a defect in
    # whatever it was checking.
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")

    strict = "--strict" in argv
    orphans = orphan_modules()
    totals = stale_totals()

    if "--write-baseline" in argv:
        write_baseline(orphans)
        print(f"已写入 {BASELINE.relative_to(ROOT)}：{len(orphans)} 个模块")
        return 0

    print(f"未被任何测试引用的模块：{len(orphans)}")
    for name in orphans:
        print("  -", name)

    if totals:
        print(f"\n文档与看板不一致：{len(totals)}")
        for item in totals:
            print("  -", item)
    else:
        print("\n文档里的 pytest 总数与看板一致。")

    baseline = read_baseline()
    added = sorted(set(orphans) - baseline)
    removed = sorted(baseline - set(orphans))

    if added:
        print(f"\n新增孤儿模块（相对基线）：{len(added)}")
        for name in added:
            print("  +", name)
    if removed:
        print(f"\n基线里已经过期的条目（现在有测试引用了）：{len(removed)}")
        for name in removed:
            print("  -", name)
    if not baseline:
        print("\n没有基线文件；先跑 --write-baseline 接受当前清单。")

    if not strict:
        return 0

    if totals or added or removed or not baseline:
        print("\n严格模式下不合格：请补测试、更新基线，或修正文档数字。")
        return 1
    print("\n严格模式通过。")
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
