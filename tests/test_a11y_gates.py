"""The native-confirm rule must fail on a real call and ignore a comment.

A gate that only ever prints "ok" is indistinguishable from one that checks nothing, and
this repository has shipped that defect once already. The two cases here are the two ways
this rule can be wrong: missing a call, or firing on the sentence that explains the rule.
"""

from __future__ import annotations

import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))

import check_a11y  # noqa: E402


def _scan(tmp_path: Path, body: str, monkeypatch: pytest.MonkeyPatch) -> list[str]:
    (tmp_path / "View.vue").write_text(body, encoding="utf-8")
    monkeypatch.setattr(check_a11y, "VIEWS", tmp_path)
    return check_a11y.check_native_confirm()


def test_a_call_is_reported(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    problems = _scan(
        tmp_path,
        '<script setup lang="ts">\n'
        "export function ask() { return window.confirm('sure?') }\n"
        "</script>\n",
        monkeypatch,
    )

    assert len(problems) == 1
    assert "View.vue:2" in problems[0]


def test_a_comment_is_not_a_violation(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """The rule's own explanation names the API; that cannot count as using it."""
    problems = _scan(
        tmp_path,
        '<script setup lang="ts">\n'
        "// Replaced window.confirm with ConfirmDialog for the focus trap.\n"
        "const a = 1\n"
        "</script>\n",
        monkeypatch,
    )

    assert problems == []


def test_the_committed_tree_has_no_native_confirm() -> None:
    assert check_a11y.check_native_confirm() == []
