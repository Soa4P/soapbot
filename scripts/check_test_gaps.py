"""The gap between "there is code" and "there is a test that knows it exists".

Why not coverage
----------------
``coverage`` is not installed, and adding it would break the rule that requirements are
an audit surface (``scripts/check_deps.py``). So none of the rules below runs the suite.

What this finds is not "uncovered lines". It is the shape of the bug that motivated the
file: ``MessageTrace.extras`` was declared in TypeScript, never serialised by
``to_dict``, read by the page — and every test passed. Nothing was uncovered. A field
simply had a reader and no writer, and no test ever named the module on both sides.

Three rules, all cheap and all checkable:

1. **Orphan modules** — a file under ``src/soapbot`` that no test names anywhere. Not
   proof it is untested (a test may reach it through a higher-level import), but every
   entry is a place where "nobody looked" is the default.
2. **Stale totals in prose** — a "N passed" / "N skipped" in a *live* document that
   disagrees with ``docs/progress/progress.json``. It cannot know the true number without
   running the suite, so it enforces the weaker but checkable property: the number a new
   reader sees matches the board, and the board is separately dated by
   ``tests/test_progress_board.py``. Both halves are checked: a line that updates its
   total but leaves an old skipped count is still telling a reader something false.

   Scope matters. A round report ("那一轮 435 passed") is a record of a day, and pinning
   every record to today's count would forbid writing history. Only documents that are
   read as *the current state* are checked; the list is explicit rather than inferred.

   A *line inside* one of those documents can still be history: the verification matrix
   records each round's delta as "1884 → 1892 passed / 12 skipped". Pinning that to
   today's board made every earlier round go red the moment a test was added, which is
   the same "forbid writing history" failure one level down. ``ROUND_CHANGE`` exempts
   only that narrow "old → new passed" shape; a bare "1902 passed, 12 skipped" and a
   benchmark ("39.7ms → 19.6ms") are still checked. ``round_report_lines`` reports what
   matched so the exemption cannot quietly stop matching.
3. **Stale orphan count in prose** — ``docs/verification-matrix.md`` describes this very
   gate as "孤儿模块基线（N 个）". That number is a claim about today, and it went from 19
   to 16 to 10 while the prose kept quoting an older one. Rule 1 already computes the
   truth, so the only work is reading the number back and comparing.

   Still no suite run: the count comes from the same textual scan as rule 1.

Usage::

    python scripts/check_test_gaps.py                 # report only
    python scripts/check_test_gaps.py --strict        # exit 1 when a rule finds drift
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
#: The skipped count travels with the total on the same line. Checking only the total
#: left `architecture.md` free to keep saying "10 项跳过" after the suite reached 12 —
#: half of a stale sentence is still a stale sentence.
SKIPPED = re.compile(r"(\d+)\s+(?:skipped|项跳过)")

#: A line recording one round's change ("全量 1884 → 1892 passed / 12 skipped") is
#: history, not a claim about today. Narrow on purpose: both sides must be integers
#: and the arrow must be followed by ``passed`` / ``项通过``. A current-state line
#: ("1902 passed, 12 skipped") has no arrow, and a benchmark ("39.7ms → 19.6ms")
#: has units on both sides, so neither is exempted.
ROUND_CHANGE = re.compile(r"\d+\s*→\s*\d+\s+(?:passed|项通过)")

#: Documents a newcomer reads as "what is true today". Everything else under ``docs/``
#: is a snapshot of a round and keeps its own numbers.
#:
#: The delivery readiness report is included because its "未验证项" list and its header
#: both read as the current state — it was quoting 886 and 959 passed while the suite ran
#: 1024, and it still claimed the real MCP server had never been connected.
#:
#: ``architecture.md`` is here for the same reason and is the one this rule missed for
#: several rounds: its directory tree ends with a line describing the *current* suite,
#: and that line sat at "1290 项通过 / 10 项跳过" while the suite ran 1791/12. It is a map
#: of this repository, not a report of one round, so its number has to be today's.
LIVE_DOCUMENTS = (
    "README.md",
    "docs/verification-matrix.md",
    "docs/delivery-readiness-v2.md",
    "docs/architecture.md",
)

#: What this rule can and cannot do: it pins *numbers*. A prose claim like "the real
#: server was never connected" is invisible to it, so the list above is where the
#: coverage stops. Pretending otherwise would be worse than the gap.

#: The document that describes this gate, and the sentence in it that quotes the orphan
#: count. Kept as one pattern rather than a bare number so the reader can see which claim
#: is being pinned; if the sentence is rewritten, the rule fails loudly instead of
#: silently checking nothing.
ORPHAN_COUNT_CLAIM = re.compile(r"孤儿模块基线（(\d+) 个）")
ORPHAN_COUNT_DOCUMENT = ROOT / "docs" / "verification-matrix.md"

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


def stale_totals(root: Path = ROOT) -> list[str]:
    """Documents whose "N passed" disagrees with the board's recorded total.

    ``root`` is injectable so the round-report exemption can be tested against a
    synthetic tree; production and CI calls use the repository root. Paths in the
    messages are the relative strings, not ``Path.relative_to``: under ``tmp_path``
    that call would raise instead of reporting a problem.
    """
    board_relative = "docs/progress/progress.json"
    board_path = root / board_relative
    try:
        board = json.loads(board_path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        return [f"{board_relative} 读不出来：{exc}"]

    recorded = str(board.get("verification", {}).get("pytest", ""))
    match = PASSED.search(recorded)
    if not match:
        return [f"{board_relative} 的 verification.pytest 里没有总数：{recorded!r}"]

    expected = match.group(1)
    skipped = SKIPPED.search(recorded)
    if not skipped:
        return [f"{board_relative} 的 verification.pytest 里没有跳过数：{recorded!r}"]
    expected_skipped = skipped.group(1)
    problems: list[str] = []
    for relative in LIVE_DOCUMENTS:
        path = root / relative
        if not path.is_file():
            continue
        for lineno, line in enumerate(
            path.read_text(encoding="utf-8", errors="replace").splitlines(), 1
        ):
            if ROUND_CHANGE.search(line):
                continue
            found = PASSED.search(line)
            if found and found.group(1) != expected:
                problems.append(
                    f"{relative}:{lineno} 写着 {found.group(1)} passed，看板是 {expected}"
                )
            found_skipped = SKIPPED.search(line)
            if found_skipped and found_skipped.group(1) != expected_skipped:
                problems.append(
                    f"{relative}:{lineno} 写着 {found_skipped.group(1)} skipped，"
                    f"看板是 {expected_skipped}"
                )
    return problems


def round_report_lines(root: Path = ROOT) -> list[str]:
    """``file:line`` for every line exempted as a past round's result.

    Returned rather than merely counted so a reviewer (and the test) can see exactly
    what the exemption covered. A rule that quietly matches nothing is indistinguishable
    from a rule that passes, which is why the test asserts a lower bound on real files.
    """
    found: list[str] = []
    for relative in LIVE_DOCUMENTS:
        path = root / relative
        if not path.is_file():
            continue
        for lineno, line in enumerate(
            path.read_text(encoding="utf-8", errors="replace").splitlines(), 1
        ):
            if ROUND_CHANGE.search(line):
                found.append(f"{relative}:{lineno}")
    return found


def stale_orphan_count(orphans: list[str]) -> list[str]:
    """The document's quoted orphan count must equal the one just computed.

    Fails when the sentence disappears too: a rule that quietly stops matching is
    indistinguishable from a rule that passes, and this one exists precisely because the
    number drifted unnoticed for several rounds.
    """
    if not ORPHAN_COUNT_DOCUMENT.is_file():
        return [f"{ORPHAN_COUNT_DOCUMENT.relative_to(ROOT)} 不存在"]
    text = ORPHAN_COUNT_DOCUMENT.read_text(encoding="utf-8", errors="replace")
    match = ORPHAN_COUNT_CLAIM.search(text)
    if not match:
        return [
            f"{ORPHAN_COUNT_DOCUMENT.relative_to(ROOT)} 里找不到「孤儿模块基线（N 个）」，"
            "这条规则正在空转"
        ]
    quoted = int(match.group(1))
    if quoted != len(orphans):
        return [
            f"{ORPHAN_COUNT_DOCUMENT.relative_to(ROOT)} 写着孤儿基线 {quoted} 个，"
            f"实际是 {len(orphans)} 个"
        ]
    return []


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
    rounds = round_report_lines()
    counts = stale_orphan_count(orphans)

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

    print(f"\n识别为轮次记录、不按今天看板校验的行：{len(rounds)}")
    for item in rounds:
        print("  -", item)

    if counts:
        print(f"\n文档里的孤儿数与实际不一致：{len(counts)}")
        for item in counts:
            print("  -", item)
    else:
        print("文档里的孤儿数与实际一致。")

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

    if totals or counts or added or removed or not baseline:
        print("\n严格模式下不合格：请补测试、更新基线，或修正文档数字。")
        return 1
    print("\n严格模式通过。")
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
