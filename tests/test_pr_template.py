"""The PR template stays as short as the fyscs repositories it mirrors.

Why this exists
---------------
The template is read by every contributor and pre-filled by GitHub on every new PR.
It went through two failures worth pinning:

1. it grew into a thirteen-section table with empty cells and unchecked boxes, which
   nobody fills in and which reads like machine output;
2. the sections it promised drifted away from what ``CONTRIBUTING.md`` told readers.

So the contract here is narrow and literal: four sections, plain lists instead of
checkboxes, no tables, and an Agent declaration that names a concrete model.
"""

from __future__ import annotations

from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
TEMPLATE = ROOT / ".github" / "pull_request_template.md"
CONTRIBUTING = ROOT / "CONTRIBUTING.md"

REQUIRED_SECTIONS = (
    "该PR作用的模块是(仅英文小写)",
    "为什么要增加/修改这个东西",
    "在提交PR前请确认已完成以下工作",
    "Agent 参与声明",
)


def template_problems(text: str) -> list[str]:
    """Return every required section or convention the template has lost."""
    out: list[str] = []
    headings = [
        line.lstrip("#").strip()
        for line in text.splitlines()
        if line.startswith("## ")
    ]
    for section in REQUIRED_SECTIONS:
        if section not in headings:
            out.append(f"模板缺少小节：{section}")

    if "不适用的小节直接删除" not in text:
        out.append("模板没有说明「不适用就删掉，不要留空」")
    if "具体型号" not in text:
        out.append("模板没有要求 Agent 声明写到具体型号")

    # The two shapes that made the old template unreadable. Checked as literals
    # rather than parsed: "a table in a PR body" is what a human notices at a
    # glance, and a parser would quietly normalise it away.
    if "| ---" in text:
        out.append("模板又出现了 Markdown 表格")
    if "- [ ]" in text:
        out.append("检查项退化成复选框")

    bullets = [line for line in text.splitlines() if line.startswith("- ")]
    if len(bullets) < 5:
        out.append("检查项少于 5 条，清单退化了")
    return out


def test_the_template_keeps_every_section() -> None:
    assert template_problems(TEMPLATE.read_text(encoding="utf-8")) == []


@pytest.mark.parametrize("section", REQUIRED_SECTIONS)
def test_deleting_a_section_is_reported(section: str) -> None:
    """A removed question must fail here, not silently vanish from every PR."""
    text = TEMPLATE.read_text(encoding="utf-8")
    kept = [
        line
        for line in text.splitlines()
        if not (line.startswith("## ") and line.lstrip("#").strip() == section)
    ]
    assert section not in [
        line.lstrip("#").strip() for line in kept if line.startswith("## ")
    ]
    assert any(section in problem for problem in template_problems("\n".join(kept)))


def test_contributing_no_longer_tells_people_to_bypass_the_template() -> None:
    """``--fill`` puts the commit message in the body; the template never loads."""
    text = CONTRIBUTING.read_text(encoding="utf-8")
    assert "gh pr create --fill" not in text
    assert "gh pr create --base master" in text
    assert "不要用 `--fill`" in text


def test_contributing_documents_the_block_mode() -> None:
    """The mode is a repo variable; if the docs never mention it, nobody flips it."""
    text = CONTRIBUTING.read_text(encoding="utf-8")
    assert "AI_REVIEW_MODE" in text
    assert "block" in text


def test_contributing_documents_who_may_bypass() -> None:
    """The rule that replaced "everyone goes through a PR" must stay explicit.

    Three facts have to survive future edits: bypass is tied to the admin role (not
    to a person — the ruleset API cannot express that on a user-owned repository), a
    submitter may not approve or force-merge their own PR, and new collaborators top
    out at maintain.
    """
    text = CONTRIBUTING.read_text(encoding="utf-8")
    assert "admin" in text
    assert "maintain" in text
    assert "不能自批" in text or "不得自批" in text
    assert "require_last_push_approval" in text or "最后一次推送" in text
    assert "--admin" in text
