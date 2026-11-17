"""Full-file review (v2): the model reads complete files, and the verdict is honest.

The v1 reviewer saw only diff hunks — three lines of context, no function bodies, no
file-level guards. v2 gives each group call the complete PR-side content plus that
file's hunks, and then pins the properties that make the extra reading *trustworthy*:

* classification is deterministic (generated/binary skipped, deletions read via diff);
* path containment — changed-file names come from the PR, a fork controls that text;
* the verdict cannot claim `safe` over content that was capped, missing or whose
  group call failed (the model is not consulted about this — it is enforced);
* group answers are parsed defensively; a failed group fails only itself.
"""

from __future__ import annotations

import importlib.util
import json
import sys
from pathlib import Path
from unittest import mock

import pytest

ROOT = Path(__file__).resolve().parents[1]
SCRIPT = ROOT / "scripts" / "ai_review.py"


def _module():
    spec = importlib.util.spec_from_file_location("ai_review_v2", SCRIPT)
    assert spec and spec.loader
    module = importlib.util.module_from_spec(spec)
    # dataclasses._is_type() resolves string annotations against sys.modules[module
    # name]; an unregistered module would crash on the FileEntry dataclass.
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


def _meta() -> dict:
    return {"title": "t", "author": "a", "body": "", "files": "1", "model": "test-model"}


def _verdict(payload: dict) -> str:
    return json.dumps(payload, ensure_ascii=False)


# ------------------------------------------------------------------ classification
def test_generated_and_binary_files_are_skipped() -> None:
    module = _module()
    for path in (
        "src/soapbot/webui/dist/assets/index-abc.js",
        "mobile/build/app/outputs/app.apk",
        "docs/图片.png",
        "package-lock.json",
    ):
        mode, reason = module.classify_changed_file(path)
        assert mode == "skip", path
        assert reason, "跳过必须写明原因，评论要能交代为什么没看"


def test_source_files_classify_full() -> None:
    module = _module()
    for path in ("src/soapbot/api/auth.py", "webui/src/views/SecurityView.vue", "README.md"):
        mode, _ = module.classify_changed_file(path)
        assert mode == "full", path


def test_diff_is_split_by_post_image_path() -> None:
    module = _module()
    diff = (
        "diff --git a/src/old.py b/src/new.py\nindex 1..2\n--- a/src/old.py\n"
        "+++ b/src/new.py\n@@ -1 +1 @@\n-old line\n+new line\n"
        "diff --git a/gone.py b/gone.py\nindex 3..0\n--- a/gone.py\n"
        "+++ /dev/null\n@@ -1 +0,0 @@\n-entire body\n"
    )
    sections = module.split_diff_by_file(diff)
    assert set(sections) == {"src/new.py", "gone.py"}
    assert "-entire body" in sections["gone.py"]  # deletion keeps its whole body


# ------------------------------------------------------------------ tree + containment
def _tree(tmp_path: Path) -> tuple[Path, dict[str, str]]:
    tree = tmp_path / "pr-tree"
    files = {
        "src/soapbot/screen/control.py": "def act():\n    return 1\n",
        "docs/guide.md": "# guide\n",
    }
    for rel, body in files.items():
        target = tree / rel
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_text(body, encoding="utf-8")
    return tree, files


def _diff_for(*paths: str) -> str:
    parts = []
    for path in paths:
        parts.append(
            f"diff --git a/{path} b/{path}\nindex 1..2 100644\n--- a/{path}\n"
            f"+++ b/{path}\n@@ -1 +1 @@\n-old\n+new"
        )
    return "\n".join(parts)


def test_collect_reads_full_content_and_marks_deletions(tmp_path) -> None:
    module = _module()
    tree, _files = _tree(tmp_path)
    diff = (
        module.split_diff_by_file(_diff_for("src/soapbot/screen/control.py"))
        and _diff_for("docs/guide.md")
        + "\n"
        + "diff --git a/removed.py b/removed.py\nindex 3..0\n--- a/removed.py\n"
        "+++ /dev/null\n@@ -1,2 +0,0 @@\n-line one\n-line two\n"
    )
    entries = module.collect_file_entries(
        ["src/soapbot/screen/control.py", "removed.py"],
        tree_root=tree, diff=diff, security_critical=module.SECURITY_CRITICAL,
    )
    assert entries[0].mode == "full" and entries[0].fully_read is True
    assert "def act():" in entries[0].content  # 完整内容进来了，不只是 hunk
    assert entries[1].deleted is True and entries[1].fully_read is True


