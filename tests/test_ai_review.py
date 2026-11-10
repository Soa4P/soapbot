"""The AI reviewer must never fail open.

A review that cannot be completed has to say so. Every failure path here — model
unreachable, unparsable JSON, unknown verdict, truncated diff — is asserted to end in
`needs_review`, because the alternative is a green comment on code nobody read.
"""

from __future__ import annotations

import importlib.util
import json
from pathlib import Path
from unittest import mock

import pytest

ROOT = Path(__file__).resolve().parents[1]
SCRIPT = ROOT / "scripts" / "ai_review.py"


def _module():
    spec = importlib.util.spec_from_file_location("ai_review", SCRIPT)
    assert spec and spec.loader
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def _meta() -> dict:
    return {"title": "t", "author": "a", "body": "", "files": "1", "model": "deepseek-chat"}


# ---------------------------------------------------------------- truncation


def test_truncate_keeps_short_text_intact() -> None:
    text, truncated, dropped = _module().truncate("a\nb\nc")

    assert text == "a\nb\nc"
    assert truncated is False
    assert dropped == ""


def test_truncate_caps_by_lines() -> None:
    module = _module()
    module.MAX_DIFF_LINES = 3

    text, truncated, dropped = module.truncate("\n".join(str(i) for i in range(10)))

    assert text.splitlines() == ["0", "1", "2"]
    assert truncated is True
    assert dropped == "7 行", "必须说明丢了多少，而不只是说「被截断」"


def test_truncate_caps_by_bytes() -> None:
    module = _module()
    module.MAX_DIFF_BYTES = 10
    module.MAX_DIFF_LINES = 100

    text, truncated, dropped = module.truncate("x" * 100)

    assert len(text.encode()) <= 10
    assert truncated is True
    assert dropped == "90 字节", "不足 1 KB 时不能显示成 0 KB"


# ---------------------------------------------------------------- parsing


def test_extract_json_handles_a_fenced_block() -> None:
    payload = _module()._extract_json('```json\n{"verdict": "safe"}\n```')

    assert payload["verdict"] == "safe"


def test_extract_json_handles_surrounding_prose() -> None:
    payload = _module()._extract_json('Sure!\n{"verdict": "safe"}\nHope that helps.')

    assert payload["verdict"] == "safe"


def test_extract_json_rejects_prose_only() -> None:
    module = _module()
    # Same module instance for the raise and the assertion: reloading it would create a
    # *different* ReviewError class, and pytest.raises compares by identity.
    with pytest.raises(module.ReviewError):
        module._extract_json("I cannot answer that.")


def test_normalise_rejects_an_unknown_verdict() -> None:
    module = _module()
    with pytest.raises(module.ReviewError):
        module.normalise({"verdict": "probably fine"})


def test_normalise_defaults_risk_to_medium() -> None:
    result = _module().normalise({"verdict": "safe", "summary": "ok"})

    assert result["risk"] == "medium"


# ---------------------------------------------------------------- degradation


def test_a_failed_call_degrades_to_needs_review() -> None:
    module = _module()
    with mock.patch.object(module, "call_model", side_effect=module.ReviewError("HTTP 500")):
        result = module.review("diff", _meta(), api_key="k", model="m", base_url="u")

    assert result["verdict"] == "needs_review"
    assert result["degraded"] is True
    assert "HTTP 500" in result["summary"]


def test_a_malformed_response_degrades_to_needs_review() -> None:
    module = _module()
    with mock.patch.object(module, "call_model", return_value="not json"):
        result = module.review("diff", _meta(), api_key="k", model="m", base_url="u")

    assert result["verdict"] == "needs_review"


def test_a_truncated_diff_cannot_be_safe() -> None:
    """'safe' over text the reviewer never saw is a claim it cannot make."""
    module = _module()
    module.MAX_DIFF_LINES = 2
    payload = json.dumps({"verdict": "safe", "risk": "low", "summary": "looks fine"})
    with mock.patch.object(module, "call_model", return_value=payload):
        result = module.review("a\nb\nc\nd", _meta(), api_key="k", model="m", base_url="u")

    assert result["verdict"] == "needs_review"
    assert result["truncated"] is True


def test_a_safe_verdict_survives_when_the_diff_was_fully_read() -> None:
    module = _module()
    payload = json.dumps({"verdict": "safe", "risk": "low", "summary": "ok", "concerns": []})
    with mock.patch.object(module, "call_model", return_value=payload):
        result = module.review("diff", _meta(), api_key="k", model="m", base_url="u")

    assert result["verdict"] == "safe"
    assert result["truncated"] is False


# ---------------------------------------------------------------- rendering


