"""The PR template is a checklist, and an unchecked one is worthless.

Why this exists
---------------
The template used to be five sections with a two-row table and four checkboxes.
It never rendered anything about the blast radius, the test-count baseline, the
AI review verdict, or how to roll the change back — so those questions were
answered (or not) depending on who opened the PR.

Two failure modes are silent and both happened or nearly happened here:

* ``gh pr create --fill`` writes the commit message into the body and never
  loads the template, so editing the template changes nothing on the PR.
* A section can be deleted and the file still looks fine, because Markdown has
  no schema. The next author then assumes the missing question was irrelevant.

These tests pin the section list and the ``--fill`` prohibition. They cannot
judge whether an author filled the sections in honestly.
"""

from __future__ import annotations

from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
TEMPLATE = ROOT / ".github" / "pull_request_template.md"
CONTRIBUTING = ROOT / "CONTRIBUTING.md"

REQUIRED_SECTIONS = (
    "改了什么",
    "为什么",
    "影响面",
    "验证",
    "数字基线",
    "AI 审查",
    "安全影响",
    "回滚",
    "检查",
)

# Baselines whose numbers must move together with the test count.
BASELINE_FILES = (
    "docs/verification-matrix.md",
    "docs/delivery-readiness-v2.md",
    "docs/architecture.md",
    "docs/progress/progress.json",
)


def template_problems(text: str) -> list[str]:
    """Return every required section or warning the template has lost."""
    out: list[str] = []
    headings = [
        line.lstrip("#").strip()
        for line in text.splitlines()
        if line.startswith("## ")
    ]
    for section in REQUIRED_SECTIONS:
        if section not in headings:
            out.append(f"模板缺少小节：{section}")

    if "不适用的小节直接删掉" not in text:
        out.append("模板没有说明「不适用就删掉，不要留空」")
    for name in BASELINE_FILES:
        if name not in text:
            out.append(f"数字基线小节没有点名 {name}")
    if "`make check` 未整体跑过" not in text:
        out.append("模板没有要求 make check 未跑时说明原因")
    if "degraded" not in text:
        out.append("AI 审查小节没有说明降级结论要人工复核")
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
