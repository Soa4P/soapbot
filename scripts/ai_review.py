#!/usr/bin/env python3
"""Ask a model to read a pull request and say whether it is safe.

What this is *not*: a gate. The deterministic checks (tests, security boundaries, plugin
IPC, secret scan, the version gate) run first and decide whether the code works. This
runs after them and answers a different question — "does the diff do what its
description says, and does anything in it look hostile" — which no static rule can
answer and no model should be trusted to answer alone. A `safe` verdict here never
authorises a merge on its own; see the workflows for what each repository does with it.

Design constraints, each with a reason:

* **Standard library only.** The job that runs this holds a secret (`pull_request_target`
  is the only trigger that gives fork PRs access to one). Every `pip install` in such a
  job is another chance for a compromised package to read that secret.
* **Never execute the PR.** The workflow checks out the *base* commit and reads the diff
  as text. Anything else would run attacker-controlled code with the secret in scope.
* **Fail closed.** A timeout, a 5xx, an empty body or unparsable JSON yields
  `needs_review`, never `safe`. Silence is not approval.
* **A truncated diff cannot be `safe`.** If the review could not see everything, saying
  "safe" would be a claim about text it never read.

Usage (from a workflow; reads everything from the environment so nothing is interpolated
into a shell):

    python scripts/ai_review.py
"""

from __future__ import annotations

import json
import os
import re
import sys
import urllib.error
import urllib.request
from pathlib import Path

DEFAULT_BASE_URL = "https://api.deepseek.com"
DEFAULT_MODEL = "deepseek-chat"
MAX_DIFF_BYTES = 200_000
MAX_DIFF_LINES = 4_000
REQUEST_TIMEOUT = 60.0

VERDICTS = ("safe", "needs_review", "malicious")
RISKS = ("low", "medium", "high")

SYSTEM_PROMPT = """你是一名代码审查员，判断一个 pull request 是否安全、是否与其描述相符。

只根据给出的 diff 与元数据判断，不要假设仓库里还有别的保护。重点看：

1. 恶意或后门行为：数据外传、隐蔽的网络请求、读取凭据/环境变量、写启动项或计划任务、
   动态执行（eval/exec/__import__）、混淆编码后执行、在正常功能里夹带额外行为。
2. 描述与实现不符：标题说修文档，diff 里改的是权限、依赖或 CI 配置。
3. 供应链风险：新增依赖、修改构建或发布配置、改动签名/校验逻辑。
4. 权限提升：扩大自己的权限、绕过审批、修改封禁或信任列表。
5. 明显的破坏：删除测试、注释掉校验、把失败改成通过。

不要因为代码风格、命名或缺少注释而判定为风险；那些不是安全问题。

只输出一个 JSON 对象，不要输出任何其他文字，格式：

{"verdict": "safe|needs_review|malicious",
 "risk": "low|medium|high",
 "summary": "一到两句中文结论",
 "concerns": [{"file": "路径", "why": "具体原因"}]}

判断标准：
- safe：改动与其描述一致，没有可疑行为。
- needs_review：有需要人确认的地方（含信息不足、被截断、看不懂意图）。
- malicious：明确发现后门、外传、提权或掩盖行为。
concerns 可以为空数组。"""


class ReviewError(RuntimeError):
    """Raised when the model could not be consulted; callers degrade to needs_review."""


def truncate(text: str) -> tuple[str, bool, str]:
    """Bound the input by lines and bytes.

    Returns `(text, was_truncated, what_was_dropped)`. The third value is the point: a
    comment that only says "the diff was truncated" leaves the reader unable to judge how
    much was missed, and "not reviewed" is not the same as "reviewed and fine". Reporting
    the volume lets a maintainer decide whether to look themselves.
    """
    lines = text.splitlines()
    total_lines = len(lines)
    kept = lines[:MAX_DIFF_LINES]
    joined = "\n".join(kept)
    dropped_lines = total_lines - len(kept)

    dropped_bytes = 0
    encoded = joined.encode("utf-8", "replace")
    if len(encoded) > MAX_DIFF_BYTES:
        dropped_bytes = len(encoded) - MAX_DIFF_BYTES
        joined = encoded[:MAX_DIFF_BYTES].decode("utf-8", "ignore")

    parts = []
    if dropped_lines:
        parts.append(f"{dropped_lines} 行")
    if dropped_bytes:
        # Sub-kilobyte remainders would render as "0 KB", which reads like nothing was
        # dropped when something was.
        parts.append(f"{dropped_bytes} 字节" if dropped_bytes < 1024 else f"{dropped_bytes // 1024} KB")
    return joined, bool(parts), " + ".join(parts)


def build_prompt(diff: str, meta: dict, truncated: bool, dropped: str = "") -> str:
    files = meta.get("files", "")
    head = [
        f"标题：{meta.get('title', '(空)')}",
        f"作者：{meta.get('author', '(未知)')}",
        f"变更文件数：{files}",
    ]
    if meta.get("body"):
        body = str(meta["body"])[:2000]
        head.append(f"描述：\n{body}")
    if truncated:
        head.append(
            f"注意：diff 已被截断（未提供 {dropped or '部分内容'}），你看到的不是全部改动。"
            "这种情况下不要给出 safe。"
        )
    head.append("--- diff 开始 ---")
    head.append(diff or "(空 diff)")
    head.append("--- diff 结束 ---")
    return "\n".join(head)


