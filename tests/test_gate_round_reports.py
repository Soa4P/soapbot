"""Round reports are history; current-state numbers are not.

Why this exists
---------------
``check_test_gaps.py`` pins "N passed" in live documents to the progress board.
But the verification matrix also records each round's delta, written naturally as
"1884 → 1892 passed / 12 skipped". Once the board moved to 1902 that historical
line went red, and the only available fix was to rewrite the sentence so it no
longer contained a number-looking claim — editing history to satisfy a gate,
which is backwards.

``ROUND_CHANGE`` now exempts only the "old → new passed" shape. These tests pin
both halves: the exemption must work, and it must not swallow a genuine drift or
quietly stop matching anything.
"""

from __future__ import annotations

import importlib.util
import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
GATE_PATH = ROOT / "scripts" / "check_test_gaps.py"

_spec = importlib.util.spec_from_file_location("check_test_gaps", GATE_PATH)
assert _spec is not None and _spec.loader is not None
gate = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(gate)

LIVE = "docs/verification-matrix.md"


def _tree(tmp_path: Path, lines: list[str], *, total: int = 100) -> Path:
    """One live document plus a board; the other live documents simply do not exist."""
    board = tmp_path / "docs" / "progress" / "progress.json"
    board.parent.mkdir(parents=True)
    board.write_text(
        json.dumps({"verification": {"pytest": f"{total} passed, 12 skipped"}}),
        encoding="utf-8",
    )
    doc = tmp_path / LIVE
    doc.parent.mkdir(parents=True, exist_ok=True)
    doc.write_text("\n".join(lines) + "\n", encoding="utf-8")
    return tmp_path


def test_a_round_report_is_not_pinned_to_today(tmp_path: Path) -> None:
    root = _tree(
        tmp_path,
        [
            "全量 90 → 100 passed / 12 skipped",
            "当前基线 100 passed, 12 skipped",
        ],
    )
    assert gate.round_report_lines(root) == [f"{LIVE}:1"]
    assert gate.stale_totals(root) == []


def test_a_current_state_drift_still_fails(tmp_path: Path) -> None:
    """The exemption must not become a blanket pass for the whole document."""
    root = _tree(
        tmp_path,
        [
            "全量 90 → 100 passed / 12 skipped",
            "当前基线 99 passed, 12 skipped",
        ],
    )
    problems = gate.stale_totals(root)
    assert any(f"{LIVE}:2" in problem and "看板是 100" in problem for problem in problems)


def test_a_stale_skipped_count_still_fails(tmp_path: Path) -> None:
    root = _tree(
        tmp_path,
        [
            "全量 90 → 100 passed / 12 skipped",
            "当前基线 100 passed, 11 skipped",
        ],
    )
    problems = gate.stale_totals(root)
    assert any(f"{LIVE}:2" in problem and "skipped" in problem for problem in problems)


def test_a_bare_old_number_without_an_arrow_is_not_exempt(tmp_path: Path) -> None:
    """Dropping the arrow must not be enough to hide a stale claim."""
    root = _tree(tmp_path, ["那一轮 90 passed / 12 skipped"])
    problems = gate.stale_totals(root)
    assert any(f"{LIVE}:1" in problem for problem in problems)
    assert gate.round_report_lines(root) == []


def test_a_benchmark_arrow_is_not_a_round_report(tmp_path: Path) -> None:
    """Units on both sides are a measurement, not a round delta."""
    root = _tree(
        tmp_path,
        [
            "median 39.7ms → 19.6ms（2.03x）；全量 99 passed, 12 skipped",
        ],
    )
    assert gate.round_report_lines(root) == []
    problems = gate.stale_totals(root)
    assert any(f"{LIVE}:1" in problem for problem in problems)


def test_the_exemption_matches_real_documents_and_nothing_is_stale() -> None:
    """A rule that quietly matches nothing looks exactly like a passing rule."""
    assert gate.round_report_lines(), "轮次记录识别规则没有匹配到任何真实文档行"
    assert gate.stale_totals() == []