def test_a_path_that_escapes_the_tree_is_refused(tmp_path) -> None:
    """Changed-file names come from the PR; a fork controls that text."""
    module = _module()
    tree, _files = _tree(tmp_path)
    (tmp_path / "secret.txt").write_text("outside", encoding="utf-8")
    for hostile in ("../../secret.txt", "/etc/passwd", "..\\..\\secret.txt"):
        entries = module.collect_file_entries(
            [hostile], tree_root=tree, diff="", security_critical=()
        )
        assert entries[0].fully_read is False, hostile
        assert "拒绝读取" in entries[0].reason, hostile
        assert "outside" not in entries[0].content


def test_an_oversized_file_is_partial_and_never_fully_read(tmp_path, monkeypatch) -> None:
    module = _module()
    tree, _files = _tree(tmp_path)
    big = tree / "src/big.py"
    big.parent.mkdir(parents=True, exist_ok=True)
    big.write_text("x = 1\n" * 5000, encoding="utf-8")
    monkeypatch.setattr(module, "MAX_FILE_LINES", 100)
    entries = module.collect_file_entries(
        ["src/big.py"], tree_root=tree, diff="", security_critical=()
    )
    assert entries[0].mode == "partial"
    assert entries[0].fully_read is False
    assert "未读" in entries[0].reason


# ------------------------------------------------------------------ grouping
def test_groups_pack_four_files_and_critical_paths_go_first() -> None:
    module = _module()

    def entry(path: str, critical: bool = False) -> module.FileEntry:
        return module.FileEntry(
            path=path, mode="full", content="x = 1\n", fully_read=True, critical=critical
        )

    entries = [
        entry("tests/test_a.py"),
        entry("src/soapbot/api/auth.py", critical=True),
        entry("src/soapbot/api/chat.py"),
        entry("tests/test_b.py"),
        entry("tests/test_c.py"),
    ]
    groups, leftovers = module.plan_groups(entries)
    assert not leftovers
    # Pack-to-full keeps the call count down; the sort only guarantees the critical
    # path is included first when the budget runs out.
    assert len(groups[0]) == module.MAX_GROUP_FILES
    assert groups[0][0].path == "src/soapbot/api/auth.py"
    assert all(len(g) <= module.MAX_GROUP_FILES for g in groups)


def test_files_beyond_the_call_budget_fall_back_and_are_flagged() -> None:
    module = _module()
    entries = [
        module.FileEntry(path=f"src/f{i}.py", mode="full", content="x", fully_read=True)
        for i in range(module.MAX_FILE_CALLS * module.MAX_GROUP_FILES + 3)
    ]
    groups, leftovers = module.plan_groups(entries)
    assert groups  # budget respected
    assert sum(len(g) for g in groups) <= module.MAX_FILE_CALLS * module.MAX_GROUP_FILES
    assert len(leftovers) == 3
    # The ranking is lexicographic, so which three fall off the end is an ordering
    # detail; what matters is that they are not in any group and review() demotes them.
    leftover_paths = {e.path for e in leftovers}
    assert leftover_paths.isdisjoint({e.path for g in groups for e in g})
    for e in leftovers:
        e.mode = "partial"
        e.fully_read = False
    assert all(not e.fully_read for e in leftovers)


# ------------------------------------------------------------------ the v2 flow
def _full_entries(module, count: int = 1) -> list:
    return [
        module.FileEntry(
            path=f"src/f{i}.py", mode="full", content="x = 1\n", hunks="+new",
            fully_read=True,
        )
        for i in range(count)
    ]


