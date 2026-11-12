"""Autonomous voice selection: the bot picks its own TTS timbre.

Design contract (docs/autonomous-capabilities-design.md §2, implemented here):

* **决策在管线内，不在插件里**。音色是宿主语音面的一部分；插件申请不到它。
* **候选集是宿主给的**：一张精选的 edge-tts 中文音色表（离线常量，不联网拉取），
  每项带一句「气质」描述。模型只能从表里挑，不能捏造音色名——捏造的名字会在
  合成时被 edge-tts 拒绝，但在挑选阶段就应当失败并回退。
* **模型只挑一次**：结果按 (persona_id, session_key) 缓存；同会话同人格的后续
  语音回复复用，人格卡变更或手动指定优先时失效。成本 ≤ 一次轻量对话。
* **操作者手动指定优先**：``settings.voice_tts_voice`` 是操作者的显式决定；
  只有当它仍是出厂默认值时，人格卡的 ``voice_self_select`` 才生效。
* **失败回退**：模型超时/返回非法 JSON/挑了表外音色 → 用出厂默认音色，本次
  语音回复照常发生。挑选失败不能让回复消失。
* **可审计**：挑选结果与理由进 trace（voice_reply extras 扩展为
  ``"voice:<音色>:<picker|operator|default>"``）。
"""

from __future__ import annotations

import json
import logging
from typing import Any

logger = logging.getLogger(__name__)

#: 出厂默认音色。与 settings.voice_tts_voice 的默认值保持一致：只有操作者没有
#: 显式改过它时，自主挑选才生效。
DEFAULT_VOICE = "zh-CN-XiaoxiaoNeural"

#: 精选候选表。全部是 edge-tts 长期稳定的 zh-CN 音色；「气质」一句话写给模型看。
#: 刻意是离线常量：联网拉全量音色表（数百项）会把挑选变成一次大上下文调用，
#: 且表内容不受本仓库控制。
VOICE_CANDIDATES: tuple[dict[str, str], ...] = (
    {"voice": "zh-CN-XiaoxiaoNeural", "气质": "温柔亲和，日常陪伴感"},
    {"voice": "zh-CN-XiaoyiNeural", "气质": "活泼轻快，少女感"},
    {"voice": "zh-CN-YunxiNeural", "气质": "年轻男性，阳光随和"},
    {"voice": "zh-CN-YunyangNeural", "气质": "成熟男性，稳重专业"},
    {"voice": "zh-CN-YunjianNeural", "气质": "浑厚男性，硬朗有力"},
    {"voice": "zh-CN-XiaohanNeural", "气质": "冷静沉稳，偏中性"},
    {"voice": "zh-CN-XiaomoNeural", "气质": "低沉慵懒，叙事感"},
    {"voice": "zh-CN-XiaoxuanNeural", "气质": "清亮知性，优雅"},
    {"voice": "zh-CN-XiaorouNeural", "气质": "柔和细腻，耐心"},
    {"voice": "zh-CN-YunfengNeural", "气质": "老成平和，长辈感"},
)

PROMPT = """你在为一个聊天机器人的语音回复挑选音色。

这个机器人的人格描述：
{persona}

它即将对话的场景：
{context}

候选音色（只能从这个表里选，voice 字段原样返回）：
{candidates}

只输出一个 JSON 对象：
{{"voice": "表中的 voice 原文", "reason": "一句话理由"}}

判断标准：音色气质与人格描述一致；不要因为「听起来专业」而选与人格冲突的。
"""


class VoicePickError(RuntimeError):
    """The model could not make a valid pick; callers fall back to the default."""


class VoicePicker:
    """One model call per (persona, session), then cached."""

    def __init__(self, *, chat, max_cache: int = 500) -> None:
        self._chat = chat
        self._cache: dict[tuple[str, str], tuple[str, str]] = {}
        self._max_cache = max_cache

    async def pick(
        self,
        *,
        persona_id: str,
        persona_prompt: str,
        session_key: str,
        recent_context: str = "",
    ) -> tuple[str, str]:
        """Return ``(voice, reason)``. Never raises for model-side failures."""
        key = (persona_id, session_key)
        cached = self._cache.get(key)
        if cached:
            return cached
        candidates = "\n".join(
            f"- {row['voice']}：{row['气质']}" for row in VOICE_CANDIDATES
        )
        prompt = PROMPT.format(
            persona=persona_prompt[:1500] or "（无人格描述）",
            context=recent_context[:800] or "（无近期上下文）",
            candidates=candidates,
        )
        voice, reason = await self._ask(prompt)
        if len(self._cache) >= self._max_cache:
            self._cache.clear()
        self._cache[key] = (voice, reason)
        return voice, reason

    async def _ask(self, prompt: str) -> tuple[str, str]:
        response = await self._chat(
            [
                {"role": "system", "content": "你是音色选型助手，只输出 JSON。"},
                {"role": "user", "content": prompt},
            ]
        )
        text = str(response or "").strip()
        try:
            payload = json.loads(text)
        except ValueError as exc:
            raise VoicePickError("模型返回的不是 JSON") from exc
        if not isinstance(payload, dict):
            raise VoicePickError("模型返回的不是 JSON 对象")
        voice = str(payload.get("voice") or "").strip()
        if voice not in {row["voice"] for row in VOICE_CANDIDATES}:
            raise VoicePickError(f"模型挑了候选表之外的音色: {voice!r}")
        reason = str(payload.get("reason") or "")[:200]
        return voice, reason

    def invalidate(self, persona_id: str | None = None) -> None:
        """Drop cache entries, all or one persona's."""
        if persona_id is None:
            self._cache.clear()
        else:
            self._cache = {k: v for k, v in self._cache.items() if k[0] != persona_id}


def build_voice_picker(chat: Any) -> VoicePicker | None:
    """Wire the picker only when a chat transport exists.

    ``chat`` is the provider router's chat callable (same one the pipeline uses);
    tests inject a stub. ``None`` means the feature degrades to the operator's
    configured voice — the pre-existing behaviour.
    """
    if chat is None:
        return None
    return VoicePicker(chat=chat)
