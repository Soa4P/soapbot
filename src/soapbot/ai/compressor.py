"""Context compression.

Goal: keep the prompt inside a hard token budget *without* losing the facts that
matter. Compression is layered, cheapest first:

  1. **Trim**     — hard-drop the oldest turns beyond a turn cap.
  2. **Fold**     — summarise older turns into a rolling summary block.
  3. **Extract**  — pull salient key-facts (names, numbers, preferences) into a
                    compact bullet list when even the summary is too big.
  4. **Shrink**   — replace old image attachments with their cached text
                    descriptions (images are the biggest token sink).
  5. **Budget**   — if still over budget, drop from the middle (keep the first
                    system turn, the most recent N turns, and the summary).

Why not just truncate: truncating mid-conversation destroys referents ("it",
"that thing"), and the model then hallucinates. Folding keeps referents alive.

The compressor is pure w.r.t. the provider: summarisation is injected as a
callable so tests can run without network, and so a cheap model can be used for
summaries while an expensive one handles the actual reply.
"""

from __future__ import annotations

import logging
import re
from collections.abc import Awaitable, Callable
from dataclasses import dataclass, field
from typing import Any

from soapbot.ai.tokens import count_messages, count_tokens

logger = logging.getLogger(__name__)

Summarizer = Callable[[str], Awaitable[str]]


@dataclass(slots=True)
class CompressionConfig:
    max_prompt_tokens: int = 6000
    """Hard ceiling for everything we send to the model."""

    reserve_for_reply: int = 1200
    """Tokens held back so the completion has room to speak."""

    keep_recent_turns: int = 8
    """Turns always preserved verbatim (a 'turn' = one user + one assistant msg)."""

    max_turns: int = 40
    """Absolute cap before folding kicks in."""

    fold_batch_turns: int = 8
    """How many turns to fold into the summary at a time."""

    enable_extraction: bool = True
    enable_image_shrink: bool = True


@dataclass(slots=True)
class CompressionResult:
    messages: list[dict[str, Any]]
    summary: str = ""
    key_facts: list[str] = field(default_factory=list)
    original_tokens: int = 0
    compressed_tokens: int = 0
    folded_turns: int = 0
    dropped_messages: int = 0
    strategy: list[str] = field(default_factory=list)

    @property
    def ratio(self) -> float:
        if self.original_tokens == 0:
            return 1.0
        return round(self.compressed_tokens / self.original_tokens, 3)


_SUMMARY_PROMPT = """请把下面的对话压缩成简洁摘要，保留：
1. 用户的身份、偏好、明确要求
2. 已经达成的结论和承诺
3. 尚未解决的问题
4. 重要的具体事实（数字、名称、时间）
不要编造未出现的信息。用中文，不超过 {limit} 字。

对话：
{content}
"""

_FACT_PATTERNS = [
    re.compile(r"[我你他她它][的叫是住想要喜欢讨厌会能]\S{1,20}"),
    re.compile(r"\d+(?:\.\d+)?\s*(?:岁|元|块|天|小时|分钟|个|次|号|月|年|%|kg|cm)"),
    re.compile(r"(?:记住|别忘|一定要|必须|不要|禁止)[^。！？\n]{1,40}"),
    re.compile(r"[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+"),
]


