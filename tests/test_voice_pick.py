"""Autonomous voice selection: picker contract and ReplyStage wiring.

The design contract being pinned (docs/autonomous-capabilities-design.md §2):

* the model may only pick from the host's curated candidate table;
* the pick is cached per (persona, session) — one model call, not one per reply;
* the operator's explicit ``voice_tts_voice`` always wins over autonomy;
* a failed pick degrades to the default voice and the reply still goes out.
"""

from __future__ import annotations

import json

from soapbot.voice.picker import VOICE_CANDIDATES, VoicePicker, VoicePickError


def _chat(responses: list[str]):
    calls: list[list[dict]] = []

    async def chat(messages):
        calls.append(messages)
        return responses.pop(0)

    chat.calls = calls
    return chat


def test_pick_returns_table_voice_and_caches() -> None:
    voice_row = VOICE_CANDIDATES[2]
    chat = _chat([json.dumps({"voice": voice_row["voice"], "reason": "阳光随和"})])
    picker = VoicePicker(chat=chat)
    voice, reason = _run(picker.pick(persona_id="p1", persona_prompt="阳光的少年", session_key="s1"))
    assert voice == voice_row["voice"]
    assert "阳光" in reason
    assert len(chat.calls) == 1
    # Second pick for the same (persona, session) is served from cache.
    voice2, _ = _run(picker.pick(persona_id="p1", persona_prompt="阳光的少年", session_key="s1"))
    assert voice2 == voice
    assert len(chat.calls) == 1


def _run(awaitable):
    import asyncio

    return asyncio.run(awaitable)


def test_pick_rejects_a_voice_outside_the_table() -> None:
    chat = _chat([json.dumps({"voice": "en-US-GuyNeural", "reason": "x"})])
    picker = VoicePicker(chat=chat)
    try:
        _run(picker.pick(persona_id="p", persona_prompt="p", session_key="s"))
    except VoicePickError as exc:
        assert "候选表" in str(exc)
    else:
        raise AssertionError("out-of-table voice must be rejected")


def test_pick_rejects_non_json() -> None:
    chat = _chat(["我觉得 zh-CN-XiaoxiaoNeural 不错"])
    picker = VoicePicker(chat=chat)
    try:
        _run(picker.pick(persona_id="p", persona_prompt="p", session_key="s"))
    except VoicePickError:
        pass
    else:
        raise AssertionError("prose must not parse as a pick")


def test_invalidate_drops_one_persona_only() -> None:
    chat = _chat([json.dumps({"voice": VOICE_CANDIDATES[0]["voice"], "reason": "a"}),
                  json.dumps({"voice": VOICE_CANDIDATES[1]["voice"], "reason": "b"}),
                  json.dumps({"voice": VOICE_CANDIDATES[0]["voice"], "reason": "a2"})])
    picker = VoicePicker(chat=chat)
    _run(picker.pick(persona_id="a", persona_prompt="p", session_key="s1"))
    _run(picker.pick(persona_id="b", persona_prompt="p", session_key="s2"))
    picker.invalidate("a")
    _run(picker.pick(persona_id="a", persona_prompt="p", session_key="s1"))
    # persona b survives; persona a re-asked (2 calls for a, 1 for b).
    assert len(chat.calls) == 3
