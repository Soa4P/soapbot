"""Workflows must pin actions by commit SHA and ask for the least privilege they need.

Two failure modes this closes (audit S-DEP-09), both invisible in review because the
file looks unchanged afterwards:

* **A tag is mutable.** ``uses: actions/checkout@v7`` resolves at run time; whoever can
  move that tag — the action's author, or anyone who compromises the repository — chooses
  what runs with this repository's token. A commit SHA cannot move.
* **No top-level ``permissions:`` inherits the repository default**, which on older
  settings is read/write. A compromised step could then push to the branch it is testing.

The interesting asymmetry: the *release* job legitimately needs ``contents: write``, and
that is fine — scoped to the job, so a test step in another job cannot publish.
"""

from __future__ import annotations

import re
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
WORKFLOWS = sorted((ROOT / ".github" / "workflows").glob("*.yml"))

#: `uses: owner/repo@<ref>` plus an optional `# comment`. Local actions (`./…`) and
#: docker references are not tag-pinned and are out of scope.
_USES = re.compile(r"^\s*-?\s*uses:\s*(\S+)(?:\s*#\s*(.*))?$", re.MULTILINE)
_SHA = re.compile(r"^[0-9a-f]{40}$")


def test_there_is_something_to_check() -> None:
    assert WORKFLOWS, "没有找到任何 workflow"


@pytest.mark.parametrize("workflow", WORKFLOWS, ids=lambda p: p.name)
def test_every_action_is_pinned_to_a_commit(workflow: Path) -> None:
    text = workflow.read_text(encoding="utf-8")
    offenders: list[str] = []
    for target, comment in _USES.findall(text):
        if target.startswith("./") or target.startswith("docker://"):
            continue
        _, _, ref = target.partition("@")
        if not _SHA.match(ref):
            offenders.append(target)
        elif not (comment or "").strip():
            # A bare SHA is unmaintainable: the reader cannot tell v7 from v5, and the
            # next person "fixes" it back to a tag.
            offenders.append(f"{target} (缺版本注释)")
    assert not offenders, f"{workflow.name} 有未钉住/未注释的 action：{offenders}"


def test_ci_defaults_to_read_only_and_scopes_write_to_the_release_job() -> None:
    text = (ROOT / ".github" / "workflows" / "ci.yml").read_text(encoding="utf-8")
    top = re.search(r"^permissions:\s*\n((?:\s{2,}.*\n)+)", text, re.MULTILINE)
    assert top, "ci.yml 没有顶层 permissions，继承仓库默认值（可能是读写）"
    assert "contents: read" in top.group(1)
    assert "contents: write" not in top.group(1), "写权限必须在 job 级声明"

    release = text[text.index("Create the release") - 4000 :]
    assert re.search(r"permissions:\s*\n\s+contents:\s*write", release), (
        "release job 需要 contents: write，但必须在它自己的 job 里声明"
    )


def test_ai_review_keeps_its_own_scoped_permissions() -> None:
    """It is `pull_request_target`: the one workflow that *must* be reviewed by eye."""
    text = (ROOT / ".github" / "workflows" / "ai-review.yml").read_text(encoding="utf-8")
    assert re.search(r"^permissions:\s*\n\s+contents:\s*read", text, re.MULTILINE)
    # Writing to the PR is the deliverable; anything beyond that is not.
    granted = re.findall(r"^\s{2}(\w[\w-]*):\s*(read|write)", text, re.MULTILINE)
    writes = {name for name, level in granted if level == "write"}
    assert writes <= {"pull-requests", "issues"}, f"ai-review 申请了额外写权限：{writes}"


def test_fork_prs_do_not_spend_the_review_key() -> None:
    """`pull_request_target` + ``secrets`` is a bill someone else can run up.

    The maintainer cannot merge a fork PR without reading it, so a model pass buys
    nothing — and every push by a stranger would cost a call (audit S-DEP-10). The
    model steps are therefore gated, and the fork path still writes a comment so the
    operator is told a human is needed rather than seeing a silent green check.
    """
    text = (ROOT / ".github" / "workflows" / "ai-review.yml").read_text(encoding="utf-8")
    fenced = "github.event.pull_request.head.repo.full_name == github.repository"
    for step in ("Read the diff as text", "Materialise the PR tree as text", "Ask the model"):
        start = text.index(f"- name: {step}")
        header = text[start : start + 400]
        assert fenced in header, f"{step} 没有被 fork 条件拦住"
    # ... and the fork path says why, instead of passing silently.
    assert "Fork PRs are not auto-reviewed" in text
    fork_step = text[text.index("Fork PRs are not auto-reviewed") :][:600]
    assert "comment.md" in fork_step


def test_the_review_script_has_a_deterministic_injection_guard() -> None:
    """Prompt injection must not be the only thing between a PR and `ai:safe`."""
    script = (ROOT / "scripts" / "ai_review.py").read_text(encoding="utf-8")
    assert "scan_reviewer_injection" in script
    assert "_forced_unsafe_reasons" in script
    # The v2 path and the diff-only fallback both consult it.
    assert script.count("scan_reviewer_injection(") >= 2
