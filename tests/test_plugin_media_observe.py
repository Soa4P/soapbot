"""The ``media_observe`` host surface: one-shot image references, never a broadcast.

An event broadcast would hand every message observer a short-lived, often signed
QQ image URL. So the host keeps the reference in memory and an approved plugin
takes it once. These tests pin the three things that make that different from
"just add a field to the payload": capability is separate from ``message``, the
session key is never supplied by the plugin, and no URL reaches a log or audit
line. The last test is the wiring test: the message-hook stage really does put
what the adapter parsed into the inbox.
"""

from __future__ import annotations

from types import SimpleNamespace

import pytest

from soapbot.core.message import (
    EventType,
    IncomingMessage,
    MessageScene,
    MessageSegment,
    SegmentType,
    Sender,
)
from soapbot.core.pipeline import PipelineContext
from soapbot.plugins.context import CallerContext, PluginContext, bind_caller
from soapbot.plugins.manifest import SENSITIVE_CAPABILITIES, Capability
from soapbot.plugins.media_inbox import (
    MAX_IMAGES_PER_MESSAGE,
    MEDIA_INBOX,
    MediaInbox,
)
from soapbot.plugins.sandbox import CapabilityDeniedError, CapabilityGrant, CapabilityGuard
from soapbot.plugins.supervisor import ALLOWED_SURFACES, arg_violation

IMAGE_URL = "https://qq.example.com/once?sig=abcdef"


@pytest.fixture(autouse=True)
def _clear_inbox():
    MEDIA_INBOX.clear()
    yield
    MEDIA_INBOX.clear()


def _caller(session_key: str = "onebot11:group:1") -> CallerContext:
    return CallerContext(
        user_id="20001",
        display_name="tester",
        role="member",
        session_key=session_key,
        scene="group",
        group_id="1",
    )


def _guard(*caps: Capability) -> tuple[CapabilityGuard, list[dict]]:
    entries: list[dict] = []

    class _Audit:
        def record(self, **kwargs):
            entries.append(kwargs)

    grant = CapabilityGrant(
        plugin="p", declared=frozenset(caps), approved=frozenset(caps)
    )
    return CapabilityGuard(grant, audit=_Audit()), entries


def _event(*segments: MessageSegment) -> IncomingMessage:
    return IncomingMessage(
        adapter="onebot11",
        message_id="m1",
        scene=MessageScene.GROUP,
        sender=Sender(user_id="20001", nickname="tester", role="member"),
        segments=list(segments) or [MessageSegment.text("hi")],
        group_id="123456",
        self_id="10000",
        event_type=EventType.MESSAGE,
    )


# ------------------------------------------------------------------ the inbox

def test_only_http_references_cross_the_boundary() -> None:
    box = MediaInbox(clock=lambda: 0.0)
    segments = [
        MessageSegment.image(url=IMAGE_URL),
        MessageSegment.image(b64="iVBORw0KGgo="),  # content, not a reference
        MessageSegment(SegmentType.IMAGE, {"path": "/tmp/attacker-controlled.png"}),
        MessageSegment(SegmentType.IMAGE, {"file": "https://cdn.example.com/b.png"}),
        MessageSegment.text("[图片]"),
    ]
    assert box.put("onebot11:group:1", segments) == 2
    assert box.take("onebot11:group:1") == [
        {"url": IMAGE_URL},
        {"url": "https://cdn.example.com/b.png"},
    ]


def test_taking_is_one_shot_and_scoped_to_the_session() -> None:
    box = MediaInbox(clock=lambda: 0.0)
    box.put("onebot11:group:1", [MessageSegment.image(url=IMAGE_URL)])
    assert box.take("onebot11:group:2") == []
    assert box.take("onebot11:group:1") == [{"url": IMAGE_URL}]
    assert box.take("onebot11:group:1") == []


def test_a_text_only_message_does_not_clear_the_picture() -> None:
    """/meme-save is a *separate* text message after the picture was sent."""
    box = MediaInbox(clock=lambda: 0.0)
    box.put("onebot11:group:1", [MessageSegment.image(url=IMAGE_URL)])
    assert box.put("onebot11:group:1", [MessageSegment.text("/meme-save")]) == 0
    assert box.take("onebot11:group:1") == [{"url": IMAGE_URL}]


def test_references_expire() -> None:
    now = [0.0]
    box = MediaInbox(ttl_seconds=30.0, clock=lambda: now[0])
    box.put("onebot11:group:1", [MessageSegment.image(url=IMAGE_URL)])
    now[0] = 31.0
    assert box.take("onebot11:group:1") == []


def test_one_message_cannot_fill_the_inbox() -> None:
    box = MediaInbox(clock=lambda: 0.0)
    segments = [
        MessageSegment.image(url=f"https://qq.example.com/{i}.png")
        for i in range(MAX_IMAGES_PER_MESSAGE + 5)
    ]
    assert box.put("onebot11:group:1", segments) == MAX_IMAGES_PER_MESSAGE
    assert len(box.take("onebot11:group:1")) == MAX_IMAGES_PER_MESSAGE