def test_full_file_review_calls_groups_then_synthesis_and_can_be_safe() -> None:
    module = _module()
    group_answer = _verdict({"files": [
        {"file": "src/f0.py", "fully_read": True,
         "findings": [{"severity": "low", "location": "act()", "why": "一处提示"}]},
    ]})
    synthesis = _verdict({
        "verdict": "safe", "risk": "low", "summary": "一致", "concerns": [],
    })
    with mock.patch.object(
        module, "call_model", side_effect=[group_answer, synthesis]
    ) as call:
        result = module.review(
            "+new", _meta(), api_key="k", model="m", base_url="https://x.example",
            entries=_full_entries(module),
        )

    assert result["verdict"] == "safe" and result["degraded"] is False
    assert call.call_count == 2
    group_prompt = call.call_args_list[0].args[0]
    synthesis_prompt = call.call_args_list[1].args[0]
    # The group call saw the complete file, not just the hunk.
    assert "完整文件内容（PR 侧）开始" in group_prompt
    assert "x = 1" in group_prompt
    # The synthesis call carries the per-file findings and the coverage table.
    assert "分文件审查 findings" in synthesis_prompt
    assert "src/f0.py" in synthesis_prompt
    assert "覆盖面" in synthesis_prompt
    assert result["coverage"] and "完整文件" in result["coverage"]
    assert result["findings"][0]["file"] == "src/f0.py"


def test_a_capped_file_forces_needs_review_even_when_the_model_says_safe() -> None:
    module = _module()
    synthesis = _verdict({"verdict": "safe", "risk": "low", "summary": "看着没问题"})
    entries = [
        module.FileEntry(
            path="src/f0.py", mode="partial", content="x = 1\n",
            hunks="+new", fully_read=False, reason="超出单文件上限（3 KB 未读）",
        )
    ]
    with mock.patch.object(module, "call_model", return_value=synthesis) as call:
        result = module.review(
            "+new", _meta(), api_key="k", model="m", base_url="https://x.example",
            entries=entries,
        )
    assert result["verdict"] == "needs_review"
    assert "自动降级" in result["summary"]
    assert call.call_count == 1  # capped 文件不进分组调用；只有汇总一次


def test_a_failed_group_call_skips_the_synthesis_when_nothing_was_read() -> None:
    module = _module()
    with mock.patch.object(
        module, "call_model", side_effect=module.ReviewError("模型返回 HTTP 500")
    ) as call:
        result = module.review(
            "+new", _meta(), api_key="k", model="m", base_url="https://x.example",
            entries=_full_entries(module),
        )
    assert result["verdict"] == "needs_review"
    assert result["degraded"] is True
    assert call.call_count == 1  # 唯一分组失败 → 不再花汇总调用


def test_a_partly_failed_review_still_reaches_synthesis_and_forces_needs_review() -> None:
    """Some groups succeed: their findings reach the synthesis, but the failed
    group's files force the downgrade — the model cannot argue them away."""
    module = _module()
    failed_group = module.ReviewError("HTTP 500")
    good_answer = _verdict({"files": [
        {"file": "src/good.py", "fully_read": True, "findings": []},
    ]})
    synthesis = _verdict({"verdict": "safe", "risk": "low", "summary": "fine"})

    def entry(path: str) -> module.FileEntry:
        return module.FileEntry(
            path=path, mode="full", content="x = 1\n", hunks="+new", fully_read=True
        )

    # Two groups: MAX_GROUP_FILES caps each group at 4 files, so 5 entries → 2 groups.
    entries = [entry(f"src/good{i}.py") for i in range(4)] + [entry("src/last.py")]
    with mock.patch.object(
        module, "call_model", side_effect=[failed_group, good_answer, synthesis]
    ) as call:
        result = module.review(
            "+new", _meta(), api_key="k", model="m", base_url="https://x.example",
            entries=entries,
        )
    assert result["verdict"] == "needs_review"
    assert result["degraded"] is False  # 不是模型故障降级，而是覆盖面强制
    assert "自动降级" in result["summary"]
    assert call.call_count == 3  # 两次分组 + 一次汇总


def test_when_every_group_fails_the_synthesis_is_not_spent() -> None:
    module = _module()
    with mock.patch.object(
        module, "call_model", side_effect=module.ReviewError("HTTP 500")
    ) as call:
        result = module.review(
            "+new", _meta(), api_key="k", model="m", base_url="https://x.example",
            entries=_full_entries(module, count=2),
        )
    assert result["verdict"] == "needs_review"
    assert result["degraded"] is True
    assert call.call_count == 1  # 两组文件打成一组（≤4 文件/组）；失败后不再汇总


