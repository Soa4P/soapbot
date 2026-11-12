"""ReplyStage × autonomous voice selection: who decides the timbre, and what
happens when the decider fails.

Pinned contract (docs/autonomous-capabilities-design.md §2):

* persona ``voice_self_select`` + picker → the picked voice reaches synthesize;
* operator's explicit ``voice_tts_voice`` (≠ factory default) wins — the picker
  is never even called;
* a failed pick degrades to the default voice and the reply still goes out;
* the decision is visible in ``ctx.extras["voice_pick"]``.
"""

from __future__ import annotations

from types import SimpleNamespace

import pytest

from soapbot.core.adapter import Adapter, AdapterMeta, Capability
from soapbot.core.message import MessageReceipt, MessageScene, MessageSegment, SegmentType
from soapbot.core.pipeline import PipelineContext
from soapbot.core.stages import ReplyStage
from soapbot.voice.picker import DEFAULT_VOICE, VOICE_CANDIDATES


class _Adapter(Adapter):
    meta = AdapterMeta(name="rec", display_name="rec", protocol="test")
    capabilities = frozenset({Capability.TEXT, Capability.REPLY, Capability.RECORD})

    def __init__(self) -> None:
        super().__init__()
        self.sent: list = []

    async def start(self):
        return None

    async def stop(self):
        return None

    async def get_self(self):
        return None

    async def send(self, message) -> MessageReceipt:
        self.sent.append(message)
        return MessageReceipt(ok=True)


class _Tts:
    """Records the voice each synthesis actually used."""

    def __init__(self, voice: str = DEFAULT_VOICE) -> None:
        self.voice = voice
        self.used: list[str | None] = []

    async def synthesize(self, text: str, *, voice: str | None = None) -> str:
        self.used.append(voice)
        return "YXVkaW8="


class _PickFail:
    async def pick(self, **kwargs):
        raise RuntimeError("model down")


def _event():
    from soapbot.core.message import IncomingMessage, Sender

    return IncomingMessage(
        adapter="rec",
        message_id="m1",
        scene=MessageScene.GROUP,
        sender=Sender(user_id="u1", nickname="u1"),
        segments=[MessageSegment.text("hi")],
        group_id="123",
    )


def _persona(*, self_select: bool):
    return SimpleNamespace(
        id="default",
        system_prompt="p",
        extra={"voice_self_select": self_select},
    )


def _ctx(persona) -> PipelineContext:
    ctx = PipelineContext(event=_event(), adapter=_Adapter())
    ctx.model_reply = "你好呀"
    ctx.extras["persona"] = persona
    return ctx


def _picker(response: str):
    import json

    async def chat(messages):
        return json.dumps(response)

    from soapbot.voice.picker import VoicePicker

    return VoicePicker(chat=chat)


@pytest.mark.asyncio
async def test_self_select_picks_and_synthesizes_with_it() -> None:
    picked_voice = VOICE_CANDIDATES[1]["voice"]
    tts = _Tts()
    stage = ReplyStage(tts=tts, picker=_picker({"voice": picked_voice, "reason": "活泼"}))
    ctx = _ctx(_persona(self_select=True))
    await stage.run(ctx)
    assert tts.used == [picked_voice]
    assert ctx.extras["voice_pick"] == f"{picked_voice}:self:活泼"
    # The reply still went out as a record segment (audio), not plain text.
    assert ctx.adapter.sent[0].segments[0].type is SegmentType.RECORD


@pytest.mark.asyncio
async def test_operator_voice_wins_over_self_select() -> None:
    custom = VOICE_CANDIDATES[3]["voice"]
    tts = _Tts(voice=custom)  # operator changed the setting away from factory default
    stage = ReplyStage(tts=tts, picker=_picker({"voice": VOICE_CANDIDATES[1]["voice"], "reason": "x"}))
    ctx = _ctx(_persona(self_select=True))
    await stage.run(ctx)
    assert tts.used == [None]  # picker never asked; operator voice applies
    assert "self" not in str(ctx.extras.get("voice_pick", ""))


@pytest.mark.asyncio
async def test_failed_pick_falls_back_and_reply_still_sends() -> None:
    tts = _Tts()
    stage = ReplyStage(tts=tts, picker=_PickFail())
    ctx = _ctx(_persona(self_select=True))
    await stage.run(ctx)
    assert tts.used == [None]
    assert ctx.extras["voice_pick"] == "default:default:"
    # The reply still went out as voice with the default timbre.
    assert ctx.adapter.sent[0].segments[0].type is SegmentType.RECORD


@pytest.mark.asyncio
async def test_no_persona_means_operator_voice() -> None:
    tts = _Tts()
    stage = ReplyStage(tts=tts, picker=_picker({"voice": VOICE_CANDIDATES[1]["voice"], "reason": "x"}))
    ctx = PipelineContext(event=_event(), adapter=_Adapter())
    ctx.model_reply = "你好呀"
    await stage.run(ctx)
    assert tts.used == [None]