def _extract_json(text: str) -> dict:
    """Tolerate a model that wraps JSON in prose or a fenced block."""
    text = text.strip()
    if text.startswith("```"):
        text = re.sub(r"^```[a-zA-Z]*\s*", "", text)
        text = re.sub(r"\s*```$", "", text)
    try:
        return json.loads(text)
    except json.JSONDecodeError:
        pass
    start, end = text.find("{"), text.rfind("}")
    if start != -1 and end > start:
        try:
            return json.loads(text[start : end + 1])
        except json.JSONDecodeError:
            pass
    # Include a short prefix: "not JSON" alone was unattributable from a CI log, and the
    # difference between prose, a truncated object and a fenced block matters when
    # deciding whether to change the prompt or the token budget.
    raise ReviewError(f"模型没有返回可解析的 JSON（开头：{text[:80]!r}）")


def normalise(payload: dict) -> dict:
    """Coerce a parsed payload into the documented shape, or fail closed."""
    verdict = str(payload.get("verdict", "")).strip().lower()
    risk = str(payload.get("risk", "")).strip().lower()
    if verdict not in VERDICTS:
        raise ReviewError(f"模型返回了未知 verdict: {verdict!r}")
    if risk not in RISKS:
        risk = "medium"

    concerns: list[dict] = []
    for item in payload.get("concerns") or []:
        if isinstance(item, dict):
            file = str(item.get("file", ""))[:200]
            why = str(item.get("why", ""))[:500]
        else:
            file, why = "", str(item)[:500]
        if why:
            concerns.append({"file": file, "why": why})

    return {
        "verdict": verdict,
        "risk": risk,
        "summary": str(payload.get("summary", ""))[:1000],
        "concerns": concerns[:20],
    }


def call_model(prompt: str, *, api_key: str, model: str, base_url: str) -> str:
    # An invisible BOM in the secret surfaces as `UnicodeEncodeError: 'latin-1' codec
    # can't encode characters` from deep inside urllib's header writer, which reads like
    # a model or network failure and sends the investigation the wrong way. It is a
    # secret-configuration problem, so say that here.
    try:
        api_key.encode("ascii")
    except UnicodeEncodeError as exc:
        raise ReviewError(
            f"DEEPSEEK_API_KEY 含非 ASCII 字符（位置 {exc.start}）；"
            "通常是复制或管道传输时带入了 BOM/全角字符"
        ) from exc

    payload = {
        "model": model,
        "messages": [
            {"role": "system", "content": SYSTEM_PROMPT},
            {"role": "user", "content": prompt},
        ],
        # Deterministic: a review that changes with the temperature is not reviewable.
        "temperature": 0,
        # `deepseek-v4-pro` is a reasoning model: `completion_tokens` includes the
        # hidden reasoning, and at 1200 the budget can be consumed before any `content`
        # is produced — which surfaced as "模型响应不是 JSON" with no explanation.
        "max_tokens": 3000,
    }
    request = urllib.request.Request(
        f"{base_url.rstrip('/')}/chat/completions",
        data=json.dumps(payload).encode("utf-8"),
        headers={
            "Content-Type": "application/json",
            "Authorization": f"Bearer {api_key}",
        },
        method="POST",
    )
    try:
        with urllib.request.urlopen(request, timeout=REQUEST_TIMEOUT) as response:
            status = getattr(response, "status", 0)
            raw = response.read()
    except urllib.error.HTTPError as exc:
        # The body of an HTTP error is where a proxy or a WAF explains itself, so it is
        # worth more than the status code. No credential is ever in a response body; the
        # Authorization header is not echoed anywhere.
        snippet = exc.read()[:300].decode("utf-8", "replace")
        raise ReviewError(f"模型返回 HTTP {exc.code}（响应开头：{snippet!r}）") from exc
    except (urllib.error.URLError, TimeoutError, OSError) as exc:
        raise ReviewError(f"无法连接模型：{type(exc).__name__}: {exc}") from exc

    try:
        body = json.loads(raw.decode("utf-8", "replace"))
    except (ValueError, TypeError) as exc:
        # Distinct from "the model's answer is not JSON": here the *transport* answered
        # with something that is not JSON at all (an HTML block page, for instance), and
        # calling that a model problem sent the first investigation in the wrong
        # direction.
        raise ReviewError(f"响应体不是 JSON（HTTP {status}，开头：{raw[:300]!r}）") from exc

    choice = (body.get("choices") or [{}])[0]
    message = choice.get("message") or {}
    content = message.get("content")
    try:
        finish = choice.get("finish_reason", "?")
    except AttributeError:
        finish = "?"
    if not content or not str(content).strip():
        # Say why it was empty. A bare "empty content" made a real CI failure
        # unattributable: it could mean the reasoning budget was exhausted, the request
        # was filtered, or the provider changed its response shape.
        usage = body.get("usage") or {}
        reasoning = (usage.get("completion_tokens_details") or {}).get("reasoning_tokens")
        raise ReviewError(
            f"模型返回空内容（finish_reason={finish}, reasoning_tokens={reasoning}, "
            f"completion_tokens={usage.get('completion_tokens')}）"
        )
    return str(content)