def test_a_mutated_result_is_not_a_live_view_of_host_state() -> None:
    box = MediaInbox(clock=lambda: 0.0)
    box.put("onebot11:group:1", [MessageSegment.image(url=IMAGE_URL)])
    taken = box.take("onebot11:group:1")
    taken[0]["url"] = "https://evil.example.com/"
    box.put("onebot11:group:1", [MessageSegment.image(url=IMAGE_URL)])
    assert box.take("onebot11:group:1") == [{"url": IMAGE_URL}]


# ------------------------------------------------------------------ capability

def test_media_observe_is_a_separate_sensitive_capability() -> None:
    assert Capability.MEDIA_OBSERVE != Capability.MESSAGE
    assert Capability.MEDIA_OBSERVE in SENSITIVE_CAPABILITIES


def test_the_surface_is_allowlisted_and_routed() -> None:
    from soapbot.plugins.surfaces import _SURFACE_TABLE

    assert "media.observe" in ALLOWED_SURFACES
    assert "media.observe" in _SURFACE_TABLE


def test_the_plugin_cannot_supply_a_session_key() -> None:
    assert "session_key" in arg_violation(
        "media.observe", {"session_key": "onebot11:group:999"}
    )
    assert arg_violation("media.observe", {}) == frozenset()


async def test_the_surface_uses_the_host_caller_and_audits_a_count_only() -> None:
    from soapbot.plugins.surfaces import SurfaceRouter

    guard, entries = _guard(Capability.MEDIA_OBSERVE)
    MEDIA_INBOX.put("onebot11:group:1", [MessageSegment.image(url=IMAGE_URL)])
    router = SurfaceRouter(guard=guard, plugin="p", audit=_AuditRecorder(entries))
    result = await router.dispatch("media.observe", {}, _caller())

    assert result == {"images": [{"url": IMAGE_URL}]}
    assert IMAGE_URL not in str(entries)
    assert any("count=1" in str(e.get("detail")) for e in entries)


async def test_a_plain_message_observer_cannot_take_images() -> None:
    from soapbot.plugins.surfaces import SurfaceRouter

    guard, _ = _guard(Capability.MESSAGE)
    router = SurfaceRouter(guard=guard, plugin="p")
    with pytest.raises(CapabilityDeniedError):
        await router.dispatch("media.observe", {}, _caller())


async def test_without_a_bound_caller_the_surface_refuses() -> None:
    from soapbot.plugins.surfaces import SurfaceRouter

    guard, _ = _guard(Capability.MEDIA_OBSERVE)
    router = SurfaceRouter(guard=guard, plugin="p")
    with pytest.raises(PermissionError):
        await router.dispatch("media.observe", {}, None)


async def test_in_process_context_takes_once_with_a_bound_caller() -> None:
    guard, _ = _guard(Capability.MEDIA_OBSERVE)
    ctx = PluginContext(plugin="p", guard=guard)
    MEDIA_INBOX.put("onebot11:group:1", [MessageSegment.image(url=IMAGE_URL)])
    with bind_caller(_caller()):
        assert await ctx.observe_images() == [{"url": IMAGE_URL}]
        assert await ctx.observe_images() == []


async def test_in_process_context_refuses_without_the_capability() -> None:
    guard, _ = _guard(Capability.MESSAGE)
    ctx = PluginContext(plugin="p", guard=guard)
    with bind_caller(_caller()), pytest.raises(CapabilityDeniedError):
        await ctx.observe_images()


async def test_in_process_context_refuses_without_a_bound_caller() -> None:
    guard, _ = _guard(Capability.MEDIA_OBSERVE)
    ctx = PluginContext(plugin="p", guard=guard)
    with pytest.raises(RuntimeError):
        await ctx.observe_images()


# ------------------------------------------------------------------ wiring

async def test_the_message_hook_stage_feeds_the_inbox() -> None:
    """Adapter segment -> pipeline -> hook stage -> inbox -> plugin.

    Without this, the capability would be a tested API with nothing writing to
    it: the exact "wired capability equals an existing capability" failure mode.
    """
    from soapbot.plugins.dispatch import PluginMessageHookStage

    loaded = SimpleNamespace(
        context=SimpleNamespace(_message_hooks=[], _event_handlers={}),
        name="p",
    )
    loader = SimpleNamespace(loaded={"p": loaded})
    stage = PluginMessageHookStage(loader)
    event = _event(MessageSegment.image(url=IMAGE_URL), MessageSegment.text("look"))
    await stage.run(PipelineContext(event=event, adapter=None))
    assert MEDIA_INBOX.take(event.session_key) == [{"url": IMAGE_URL}]


class _AuditRecorder:
    def __init__(self, entries: list[dict]) -> None:
        self._entries = entries

    def record(self, **kwargs) -> None:
        self._entries.append(kwargs)
