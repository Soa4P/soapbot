"""The deterministic impact layer of the PR reviewer.

The impact read exists because "which surfaces did this touch" is a filename
question: a reviewer (human or model) can read 400 diff lines and never register
that one of them edits the approval surface. These tests pin the two properties
that make the layer trustworthy — it is independent of the model call, and it
names security-critical files explicitly.
"""

from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts"))

from ai_review import analyse_impact, build_prompt, render_impact


def test_subsystems_are_counted_by_prefix() -> None:
    impact = analyse_impact(
        [
            "src/soapbot/api/chat.py",
            "src/soapbot/api/accounts.py",
            "src/soapbot/memory/store.py",
            "docs/guide.md",
        ]
    )
    assert impact["total"] == 4
    assert impact["subsystems"] == {"面板 API": 2, "记忆与存档": 1, "文档": 1}


def test_unknown_paths_are_counted_not_dropped() -> None:
    impact = analyse_impact(["data/some-file.txt", "README.md"])
    assert impact["unknown"] == 2
    assert impact["subsystems"] == {}


def test_security_critical_hits_are_named() -> None:
    impact = analyse_impact(
        [
            "src/soapbot/api/auth.py",
            "src/soapbot/plugins/surfaces.py",
            ".github/workflows/ci.yml",
            "webui/src/views/OverviewView.vue",
        ]
    )
    assert impact["security_hits"] == [
        "src/soapbot/api/auth.py",
        "src/soapbot/plugins/surfaces.py",
        ".github/workflows/ci.yml",
    ]


def test_render_marks_clean_prs_and_hits_alike() -> None:
    clean = render_impact(analyse_impact(["docs/guide.md"]))
    assert "未触及安全关键面" in clean
    dirty = render_impact(analyse_impact(["src/soapbot/api/auth.py"]))
    assert "⚠ 触及安全关键面" in dirty and "api/auth.py" in dirty


def test_impact_reaches_the_model_prompt() -> None:
    impact = analyse_impact(["src/soapbot/api/auth.py"])
    prompt = build_prompt("(diff)", {"title": "t", "impact": impact}, truncated=False)
    # The cross-check instruction keeps the model from taking credit for the list.
    assert "影响面" in prompt
    assert "由文件名统计得出" in prompt


def test_prompt_carries_commit_subjects() -> None:
    prompt = build_prompt(
        "(diff)", {"title": "t", "commits": "修复: 登录\n新增: 某功能"}, truncated=False
    )
    assert "提交信息" in prompt
    assert "- 修复: 登录" in prompt


def test_comment_shows_impact_even_without_model_work(tmp_path, monkeypatch) -> None:
    """A missing API key still yields a comment carrying the blast radius."""
    import importlib

    import ai_review

    importlib.reload(ai_review)
    files = tmp_path / "files.txt"
    files.write_text("src/soapbot/api/auth.py\n", encoding="utf-8")
    diff = tmp_path / "pr.diff"
    diff.write_text("(diff)", encoding="utf-8")
    monkeypatch.setenv("PR_CHANGED_FILES_PATH", str(files))
    monkeypatch.setenv("PR_DIFF_PATH", str(diff))
    monkeypatch.delenv("DEEPSEEK_API_KEY", raising=False)
    monkeypatch.delenv("AI_REVIEW_COMMENT_PATH", raising=False)
    monkeypatch.delenv("GITHUB_OUTPUT", raising=False)
    exit_code = ai_review.main()
    assert exit_code == 0


def test_comment_impact_section_appears_in_render(monkeypatch) -> None:
    import ai_review

    meta = {
        "title": "t",
        "author": "a",
        "model": "m",
        "impact": analyse_impact(["src/soapbot/api/auth.py", "tests/test_x.py"]),
        "commits": "修复: 某问题",
    }
    result = {
        "verdict": "needs_review",
        "risk": "medium",
        "summary": "一句话",
        "concerns": [],
        "truncated": False,
        "degraded": False,
    }
    comment = ai_review.render_comment(result, meta)
    assert "影响面" in comment
    assert "api/auth.py" in comment
    assert "### 提交（1 个）" in comment
    # The advisory framing is the contract with the repo: assist, never approve.
    assert "不构成批准" in comment