def test_comment_states_the_disclaimer_and_concerns() -> None:
    module = _module()
    result = module.normalise(
        {
            "verdict": "malicious",
            "risk": "high",
            "summary": "外传数据",
            "concerns": [{"file": "a.py", "why": "读取 ~/.ssh 并发往外部"}],
        }
    )
    comment = module.render_comment({**result, "truncated": False, "degraded": False}, _meta())

    assert "疑似恶意" in comment
    assert "a.py" in comment
    assert "本评论由 AI 生成" in comment


# ---------------------------------------------------------------- entrypoint


def test_missing_api_key_reports_rather_than_passing(tmp_path, monkeypatch, capsys) -> None:
    module = _module()
    diff = tmp_path / "pr.diff"
    diff.write_text("+ hello", encoding="utf-8")
    comment = tmp_path / "comment.md"
    output = tmp_path / "out.txt"

    monkeypatch.delenv("DEEPSEEK_API_KEY", raising=False)
    monkeypatch.setenv("PR_DIFF_PATH", str(diff))
    monkeypatch.setenv("AI_REVIEW_COMMENT_PATH", str(comment))
    monkeypatch.setenv("GITHUB_OUTPUT", str(output))

    assert module.main() == 0

    assert "DEEPSEEK_API_KEY" in comment.read_text(encoding="utf-8")
    assert "verdict=needs_review" in output.read_text(encoding="utf-8")


# ---------------------------------------------------------------- retry budget


def _empty(module, max_tokens: int):
    return module.EmptyCompletionError(
        finish_reason="length",
        reasoning_tokens=max_tokens,
        completion_tokens=max_tokens,
        max_tokens=max_tokens,
    )


def test_an_exhausted_budget_is_retried_once_with_a_bigger_budget() -> None:
    """The whole point of the fix: one more call, with more room to think."""
    module = _module()
    payload = json.dumps({"verdict": "safe", "risk": "low", "summary": "ok", "concerns": []})
    with mock.patch.object(
        module, "call_model", side_effect=[_empty(module, module.MAX_TOKENS), payload]
    ) as call:
        result = module.review("diff", _meta(), api_key="k", model="m", base_url="u")

    assert result["verdict"] == "safe"
    assert result["degraded"] is False
    assert call.call_count == 2, "只允许重试一次"
    budgets = [item.kwargs["max_tokens"] for item in call.call_args_list]
    assert budgets == [module.MAX_TOKENS, module.RETRY_MAX_TOKENS]
    assert module.RETRY_MAX_TOKENS > module.MAX_TOKENS


def test_both_attempts_exhausted_report_which_budgets_were_tried() -> None:
    """The next person must see the numbers, not 「空内容」 again."""
    module = _module()
    with mock.patch.object(
        module,
        "call_model",
        side_effect=[
            _empty(module, module.MAX_TOKENS),
            _empty(module, module.RETRY_MAX_TOKENS),
        ],
    ):
        result = module.review("diff", _meta(), api_key="k", model="m", base_url="u")

    assert result["verdict"] == "needs_review"
    assert result["degraded"] is True
    assert str(module.MAX_TOKENS) in result["summary"]
    assert str(module.RETRY_MAX_TOKENS) in result["summary"]


def test_an_http_error_is_not_retried() -> None:
    """Retrying 401 spends another request and returns the same 401."""
    module = _module()
    with mock.patch.object(
        module, "call_model", side_effect=module.ReviewError("模型返回 HTTP 401")
    ) as call:
        result = module.review("diff", _meta(), api_key="k", model="m", base_url="u")

    assert result["verdict"] == "needs_review"
    assert call.call_count == 1


def test_empty_content_for_a_non_budget_reason_is_not_retried() -> None:
    """A content filter is not fixed by a bigger budget."""
    module = _module()
    with mock.patch.object(
        module,
        "call_model",
        side_effect=module.ReviewError("模型返回空内容（finish_reason=content_filter）"),
    ) as call:
        result = module.review("diff", _meta(), api_key="k", model="m", base_url="u")

    assert result["verdict"] == "needs_review"
    assert call.call_count == 1


def test_a_successful_retry_does_not_bypass_the_truncation_rule() -> None:
    """Retrying changes the budget, not the rules about what a verdict may claim."""
    module = _module()
    module.MAX_DIFF_LINES = 2
    payload = json.dumps({"verdict": "safe", "risk": "low", "summary": "ok"})
    with mock.patch.object(
        module, "call_model", side_effect=[_empty(module, module.MAX_TOKENS), payload]
    ):
        result = module.review("a\nb\nc\nd", _meta(), api_key="k", model="m", base_url="u")

    assert result["verdict"] == "needs_review"
    assert result["truncated"] is True