class ContextCompressor:
    def __init__(
        self,
        config: CompressionConfig | None = None,
        summarizer: Summarizer | None = None,
    ) -> None:
        self.config = config or CompressionConfig()
        self._summarizer = summarizer

    # ------------------------------------------------------------------ public
    async def compress(
        self,
        messages: list[dict[str, Any]],
        *,
        prior_summary: str = "",
    ) -> CompressionResult:
        cfg = self.config
        original = count_messages(messages)
        budget = max(256, cfg.max_prompt_tokens - cfg.reserve_for_reply)

        result = CompressionResult(messages=list(messages), original_tokens=original)
        result.summary = prior_summary
        working = list(messages)

        # 1. shrink image attachments to cached text descriptions (cheapest win)
        if cfg.enable_image_shrink:
            shrunk = self._shrink_images(working)
            if shrunk is not None:
                working = shrunk
                result.strategy.append("image_shrink")

        current = count_messages(working)
        if current <= budget:
            result.messages = working
            result.compressed_tokens = current
            return result

        # 2. fold older turns into a rolling summary.
        # Must run BEFORE any trimming: dropping the oldest turns first would
        # permanently destroy the very facts the summary is supposed to carry.
        working, folded = await self._fold(working, result.summary, budget)
        result.folded_turns += folded
        if folded:
            result.strategy.append("fold")

        # Record the folded summary, but keep the ``_summary`` marker on the
        # message for now: the later trim/drop steps must be able to recognise it
        # and pin it. It is stripped only at the very end.
        for m in working:
            if "_summary" in m:
                result.summary = m["_summary"]
                break
        clean = list(working)
        current = count_messages(clean)

        # 3. hard turn cap, applied after folding so the summary survives
        if len(clean) > cfg.max_turns:
            before = len(clean)
            clean = self._keep_head_and_recent(clean, cfg.max_turns)
            result.strategy.append("trim")
            result.dropped_messages += before - len(clean)
            current = count_messages(clean)

        # 4. extractive key facts when the summary alone is still too fat
        if current > budget and cfg.enable_extraction:
            facts = self.extract_facts(messages)
            if facts:
                fact_block = "已确认的关键事实：\n" + "\n".join(f"- {f}" for f in facts[:20])
                clean = self._inject_system_note(clean, fact_block)
                result.key_facts = facts[:20]
                result.strategy.append("extract")
                current = count_messages(clean)

        # 5. last resort: drop from the middle, keeping recent turns intact
        if current > budget:
            clean = self._drop_middle(clean, budget)
            result.strategy.append("budget")
            current = count_messages(clean)

        clean = [{k: v for k, v in m.items() if k != "_summary"} for m in clean]
        result.messages = clean
        result.compressed_tokens = current
        logger.info(
            "compressed %s -> %s tokens (%.0f%%) strategies=%s folded=%d",
            result.original_tokens,
            result.compressed_tokens,
            result.ratio * 100,
            result.strategy,
            result.folded_turns,
        )
        return result

    # ------------------------------------------------------------------ steps
    def _keep_head_and_recent(self, messages: list[dict[str, Any]], cap: int) -> list[dict[str, Any]]:
        """Keep the leading system prompt, any summary block, and the newest turns.

        The summary block must be preserved explicitly: it has role ``system``
        but is not at index 0, so a naive ``messages[:1]`` slice would silently
        throw away the compressed history we just paid for.
        """
        head: list[dict[str, Any]] = []
        pinned: list[dict[str, Any]] = []
        body: list[dict[str, Any]] = []
        for i, m in enumerate(messages):
            if "_summary" in m:
                pinned.append(m)
            elif i == 0 and m.get("role") == "system":
                head.append(m)
            elif m.get("role") != "system":
                body.append(m)
        return head + pinned + body[-cap:]

    def _shrink_images(self, messages: list[dict[str, Any]]) -> list[dict[str, Any]] | None:
        """Replace image parts in *history* with their text description.

        The most recent user message keeps its image so the model can actually
        see what was just sent; only history is rewritten.
        """
        changed = False
        out: list[dict[str, Any]] = []
        last_user_idx = max(
            (i for i, m in enumerate(messages) if m.get("role") == "user"), default=-1
        )
        for idx, m in enumerate(messages):
            content = m.get("content")
            if idx == last_user_idx or not isinstance(content, list):
                out.append(m)
                continue
            new_parts: list[dict[str, Any]] = []
            for part in content:
                if isinstance(part, dict) and part.get("type") == "image_url":
                    desc = part.get("description") or "[图片：未生成描述]"
                    new_parts.append({"type": "text", "text": str(desc)})
                    changed = True
                else:
                    new_parts.append(part)
            out.append({**m, "content": new_parts})
        return out if changed else None

    async def _fold(
        self, messages: list[dict[str, Any]], summary: str, budget: int
    ) -> tuple[list[dict[str, Any]], int]:
        cfg = self.config
        if self._summarizer is None:
            # No summariser available: fall back to trimming instead of hanging.
            keep = cfg.keep_recent_turns * 2
            if len(messages) <= keep:
                return messages, 0
            folded = len(messages) - keep
            return messages[-keep:], folded

        system = [m for m in messages if m.get("role") == "system"]
        body = [m for m in messages if m.get("role") != "system"]
        keep_recent = cfg.keep_recent_turns * 2
        if len(body) <= keep_recent:
            return messages, 0

        to_fold = body[: len(body) - keep_recent]
        recent = body[len(body) - keep_recent :]
        convo_text = "\n".join(
            f"{m.get('role')}: {_content_text(m.get('content'))}" for m in to_fold
        )
        prompt = _SUMMARY_PROMPT.format(limit=400, content=convo_text[:8000])
        try:
            new_summary = await self._summarizer(prompt)
        except Exception as exc:
            logger.warning("summariser failed, falling back to trim: %s", exc)
            return system + recent, len(to_fold)

        merged = f"{summary}\n{new_summary}".strip() if summary else new_summary.strip()
        summary_msg = {
            "role": "system",
            "content": f"以下是更早对话的摘要（供参考，不要复述）：\n{merged}",
            "_summary": merged,
        }
        rebuilt = [*system, summary_msg, *recent]
        if count_messages(rebuilt) > budget:
            # Folded summary still too big: keep trimming history.
            return [*system, summary_msg, *recent], len(to_fold)
        return rebuilt, len(to_fold)

    def extract_facts(self, messages: list[dict[str, Any]]) -> list[str]:
        """Cheap extractive pass — no model call, so it always works."""
        seen: set[str] = set()
        facts: list[str] = []
        for m in messages:
            if m.get("role") != "user":
                continue
            text = _content_text(m.get("content"))
            for pattern in _FACT_PATTERNS:
                for hit in pattern.findall(text):
                    item = hit.strip()
                    if len(item) < 3 or item in seen:
                        continue
                    seen.add(item)
                    facts.append(item)
                    if len(facts) >= 40:
                        return facts
        return facts

    def _inject_system_note(
        self, messages: list[dict[str, Any]], note: str
    ) -> list[dict[str, Any]]:
        if not messages:
            return [{"role": "system", "content": note}]
        if messages[0].get("role") == "system":
            merged = f"{messages[0].get('content', '')}\n\n{note}"
            return [{**messages[0], "content": merged}] + messages[1:]
        return [{"role": "system", "content": note}, *messages]

    def _drop_middle(self, messages: list[dict[str, Any]], budget: int) -> list[dict[str, Any]]:
        """Keep the system head + pinned summary and newest turns; drop the middle.

        The summary block is pinned here too — dropping it would erase the only
        compressed record of the conversation we are trying to preserve.
        """
        if not messages:
            return messages
        head: list[dict[str, Any]] = []
        pinned: list[dict[str, Any]] = []
        body: list[dict[str, Any]] = []
        for i, m in enumerate(messages):
            if "_summary" in m:
                pinned.append(m)
            elif i == 0 and m.get("role") == "system":
                head.append(m)
            elif m.get("role") != "system":
                body.append(m)
        prefix = head + pinned
        lo, hi = 0, len(body)
        # Binary search for the largest suffix that fits.
        while lo < hi:
            mid = (lo + hi) // 2
            candidate = prefix + body[mid:]
            if count_messages(candidate) <= budget:
                hi = mid
            else:
                lo = mid + 1
        return prefix + body[lo:]


def _content_text(content: Any) -> str:
    if isinstance(content, str):
        return content
    if isinstance(content, list):
        parts = []
        for p in content:
            if isinstance(p, dict) and p.get("type") == "text":
                parts.append(str(p.get("text", "")))
            elif isinstance(p, dict) and p.get("type") == "image_url":
                parts.append("[图片]")
        return " ".join(parts)
    return str(content)


def estimate_turn_tokens(text: str) -> int:
    return count_tokens(text)
