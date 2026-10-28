"""Streaming: the split rules, and the wiring that makes the rules matter.

The aggregator is tested directly because it is pure. The rest is tested through the
real stages, because the interesting failures are wiring failures — a sentence list
that is computed and then never sent, or a reply stage that sends the whole text again
on top of it.
"""

from __future__ import annotations

import pytest

from soapbot.ai.engine import AIEngine
from soapbot.ai.persona import Persona, PersonaStore
from soapbot.ai.stages import ModelStage
from soapbot.ai.streaming import SentenceAggregator
from soapbot.core.adapter import Adapter, AdapterMeta, Capability
from soapbot.core.message import (
    EventType,
    IncomingMessage,
    MessageReceipt,
    MessageScene,
    MessageSegment,
    Sender,
)
from soapbot.core.pipeline import PipelineContext
from soapbot.core.stages import ReplyStage
from soapbot.providers.base import (
    BaseProvider,
    CapabilitySlot,
    ChatResponse,
    ProviderConfig,
    ProviderError,
)
from soapbot.providers.router import ProviderRouter

# ------------------------------------------------------------------ aggregator


def test_splits_on_cjk_enders() -> None:
    agg = SentenceAggregator()
    assert agg.feed("你好。今天", 0.0) == ["你好。"]
    assert agg.feed("天气不错！", 0.1) == ["今天天气不错！"]
    assert agg.pending == ""


def test_keeps_decimal_points_together() -> None:
    """`3.14` must not become two messages; a full stop needs a following space."""
    agg = SentenceAggregator()
    assert agg.feed("圆周率是 3.14 左右", 0.0) == []
    assert agg.flush() == ["圆周率是 3.14 左右"]


def test_first_packet_deadline_breaks_a_stuck_sentence() -> None:
    """Without the deadline a slow model makes time-to-first-message = total time."""
    agg = SentenceAggregator(first_packet_deadline=1.0)
    assert agg.feed("这句话一直没有结束标点", 0.0) == []
    assert agg.feed("还在继续", 0.5) == []
    assert agg.feed("终于", 1.1) == ["这句话一直没有结束标点还在继续终于"]


def test_deadline_applies_to_the_first_packet_only() -> None:
    agg = SentenceAggregator(first_packet_deadline=1.0)
    agg.feed("第一句。", 0.0)
    # Long silence after the first send must not chop the next sentence in half.
    assert agg.feed("第二句还没有标点", 5.0) == []
    assert agg.flush() == ["第二句还没有标点"]


def test_long_sentence_is_cut_at_a_soft_break() -> None:
    agg = SentenceAggregator(max_chars=10, first_packet_deadline=999)
    out = agg.feed("一二三四五，六七八九十，十一十二", 0.0)
    assert out
    assert out[0].endswith("，")
    assert len(out[0]) <= 10


def test_punctuation_only_fragment_is_dropped() -> None:
    agg = SentenceAggregator()
    assert agg.feed("。。。", 0.0) == []
    assert agg.flush() == []


# --------------------------------------------------------------------- doubles


class _Recorder(Adapter):
    meta = AdapterMeta(name="rec", display_name="rec", protocol="test")
    capabilities = frozenset(
        {Capability.TEXT, Capability.REPLY, Capability.PROGRESSIVE}
    )

    def __init__(self) -> None:
        super().__init__()
        self.sent: list[tuple[str, str]] = []

    async def start(self) -> None:  # pragma: no cover - unused
        return None

    async def stop(self) -> None:  # pragma: no cover - unused
        return None

    async def get_self(self):  # pragma: no cover - unused
        return None

    async def send(self, message) -> MessageReceipt:
        body = "".join(seg.plain() for seg in message.segments)
        self.sent.append((body, message.reply_to))
        return MessageReceipt(ok=True)


class _SingleReply(_Recorder):
    """Same adapter without the progressive promise (official-API shape)."""

    capabilities = frozenset({Capability.TEXT, Capability.REPLY})


class _TokenProvider(BaseProvider):
    kind = "fake"
    slots = frozenset({CapabilitySlot.CHAT, CapabilitySlot.STREAM})

    def __init__(
        self,
        pieces: list[str],
        *,
        fail_after: int | None = None,
        provider_id: str = "fake",
    ) -> None:
        # The router keys providers by id, so two doubles sharing an id means the
        # second silently replaces the first — which looks exactly like a failover bug.
        super().__init__(ProviderConfig(id=provider_id, kind="fake", model="fake-model"))
        self.pieces = pieces
        self.fail_after = fail_after
        self.calls = 0

    async def chat(self, request) -> ChatResponse:
        self.calls += 1
        return ChatResponse(content="".join(self.pieces), provider="fake")

    async def stream(self, request):
        self.calls += 1
        for i, piece in enumerate(self.pieces):
            if self.fail_after is not None and i == self.fail_after:
                raise ProviderError("connection reset mid-answer")
            yield piece


class _SilentStream(BaseProvider):
    """Declares streaming but produces nothing — a provider bug, not a user error."""

    kind = "fake"
    slots = frozenset({CapabilitySlot.CHAT, CapabilitySlot.STREAM})

    def __init__(self) -> None:
        super().__init__(ProviderConfig(id="silent", kind="fake", model="m"))

    async def chat(self, request) -> ChatResponse:
        return ChatResponse(content="整段回答", provider="silent")

    async def stream(self, request):
        return
        yield  # unreachable; makes this a generator function