def test_a_security_critical_file_skipped_as_generated_forces_needs_review() -> None:
    module = _module()
    synthesis = _verdict({"verdict": "safe", "risk": "low", "summary": "fine"})
    entries = [
        module.FileEntry(
            path="deploy/未知.bin", mode="skip", reason="二进制/生成物后缀",
            critical=True, fully_read=False,
        )
    ]
    with mock.patch.object(module, "call_model", return_value=synthesis):
        result = module.review(
            "+new", _meta(), api_key="k", model="m", base_url="https://x.example",
            entries=entries,
        )
    assert result["verdict"] == "needs_review"
    assert "安全关键" in result["summary"]


def test_deletions_alone_can_back_a_safe_verdict() -> None:
    module = _module()
    synthesis = _verdict({"verdict": "safe", "risk": "low", "summary": "纯删除"})
    entries = [
        module.FileEntry(
            path="src/gone.py", mode="diff_only", deleted=True, fully_read=True,
        )
    ]
    with mock.patch.object(module, "call_model", return_value=synthesis):
        result = module.review(
            "-line", _meta(), api_key="k", model="m", base_url="https://x.example",
            entries=entries,
        )
    assert result["verdict"] == "safe", "删除的全文就在 diff 里，不应被误伤"


def test_group_answer_shapes_are_tolerated() -> None:
    module = _module()
    fenced = "```json\n{\"files\": [{\"file\": \"src/f0.py\", \"findings\": \"缺细节\"}]}\n```"
    payload = module._extract_group_payload(fenced)
    assert payload["files"][0]["file"] == "src/f0.py"
    assert module._normalise_findings("缺细节") == [
        {"severity": "medium", "location": "", "why": "缺细节"}
    ]
    for bad in ("not json", "[]", "null"):
        with pytest.raises(module.ReviewError):
            module._extract_group_payload(bad)


def test_findings_flow_into_the_comment() -> None:
    module = _module()
    entries = [
        module.FileEntry(
            path="src/f0.py", mode="full", fully_read=True,
            findings=[{"severity": "high", "location": "act()", "why": "读取环境变量并外传"}],
        )
    ]
    result = {
        "verdict": "needs_review", "risk": "high", "summary": "可疑外传",
        "concerns": [], "truncated": False, "degraded": False,
        "coverage": module._render_coverage_block(entries),
        "findings": [{"file": "src/f0.py", "findings": entries[0].findings}],
    }
    comment = module.render_comment(result, _meta())
    assert "分文件审查发现" in comment
    assert "src/f0.py" in comment and "act()" in comment
    assert "审查覆盖面" in comment
    assert "不构成批准" in comment


def test_main_without_the_tree_falls_back_to_diff_only(tmp_path, monkeypatch) -> None:
    """A missing materialisation step must degrade honestly, not review nothing."""
    module = _module()
    diff = tmp_path / "pr.diff"
    diff.write_text("+ hello", encoding="utf-8")
    files = tmp_path / "pr-files.txt"
    files.write_text("src/soapbot/api/auth.py\n", encoding="utf-8")
    comment = tmp_path / "comment.md"
    output = tmp_path / "out.txt"
    monkeypatch.setenv("DEEPSEEK_API_KEY", "k")
    monkeypatch.setenv("PR_DIFF_PATH", str(diff))
    monkeypatch.setenv("PR_CHANGED_FILES_PATH", str(files))
    monkeypatch.delenv("PR_FILES_ROOT", raising=False)
    monkeypatch.setenv("AI_REVIEW_COMMENT_PATH", str(comment))
    monkeypatch.setenv("GITHUB_OUTPUT", str(output))
    synthesis = _verdict({"verdict": "safe", "risk": "low", "summary": "fine"})
    with mock.patch.object(module, "call_model", return_value=synthesis):
        assert module.main() == 0
    assert "verdict=needs_review" in output.read_text(encoding="utf-8")
    assert "未完整读取" in comment.read_text(encoding="utf-8")


