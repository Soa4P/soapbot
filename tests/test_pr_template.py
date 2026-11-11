"""The PR template is short enough for a first-time contributor to fill in.

Why this exists
---------------
The template must ask for the small set of facts a maintainer needs to review a
public contribution: purpose, user instructions, breaking changes, verification,
and Agent participation. It should not turn every PR into an internal audit report.

A removed question must fail here, not silently vanish from future PRs. These tests
pin the contributor-facing section list and the ``--fill`` prohibition.
"""

from __future__ import annotations

from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
TEMPLATE = ROOT / ".github" / "pull_request_template.md"
CONTRIBUTING = ROOT / "CONTRIBUTING.md"

REQUIRED_SECTIONS = (
    "该 PR 作用的地图（仅英文小写）",
    "为什么要增加/修改这个东西",
    "用户怎么使用",
    "破坏性变更",
    "在提交 PR 前确认已经完成以下工作",
    "验证结果",
    "Agent 参与声明",
)

#: CONTRIBUTING.md explicitly tells readers that these sections exist, so a template
#: that drops them makes the contribution guide a lie. Kept separate from
#: REQUIRED_SECTIONS so the parameterised case count stays stable — a doc edit must
#: not force four "N passed" baselines to be rewritten.
EXTRA_SECTIONS = (
    "改了什么",
    "影响面",
    "安全影响",
    "数字基线",
    "AI 审查",
    "回滚",
)


def template_problems(text: str) -> list[str]:
    """Return every required section or warning the template has lost."""
    out: list[str] = []
    headings = [
        line.lstrip("#").strip()
        for line in text.splitlines()
        if line.startswith("## ")
    ]
    for section in (*REQUIRED_SECTIONS, *EXTRA_SECTIONS):
        if section not in headings:
            out.append(f"模板缺少小节：{section}")

    if "不适用的小节直接删除" not in text:
        out.append("模板没有说明「不适用就删掉，不要留空」")
    if "none" not in text or "实际使用的模型" not in text:
        out.append("模板没有要求声明 Agent 参与情况")
    if "未验证" not in text:
        out.append("模板没有要求标注未验证内容")
    if text.count("- [ ]") < 5:
        out.append("检查项少于 5 条，勾选清单退化了")
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
    assert "--fill 会用 commit message" in text or "不要用 `--fill`" in text


def test_contributing_documents_the_block_mode() -> None:
    """The mode is a repo variable; if the docs never mention it, nobody flips it."""
    text = CONTRIBUTING.read_text(encoding="utf-8")
    assert "AI_REVIEW_MODE" in text
    assert "block" in text