class _ChatOnly(BaseProvider):
    """Declares no streaming and has no callable stream: the router must cope."""

    kind = "fake"
    slots = frozenset({CapabilitySlot.CHAT})
    stream = None  # type: ignore[assignment]

    def __init__(self) -> None:
        super().__init__(ProviderConfig(id="chatty", kind="fake", model="m"))

    async def chat(self, request) -> ChatResponse:
        return ChatResponse(content="整段回答", provider="chatty")


def _event() -> IncomingMessage:
    return IncomingMessage(
        adapter="onebot11",
        message_id="m1",
        scene=MessageScene.GROUP,
        sender=Sender(user_id="20001", nickname="tester", role="member"),
        segments=[MessageSegment.text("你好")],
        group_id="123456",
        self_id="10000",
        event_type=EventType.MESSAGE,
    )


def _engine(provider: BaseProvider) -> AIEngine:
    router = ProviderRouter()
    router.add(provider)
    personas = PersonaStore()
    personas.add(Persona(id="p1", name="测试"))
    return AIEngine(router=router, personas=personas)


# ---------------------------------------------------------------------- router


async def test_router_falls_back_to_chat_for_a_provider_without_stream() -> None:
    router = ProviderRouter()
    router.add(_ChatOnly())
    pieces = [p async for p in router.stream(_request())]
    assert pieces == ["整段回答"]


async def test_router_does_not_fail_over_after_the_first_token() -> None:
    """Half an answer is already in the group; a second provider would splice it."""
    primary = _TokenProvider(["前半句。", "后半句。"], fail_after=1, provider_id="primary")
    backup = _TokenProvider(["别的回答。"], provider_id="backup")
    router = ProviderRouter()
    router.add(primary)
    router.add(backup)

    seen: list[str] = []
    with pytest.raises(ProviderError):
        async for piece in router.stream(_request()):
            seen.append(piece)
    assert seen == ["前半句。"]
    assert backup.calls == 0


def _request():
    from soapbot.providers.base import ChatMessage, ChatRequest

    return ChatRequest(messages=[ChatMessage(role="user", content="你好")])


# ----------------------------------------------------------------------- stages


async def test_stream_sends_one_message_per_sentence() -> None:
    adapter = _Recorder()
    ctx = PipelineContext(event=_event(), adapter=adapter)
    stage = ModelStage(
        _engine(_TokenProvider(["你好。", "今天天气不错！", "再见。"])),
        streaming=True,
        send_interval=0,
    )

    await stage.run(ctx)
    await ReplyStage().run(ctx)

    assert [body for body, _ in adapter.sent] == ["你好。", "今天天气不错！", "再见。"]
    # Only the first message quotes the triggering message, or the group sees three
    # separate replies instead of one answer.
    assert adapter.sent[0][1] == "m1"
    assert [reply for _, reply in adapter.sent[1:]] == ["", ""]


async def test_reply_stage_does_not_resend_what_was_streamed() -> None:
    adapter = _Recorder()
    ctx = PipelineContext(event=_event(), adapter=adapter)
    stage = ModelStage(
        _engine(_TokenProvider(["第一句。", "第二句。"])), streaming=True, send_interval=0
    )

    await stage.run(ctx)
    await ReplyStage().run(ctx)

    assert len(adapter.sent) == 2
    assert ctx.extras["reply_chunks"] == ["第一句。", "第二句。"]
    assert ctx.extras["send_ok"] is True
    assert ctx.extras["stream"]["first_send_ms"] is not None


async def test_adapter_without_progressive_gets_exactly_one_message() -> None:
    adapter = _SingleReply()
    ctx = PipelineContext(event=_event(), adapter=adapter)
    stage = ModelStage(
        _engine(_TokenProvider(["第一句。", "第二句。"])), streaming=True, send_interval=0
    )

    await stage.run(ctx)
    await ReplyStage().run(ctx)

    assert len(adapter.sent) == 1
    assert adapter.sent[0][0] == "第一句。第二句。"


async def test_mid_stream_failure_keeps_what_was_already_sent() -> None:
    """Re-sending a complete answer on top of a fragment reads as two replies."""
    adapter = _Recorder()
    ctx = PipelineContext(event=_event(), adapter=adapter)
    stage = ModelStage(
        _engine(_TokenProvider(["第一句。", "第二句。"], fail_after=1)),
        streaming=True,
        send_interval=0,
    )

    await stage.run(ctx)
    await ReplyStage().run(ctx)

    assert [body for body, _ in adapter.sent] == ["第一句。"]
    assert ctx.extras["stream"]["interrupted"] is True
    assert ctx.extras["send_error"]


async def test_stream_that_produces_nothing_falls_back_to_a_normal_call() -> None:
    adapter = _Recorder()
    ctx = PipelineContext(event=_event(), adapter=adapter)
    engine = _engine(_SilentStream())
    stage = ModelStage(engine, streaming=True, send_interval=0)

    await stage.run(ctx)
    await ReplyStage().run(ctx)

    # The provider's non-streaming answer still reaches the group exactly once.
    assert len(adapter.sent) == 1
    assert ctx.model_reply == "整段回答"
