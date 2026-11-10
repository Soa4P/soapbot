"""The AI review workflow is code too, and a broken one fails in zero seconds.

Why this exists
---------------
On 2026-11-09 a run of ``ai-review.yml`` ended in ``startup_failure`` after 0s.
GitHub would only say "This run likely failed because of a workflow file issue" —
no log, no step output, and ``make check`` cannot see it, because nothing local
executes the YAML. The same blind spot would let someone quietly drop the safety
model (checkout of ``base.sha``, diff read as text only) and leave a workflow that
looks fine while handing a secret to PR-controlled code.

What this can and cannot do: it parses structure, not the Actions schema. It will
not catch an invalid expression, but it does catch a file that no longer parses, a
checkout that moved off ``base.sha``, an install step appearing in the job that
holds ``DEEPSEEK_API_KEY``, a mode variable nobody reads, and an enforce step
placed before the comment — which would hide the reason for a red job.
"""

from __future__ import annotations

from pathlib import Path

import pytest
import yaml

ROOT = Path(__file__).resolve().parents[1]
WORKFLOW = ROOT / ".github" / "workflows" / "ai-review.yml"
BASE_REF = "${{ github.event.pull_request.base.sha }}"
ENFORCE = "Enforce review mode"


def _workflow() -> dict:
    return yaml.safe_load(WORKFLOW.read_text(encoding="utf-8"))


def workflow_problems(workflow: dict) -> list[str]:
    """Return every way the workflow would be unsafe or silently unenforced."""
    out: list[str] = []
    steps = ((workflow.get("jobs") or {}).get("review") or {}).get("steps") or []
    names = [str(step.get("name", "")) for step in steps]

    checkout = next(
        (step for step in steps if "checkout" in str(step.get("uses", ""))), None
    )
    if checkout is None:
        out.append("没有 checkout 步骤")
    elif (checkout.get("with") or {}).get("ref") != BASE_REF:
        out.append("checkout 没有钉在 pull_request.base.sha")

    if ENFORCE not in names:
        out.append("缺少 Enforce review mode 步骤")
    else:
        position = names.index(ENFORCE)
        enforce = steps[position]
        env = enforce.get("env") or {}
        mode = str(env.get("MODE", ""))
        run = str(enforce.get("run", ""))
        if "AI_REVIEW_MODE" not in mode:
            out.append("Enforce 没有读取 AI_REVIEW_MODE（变量会再次变成死配置）")
        if "|| 'observe'" not in mode:
            out.append("observe 不是默认值")
        if "block" not in run:
            out.append("Enforce 没有 block 分支")
        if "exit 0" not in run:
            out.append("Enforce 没有 observe 的通过路径")
        if "未知的 AI_REVIEW_MODE" not in run:
            out.append("Enforce 对未知模式没有 fail-closed 分支（拼错会静默变成 observe）")
        for earlier in ("Comment", "Label"):
            if earlier in names and names.index(earlier) > position:
                out.append(f"Enforce 排在 {earlier} 之后才算最后，现在它在前")
        if position != len(names) - 1:
            out.append("Enforce 不是最后一步，失败时 PR 上不会留下原因")

    text = yaml.safe_dump(workflow, allow_unicode=True)
    for forbidden in ("pip install", "npm install", "npm ci"):
        if forbidden in text:
            out.append(f"持有密钥的 job 里出现了 {forbidden}")
    return out


def test_the_workflow_is_safe_and_the_mode_is_wired() -> None:
    assert workflow_problems(_workflow()) == []


def test_the_workflow_parses() -> None:
    """The 0-second startup_failure left no log; parsing is the only local signal."""
    assert _workflow()["jobs"]["review"]["runs-on"] == "ubuntu-latest"


@pytest.mark.parametrize(
    ("mutate", "expected"),
    [
        (lambda w: w["jobs"]["review"]["steps"].pop(0), "checkout"),
        (lambda w: w["jobs"]["review"].__setitem__("steps", [
            s for s in w["jobs"]["review"]["steps"] if s.get("name") != ENFORCE
        ]), "缺少 Enforce"),
        (lambda w: w["jobs"]["review"]["steps"].append(
            {"name": "Install", "run": "pip install requests"}
        ), "pip install"),
    ],
)
def test_known_regressions_are_reported(mutate, expected: str) -> None:
    workflow = _workflow()
    mutate(workflow)
    found = workflow_problems(workflow)
    assert any(expected in problem for problem in found), found


def test_moving_enforce_before_the_comment_is_reported() -> None:
    """In block mode an early failure means no comment, so the PR shows a bare red X."""
    workflow = _workflow()
    steps = workflow["jobs"]["review"]["steps"]
    enforce = next(step for step in steps if step.get("name") == ENFORCE)
    steps.remove(enforce)
    comment_at = next(i for i, step in enumerate(steps) if step.get("name") == "Comment")
    steps.insert(comment_at, enforce)

    found = workflow_problems(workflow)
    assert any("Enforce 不是最后一步" in problem for problem in found), found


def test_a_typo_in_the_mode_variable_fails_closed() -> None:
    """``MODE=Block`` must not be read as observe: that is the same silent no-op the
    unread variable was."""
    workflow = _workflow()
    enforce = next(
        step for step in workflow["jobs"]["review"]["steps"] if step.get("name") == ENFORCE
    )
    enforce["run"] = (
        'if [ "$MODE" != "block" ]; then exit 0; fi\n'
        'if [ "$VERDICT" != "safe" ]; then exit 1; fi\n'
    )

    found = workflow_problems(workflow)
    assert any("未知模式" in problem for problem in found), found
