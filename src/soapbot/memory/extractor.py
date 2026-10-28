"""Memory extraction: decide what is worth remembering.

Two passes, cheap first:

1. **Heuristic** — regexes for names, preferences, dates, explicit "记住". Runs
   on every message, costs nothing, catches the high-value cases.
2. **Model** — optional, batched, only when the heuristic found little and the
   turn looks substantive. Avoids paying an LLM call for every "哈哈".

Without the heuristic gate, a chatty group burns tokens on extraction for every
message and the memory table fills with noise that poisons retrieval. Precision
matters more than recall here: a wrong memory is worse than a missing one,
because it keeps resurfacing.
"""

from __future__ import annotations

import json
import logging
import re
from dataclasses import dataclass, field

from soapbot.memory.store import MemoryLayer

logger = logging.getLogger(__name__)

_EXPLICIT_RE = re.compile(
    r"(?:记住|记一下|别忘|不要忘|帮我记)[：:，,]?\s*(.{2,80})", re.UNICODE
)
_PREFERENCE_RE = re.compile(
    r"我(?:喜欢|讨厌|爱吃|不吃|习惯|想要|希望|不喜欢)\s*(.{1,30})", re.UNICODE
)
_FACT_RE = re.compile(
    r"(?:我叫|我的名字是|我是|我住在|我在)\s*([^\s，。！？,.]{1,20})", re.UNICODE
)
_TIME_RE = re.compile(
    r"(?:生日|纪念日|考试|面试|会议)[是在]?\s*(\d{1,2}\s*月\s*\d{1,2}\s*[日号]|\d{4}-\d{1,2}-\d{1,2})",
    re.UNICODE,
)

_HIGH_VALUE_HINTS = ("记住", "别忘", "我的", "我叫", "我喜欢", "我讨厌", "生日", "重要")

_EXTRACT_PROMPT = """从下面这轮对话中提取值得长期记住的信息（用户偏好、身份事实、明确要求、重要约定）。
只输出 JSON 数组，每项 {{"content": "一句话事实", "layer": "semantic|episodic", "importance": 0.0-1.0}}。
没有值得记住的内容就输出 []。不要编造，不要推测。
对话：
{content}
"""


@dataclass(slots=True)
class ExtractedMemory:
    content: str
    layer: MemoryLayer = MemoryLayer.SEMANTIC
    importance: float = 0.5
    source: str = "heuristic"


@dataclass(slots=True)
class ExtractionResult:
    memories: list[ExtractedMemory] = field(default_factory=list)
    used_model: bool = False
    skipped_reason: str = ""


class MemoryExtractor:
    def __init__(
        self,
        *,
        enable_model: bool = False,
        summarizer=None,
        min_chars: int = 6,
    ) -> None:
        self.enable_model = enable_model
        self._model = summarizer
        self.min_chars = min_chars

    async def extract(
        self, user_text: str, assistant_text: str = "", *, subject: str = ""
    ) -> ExtractionResult:
        result = ExtractionResult()
        if len(user_text.strip()) < self.min_chars:
            result.skipped_reason = "too_short"
            return result

        seen: set[str] = set()

        def add(content: str, importance: float, source: str = "heuristic") -> None:
            text_value = content.strip(" ，。,.")
            if len(text_value) < 2 or text_value in seen:
                return
            seen.add(text_value)
            result.memories.append(
                ExtractedMemory(
                    content=text_value, layer=MemoryLayer.SEMANTIC, importance=importance, source=source
                )
            )

        for match in _EXPLICIT_RE.finditer(user_text):
            add(match.group(1), 0.9)

        for match in _PREFERENCE_RE.finditer(user_text):
            add(f"用户{match.group(0).strip()}", 0.7)

        for match in _FACT_RE.finditer(user_text):
            add(f"用户信息：{match.group(0).strip()}", 0.8)

        for match in _TIME_RE.finditer(user_text):
            add(f"用户提到时间：{match.group(0).strip()}", 0.75)

        # Model pass only when the cheap pass found nothing but the turn looks
        # substantive. This is the cost/recall trade-off made explicit.
        if (
            not result.memories
            and self.enable_model
            and self._model is not None
            and any(h in user_text for h in _HIGH_VALUE_HINTS)
        ):
            try:
                raw = await self._model(
                    _EXTRACT_PROMPT.format(content=f"用户: {user_text}\n助手: {assistant_text}")
                )
                result.used_model = True
                result.memories.extend(_parse_model_output(raw))
            except Exception as exc:
                logger.warning("model memory extraction failed: %s", exc)

        return result


def _parse_model_output(raw: str) -> list[ExtractedMemory]:
    text_value = raw.strip()
    start = text_value.find("[")
    end = text_value.rfind("]")
    if start == -1 or end == -1:
        return []
    try:
        items = json.loads(text_value[start : end + 1])
    except json.JSONDecodeError:
        return []
    out: list[ExtractedMemory] = []
    for item in items if isinstance(items, list) else []:
        if not isinstance(item, dict):
            continue
        content = str(item.get("content", "")).strip()
        if len(content) < 2:
            continue
        layer_raw = str(item.get("layer", "semantic"))
        layer = MemoryLayer.EPISODIC if layer_raw == "episodic" else MemoryLayer.SEMANTIC
        try:
            importance = float(item.get("importance", 0.5))
        except (TypeError, ValueError):
            importance = 0.5
        out.append(
            ExtractedMemory(
                content=content,
                layer=layer,
                importance=max(0.0, min(1.0, importance)),
                source="model",
            )
        )
    return out
