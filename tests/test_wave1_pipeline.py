"""Wave 1 tests: deterministic pipeline gates (dedup / whitelist / wake / sanitize).

These are the群聊安全 checks that must not depend on the model behaving.
"""

from __future__ import annotations

import pytest

from soapbot.adapters.onebot11 import OneBot11Adapter
from soapbot.core.message import (
    EventType,
    IncomingMessage,
    MessageScene,
    MessageSegment,
    SegmentType,
    Sender,
)
from soapbot.core.pipeline import Pipeline, PipelineContext
from soapbot.core.stages import (
    AccessPolicy,
    DedupStage,
    SanitizeStage,
    StripWakeWordStage,
    WakeStage,
    WhitelistStage,
)


def make_event(
    *,
    text: str = "hi",
    group_id: str = "123456",
    user_id: str = "20001",
    scene: MessageScene = MessageScene.GROUP,
    segments: list[MessageSegment] | None = None,
    message_id: str = "m1",
    role: str = "member",
) -> IncomingMessage:
    return IncomingMessage(
        adapter="onebot11",
        message_id=message_id,
        scene=scene,
        sender=Sender(user_id=user_id, nickname="tester", role=role),
        segments=segments or [MessageSegment.text(text)],
        group_id=group_id if scene is MessageScene.GROUP else "",
        self_id="10000",
        event_type=EventType.MESSAGE,
    )


def make_ctx(event: IncomingMessage) -> PipelineContext:
    adapter = OneBot11Adapter(account_id="10000")
    return PipelineContext(event=event, adapter=adapter)


# ---------------------------------------------------------------- whitelist
async def test_whitelist_allows_when_empty() -> None:
    ctx = make_ctx(make_event())
    result = await WhitelistStage().run(ctx)
    assert result.halt is False


async def test_whitelist_blocks_group_not_listed() -> None:
    policy = AccessPolicy(group_allowlist={"999"})
    ctx = make_ctx(make_event(group_id="123456"))
    result = await WhitelistStage(policy).run(ctx)
    assert result.halt is True
    assert result.reason == "group_not_allowed"


async def test_whitelist_allows_listed_group() -> None:
    policy = AccessPolicy(group_allowlist={"123456"})
    ctx = make_ctx(make_event(group_id="123456"))
    assert (await WhitelistStage(policy).run(ctx)).halt is False


async def test_whitelist_blacklist_user_wins() -> None:
    policy = AccessPolicy(group_allowlist={"123456"}, user_blacklist={"20001"})
    ctx = make_ctx(make_event())
    result = await WhitelistStage(policy).run(ctx)
    assert result.halt is True
    assert result.reason == "user_blacklisted"


async def test_whitelist_private_not_listed_blocked() -> None:
    policy = AccessPolicy(private_allowlist={"30001"})
    ctx = make_ctx(make_event(scene=MessageScene.PRIVATE, user_id="20001"))
    result = await WhitelistStage(policy).run(ctx)
    assert result.halt is True
    assert result.reason == "private_not_allowed"


# ---------------------------------------------------------------- wake
async def test_wake_private_always_woken() -> None:
    ctx = make_ctx(make_event(scene=MessageScene.PRIVATE))
    assert (await WakeStage().run(ctx)).halt is False
    assert ctx.extras["wake_reason"] == "private"


async def test_wake_group_requires_at_or_word() -> None:
    ctx = make_ctx(make_event(text="just chatting"))
    result = await WakeStage().run(ctx)
    assert result.halt is True
    assert result.reason == "not_woken"


async def test_wake_group_by_at_segment() -> None:
    segments = [MessageSegment.at("10000"), MessageSegment.text(" hello")]
    ctx = make_ctx(make_event(segments=segments))
    assert (await WakeStage().run(ctx)).halt is False
    assert ctx.extras["wake_reason"] == "at"


async def test_wake_group_by_wake_word() -> None:
    ctx = make_ctx(make_event(text="soapbot 你好"))
    assert (await WakeStage().run(ctx)).halt is False
    assert "wake_word" in ctx.extras["wake_reason"]


async def test_wake_at_other_user_does_not_wake() -> None:
    segments = [MessageSegment.at("99999"), MessageSegment.text(" hey")]
    ctx = make_ctx(make_event(segments=segments))
    assert (await WakeStage().run(ctx)).halt is True