def review(diff: str, meta: dict, *, api_key: str, model: str, base_url: str) -> dict:
    """Return the documented verdict shape. Never raises for model-side failures."""
    clipped, truncated, dropped = truncate(diff)
    prompt = build_prompt(clipped, meta, truncated, dropped)
    try:
        raw = call_model(prompt, api_key=api_key, model=model, base_url=base_url)
        result = normalise(_extract_json(raw))
    except ReviewError as exc:
        return {
            "verdict": "needs_review",
            "risk": "medium",
            "summary": f"自动审查未能完成：{exc}",
            "concerns": [],
            "truncated": truncated,
            "dropped": dropped,
            "degraded": True,
        }

    if truncated and result["verdict"] == "safe":
        # It only saw part of the change; "safe" would be a claim about unread text.
        result["verdict"] = "needs_review"
        result["risk"] = "medium"
        result["summary"] = (result["summary"] + "（diff 已截断，无法确认全部改动）").strip()
    result["truncated"] = truncated
    result["dropped"] = dropped
    result["degraded"] = False
    return result


def render_comment(result: dict, meta: dict) -> str:
    badge = {"safe": "✅ 未发现问题", "needs_review": "⚠️ 需要人工确认", "malicious": "🚫 疑似恶意"}
    lines = [
        f"## {badge.get(result['verdict'], result['verdict'])}",
        "",
        f"**风险等级**：{result['risk']}　**模型**：`{meta.get('model', '')}`",
        "",
        result["summary"] or "(无结论)",
    ]
    if result.get("truncated"):
        # Say how much was skipped. "Truncated" alone reads like a formatting note;
        # "1200 行未审查" is a fact the maintainer can act on.
        dropped = result.get("dropped") or "未知数量"
        lines += [
            "",
            f"> diff 超过审查上限，只看了前面的部分：**{dropped} 未审查**。结论已自动降级为 needs_review。",
        ]
    if result.get("degraded"):
        lines += ["", "> 模型调用失败，本条不是对代码的判断。请人工审查。"]
    if result["concerns"]:
        lines += ["", "### 具体关注点", ""]
        for item in result["concerns"]:
            where = f"`{item['file']}`" if item["file"] else "（未指明文件）"
            lines.append(f"- {where}：{item['why']}")
    lines += [
        "",
        "---",
        "",
        "本评论由 AI 生成，只作参考；合并决定仍由确定性检查与维护者做出。",
    ]
    return "\n".join(lines)


def _write_output(name: str, value: str) -> None:
    target = os.environ.get("GITHUB_OUTPUT")
    if target:
        with open(target, "a", encoding="utf-8") as handle:
            handle.write(f"{name}={value}\n")


def main() -> int:
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")

    api_key = os.environ.get("DEEPSEEK_API_KEY", "").strip()
    if not api_key:
        # Missing secret is a configuration error: report it, but still post a comment so
        # the PR does not silently look "reviewed and fine".
        result = {
            "verdict": "needs_review",
            "risk": "medium",
            "summary": "未配置 DEEPSEEK_API_KEY，本次没有进行自动审查。",
            "concerns": [],
            "truncated": False,
            "degraded": True,
        }
    else:
        diff_path = Path(os.environ.get("PR_DIFF_PATH", "pr.diff"))
        try:
            diff = diff_path.read_text(encoding="utf-8", errors="replace")
        except OSError as exc:
            result = {
                "verdict": "needs_review",
                "risk": "medium",
                "summary": f"读取 diff 失败：{type(exc).__name__}",
                "concerns": [],
                "truncated": False,
                "degraded": True,
            }
        else:
            model = os.environ.get("AI_REVIEW_MODEL", DEFAULT_MODEL)
            base_url = os.environ.get("AI_REVIEW_BASE_URL", DEFAULT_BASE_URL)
            meta = {
                "title": os.environ.get("PR_TITLE", ""),
                "author": os.environ.get("PR_AUTHOR", ""),
                "body": os.environ.get("PR_BODY", ""),
                "files": os.environ.get("PR_FILES", ""),
                "model": model,
            }
            result = review(diff, meta, api_key=api_key, model=model, base_url=base_url)
            result["model"] = model

    meta = {
        "title": os.environ.get("PR_TITLE", ""),
        "author": os.environ.get("PR_AUTHOR", ""),
        "model": result.get("model", os.environ.get("AI_REVIEW_MODEL", DEFAULT_MODEL)),
    }
    comment = render_comment(result, meta)

    out_path = os.environ.get("AI_REVIEW_COMMENT_PATH")
    if out_path:
        Path(out_path).write_text(comment, encoding="utf-8")

    _write_output("verdict", result["verdict"])
    _write_output("risk", result["risk"])
    _write_output("degraded", "true" if result.get("degraded") else "false")
    print(comment)
    return 0


if __name__ == "__main__":
    sys.exit(main())