def test_main_uses_the_tree_when_provided(tmp_path, monkeypatch) -> None:
    module = _module()
    tree, _files = _tree(tmp_path)
    diff = tmp_path / "pr.diff"
    diff.write_text(_diff_for("src/soapbot/screen/control.py"), encoding="utf-8")
    names = tmp_path / "pr-files.txt"
    names.write_text("src/soapbot/screen/control.py\n", encoding="utf-8")
    comment = tmp_path / "comment.md"
    output = tmp_path / "out.txt"
    monkeypatch.setenv("DEEPSEEK_API_KEY", "k")
    monkeypatch.setenv("PR_DIFF_PATH", str(diff))
    monkeypatch.setenv("PR_CHANGED_FILES_PATH", str(names))
    monkeypatch.setenv("PR_FILES_ROOT", str(tree))
    monkeypatch.setenv("AI_REVIEW_COMMENT_PATH", str(comment))
    monkeypatch.setenv("GITHUB_OUTPUT", str(output))
    group_answer = _verdict({"files": [
        {"file": "src/soapbot/screen/control.py", "fully_read": True, "findings": []},
    ]})
    synthesis = _verdict({
        "verdict": "safe", "risk": "low", "summary": "一致", "concerns": [],
    })
    with mock.patch.object(
        module, "call_model", side_effect=[group_answer, synthesis]
    ) as call:
        assert module.main() == 0
    assert "verdict=safe" in output.read_text(encoding="utf-8")
    assert "完整文件" in comment.read_text(encoding="utf-8")
    assert call.call_args_list[0].kwargs.get("system_prompt") == module.FILES_SYSTEM_PROMPT


# ------------------------------------------------------------------ egress guards
def test_base_url_must_be_https_with_a_hostname() -> None:
    module = _module()
    assert module.validate_base_url("https://api.deepseek.com") == "https://api.deepseek.com"
    for bad in ("http://api.deepseek.com", "file:///etc/passwd", "api.deepseek.com", ""):
        with pytest.raises(module.ReviewError):
            module.validate_base_url(bad)


def test_private_and_metadata_addresses_are_refused() -> None:
    """A drifted AI_REVIEW_BASE_URL must fail closed, not probe the internal network."""
    module = _module()
    for host in ("127.0.0.1", "169.254.169.254", "10.0.0.5", "192.168.1.1"):
        with pytest.raises(module.ReviewError):
            module._assert_routable_hostname(host)


# ------------------------------------------------------- deleted 判定（v1.0 审计修复）
def test_real_diff_header_does_not_falsify_deletion() -> None:
    """A real `gh pr diff` section always carries "\\n--- a/…" — counting "-"
    lines classified EVERY tree-missing live file as deleted (fully_read=True),
    which defeated the not-fully-read downgrade. The structural marker
    (`+++ /dev/null`) is the only honest signal."""
    module = _module()
    diff = (
        "diff --git a/src/app.py b/src/app.py\n"
        "index abc..def 100644\n"
        "--- a/src/app.py\n"
        "+++ b/src/app.py\n"
        "@@ -1 +1 @@\n"
        "-old\n"
        "+new\n"
    )
    entries = module.collect_file_entries(
        ["src/app.py"], tree_root=None, diff=diff, security_critical=()
    )
    assert entries[0].deleted is False
    assert entries[0].fully_read is False  # 树缺失 = 未完整读取 = 强制降级


def test_true_deletion_is_recognized_structurally(tmp_path) -> None:
    module = _module()
    diff = (
        "diff --git a/gone.py b/gone.py\n"
        "index abc..000\n"
        "--- a/gone.py\n"
        "+++ /dev/null\n"
        "@@ -1 +0,0 @@\n"
        "-body\n"
    )
    # tree_root 是真实存在的目录：文件不在其中（= 树里确实没有这个文件），
    # 才会走到 is_file() 的删除判定分支。
    entries = module.collect_file_entries(
        ["gone.py"], tree_root=tmp_path, diff=diff, security_critical=()
    )
    assert entries[0].deleted is True and entries[0].fully_read is True