# ---------------------------------------------------------------- strip + sanitize
async def test_strip_wake_removes_at_and_word() -> None:
    segments = [MessageSegment.at("10000"), MessageSegment.text("soapbot 讲个笑话")]
    event = make_event(segments=segments)
    ctx = make_ctx(event)
    await StripWakeWordStage(wake_words=["soapbot"]).run(ctx)
    cleaned = ctx.extras["clean_segments"]
    assert all(s.type is not SegmentType.AT for s in cleaned)
    assert "".join(s.plain() for s in cleaned).strip() == "讲个笑话"


@pytest.mark.parametrize("prefix", ["/", "!", "／", "！"])
async def test_strip_wake_never_removes_a_command_prefix(prefix: str) -> None:
    """``/`` is a legal wake word, and stripping it silently disables every command.

    The failure is well hidden: ``/budget`` becomes ``budget``, ``CommandStage``
    stops recognising it, and the run ends with an empty reply — which reads like
    a model problem rather than a configuration one. A deployment that adds ``/``
    to its wake words would lose ``/recall``, ``/kb`` and the rest with no error.
    """
    event = make_event(segments=[MessageSegment.text(f"{prefix}budget 25 书")])
    ctx = make_ctx(event)
    await StripWakeWordStage(wake_words=[prefix, "soapbot"]).run(ctx)
    cleaned = "".join(s.plain() for s in ctx.extras["clean_segments"])
    assert cleaned.startswith(prefix), f"command prefix {prefix!r} was stripped"
    assert "budget" in cleaned


async def test_strip_wake_still_removes_a_normal_wake_word() -> None:
    """The guard above must not disable the actual stripping behaviour."""
    event = make_event(segments=[MessageSegment.text("soapbot 你好")])
    ctx = make_ctx(event)
    await StripWakeWordStage(wake_words=["/", "soapbot"]).run(ctx)
    cleaned = "".join(s.plain() for s in ctx.extras["clean_segments"])
    assert cleaned.strip() == "你好"


async def test_sanitize_strips_zero_width_and_truncates() -> None:
    text = "a\u200bb\u200d" + "x" * 5000
    ctx = make_ctx(make_event(text=text))
    await SanitizeStage(max_chars=100).run(ctx)
    cleaned = ctx.extras["clean_segments"]
    out = "".join(s.plain() for s in cleaned)
    assert "\u200b" not in out
    assert "\u200d" not in out
    assert len(out) <= 100
    assert ctx.extras["truncated"] is True


async def test_sanitize_preserves_images_under_budget() -> None:
    segments = [MessageSegment.text("x" * 5000), MessageSegment.image(url="http://a/b.png")]
    ctx = make_ctx(make_event(segments=segments))
    await SanitizeStage(max_chars=50).run(ctx)
    cleaned = ctx.extras["clean_segments"]
    assert any(s.type is SegmentType.IMAGE for s in cleaned)


# ---------------------------------------------------------------- dedup
async def test_dedup_blocks_same_message_id() -> None:
    stage = DedupStage()
    ctx1 = make_ctx(make_event(message_id="dup-1"))
    ctx2 = make_ctx(make_event(message_id="dup-1"))
    assert (await stage.run(ctx1)).halt is False
    result = await stage.run(ctx2)
    assert result.halt is True
    assert result.reason == "duplicate"


async def test_dedup_lru_bounded() -> None:
    stage = DedupStage(capacity=2)
    for i in range(5):
        await stage.run(make_ctx(make_event(message_id=f"m{i}")))
    assert len(stage._seen) == 2


# ---------------------------------------------------------------- pipeline order
async def test_pipeline_halts_at_first_blocking_stage() -> None:
    pipeline = Pipeline([DedupStage(), WhitelistStage(AccessPolicy(user_blacklist={"20001"}))])
    ctx = await pipeline.run(make_ctx(make_event()))
    assert ctx.halted is True
    assert ctx.halt_reason == "user_blacklisted"
    assert "dedup" in ctx.timings
    assert "whitelist" in ctx.timings


async def test_pipeline_records_timings() -> None:
    pipeline = Pipeline([WakeStage()])
    ctx = await pipeline.run(make_ctx(make_event(text="soapbot hi")))
    assert ctx.halted is False
    assert ctx.timings["wake"] >= 0
