"""The type-check ratchet's *current* description must match how it is wired.

Why this exists
---------------
``check_mypy_baseline.py`` became a blocking gate in ``make check`` and in two CI
jobs, and its baseline moved from 79 to 80 because CI reports one more error than
a cold local run. The prose did not follow: ``deployment.md`` still described an
advisory ``types`` job with ``continue-on-error``, ``CONTRIBUTING.md`` called it
"not a blocking gate" at baseline 79, the ``operations.md`` gate list omitted it,
and ``verification-matrix.md`` told readers to run ``python -m mypy src``. Worst
of all, ``ci.yml`` carried a comment saying mypy is "deliberately *not* a gate
here" immediately below the step that makes it one.

``tests/test_gate_parity.py`` compares the Makefile against CI. It cannot see a
sentence. This module pins the sentences, the baseline value and the wiring
together: changing the baseline or moving the gate has to update the docs too.

History is deliberately out of scope. CHANGELOG.md, the ph32 note in
progress.json and the "Why this exists" docstring in the gate itself describe the
day the ratchet was introduced, and stay as written.
"""

from __future__ import annotations

import re
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]

#: Documents a reader treats as "what is true today".
CURRENT_DOCS = (
    "docs/deployment.md",
    "CONTRIBUTING.md",
    "docs/verification-matrix.md",
    "docs/operations.md",
)

#: Phrases that describe the *old* arrangement. Each was a claim about today, not
#: a dated round report, which is why none of them belongs in a current-state doc.
STALE_PHRASES = (
    "continue-on-error",
    "只报告不阻断",
    "尚未作为阻断项",
    "基线 79",
    "79 个错误，分布在 31 个文件",
)

ALL_FILES = (
    *CURRENT_DOCS,
    "Makefile",
    ".github/workflows/ci.yml",
    "scripts/mypy_baseline.txt",
)


def baseline(root: Path) -> int:
    """Read the number the gate itself uses, so the docs cannot invent one."""
    for line in (root / "scripts" / "mypy_baseline.txt").read_text(
        encoding="utf-8"
    ).splitlines():
        stripped = line.strip()
        if stripped and not stripped.startswith("#"):
            return int(stripped)
    raise AssertionError("mypy_baseline.txt 里没有数字")


def problems(root: Path) -> list[str]:
    """Return every way the current-state description disagrees with the wiring."""
    try:
        value = baseline(root)
    except (OSError, ValueError, AssertionError) as exc:
        return [f"读不到基线：{exc}"]
    out: list[str] = []

    for relative in CURRENT_DOCS:
        path = root / relative
        if not path.is_file():
            out.append(f"{relative} 不存在")
            continue
        text = path.read_text(encoding="utf-8")
        for phrase in STALE_PHRASES:
            if phrase in text:
                out.append(f"{relative} 还写着过时描述：{phrase}")
        if "check_mypy_baseline.py" not in text:
            out.append(f"{relative} 没写出真正跑的门禁脚本")
        if f"基线 {value}" not in text and f"取 {value}" not in text:
            out.append(f"{relative} 没有写出当前基线 {value}")

    makefile = root / "Makefile"
    if makefile.is_file():
        body = makefile.read_text(encoding="utf-8")
        check_line = next(
            (line for line in body.splitlines() if line.startswith("check:")), ""
        )
        if "mypy-baseline" not in check_line:
            out.append("Makefile 的 check 没有包含 mypy-baseline")
        if re.search(r"prints \d+ errors", body):
            out.append("Makefile 注释还钉着具体错误数")
    else:
        out.append("Makefile 不存在")

    ci = root / ".github" / "workflows" / "ci.yml"
    if ci.is_file():
        body = ci.read_text(encoding="utf-8")
        if body.count("python scripts/check_mypy_baseline.py") < 2:
            out.append("CI 里跑棘轮脚本的 job 少于两个")
        if "mypy is deliberately *not* a gate" in body:
            out.append("CI 注释还声称 mypy 不是门禁")
    else:
        out.append("ci.yml 不存在")
    return out


def _copy(root: Path) -> None:
    for relative in ALL_FILES:
        source = ROOT / relative
        target = root / relative
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_text(source.read_text(encoding="utf-8"), encoding="utf-8")


def test_current_descriptions_match_the_wiring() -> None:
    assert problems(ROOT) == []


@pytest.mark.parametrize(
    ("relative", "old", "new", "expected"),
    [
        ("scripts/mypy_baseline.txt", "\n80\n", "\n81\n", "没有写出当前基线 81"),
        ("docs/deployment.md", "check_mypy_baseline.py", "", "没写出真正跑的门禁脚本"),
        ("Makefile", " mypy-baseline test", " test", "check 没有包含"),
        (
            ".github/workflows/ci.yml",
            "python scripts/check_mypy_baseline.py",
            "",
            "job 少于两个",
        ),
        ("CONTRIBUTING.md", "基线 80", "基线 79", "还写着过时描述：基线 79"),
        (
            "docs/deployment.md",
            "**类型检查现状**",
            "**类型检查现状**（continue-on-error）",
            "还写着过时描述：continue-on-error",
        ),
        (
            ".github/workflows/ci.yml",
            "      - name: Test",
            "      # mypy is deliberately *not* a gate here.\n      - name: Test",
            "CI 注释还声称 mypy 不是门禁",
        ),
    ],
)
def test_one_regression_is_enough_to_fail(
    tmp_path: Path, relative: str, old: str, new: str, expected: str
) -> None:
    """Each individual regression is caught, not just an empty tree."""
    _copy(tmp_path)
    path = tmp_path / relative
    text = path.read_text(encoding="utf-8")
    assert old in text, "反向用例自身失去了意义"
    path.write_text(text.replace(old, new, 1), encoding="utf-8")
    found = problems(tmp_path)
    assert any(expected in problem for problem in found), (relative, expected, found)
