"""Wave 1 tests: adapter contract, capability degradation, and OneBot mock round-trip.

A6 gate: both adapters share the contract and degrade unsupported segments.
A1 gate (partial): inbound group message -> pipeline -> outbound send.
"""

from __future__ import annotations

import asyncio

from soapbot.adapters.mock_onebot import MockOneBot11Server
from soapbot.adapters.onebot11 import (
    OneBot11Adapter,
    parse_message_array,
    segments_to_message_array,
)
from soapbot.core.adapter import Capability
from soapbot.core.message import (
    MessageScene,
    MessageSegment,
    OutgoingMessage,
    SegmentType,
)


def test_parse_message_array_text_and_image() -> None:
    raw = [
        {"type": "text", "data": {"text": "hello "}},
        {"type": "image", "data": {"url": "https://example.com/a.png"}},
        {"type": "at", "data": {"qq": "10000"}},
    ]
    segs = parse_message_array(raw)
    assert [s.type for s in segs] == [SegmentType.TEXT, SegmentType.IMAGE, SegmentType.AT]
    assert segs[0].plain() == "hello "
    assert segs[1].plain() == "[图片]"


def test_parse_message_array_unknown_type_degrades_to_text() -> None:
    segs = parse_message_array([{"type": "mystery", "data": {"text": "kept"}}])
    assert len(segs) == 1
    assert segs[0].type is SegmentType.TEXT
    assert segs[0].plain() == "kept"


def test_parse_message_array_cq_string_passthrough() -> None:
    segs = parse_message_array("plain CQ string")
    assert len(segs) == 1
    assert segs[0].plain() == "plain CQ string"


def test_segments_to_message_array_roundtrip() -> None:
    segs = [MessageSegment.text("hi"), MessageSegment.image(url="http://x/y.png")]
    array = segments_to_message_array(segs)
    assert array[0] == {"type": "text", "data": {"text": "hi"}}
    assert array[1]["type"] == "image"


def test_onebot_adapter_declares_full_capabilities() -> None:
    adapter = OneBot11Adapter(account_id="1")
    assert adapter.supports(Capability.MARKDOWN) is False
    assert adapter.supports(Capability.AT) is True
    assert adapter.supports(Capability.FORWARD) is True
    assert adapter.supports(Capability.MUTE) is True


def test_adapter_degrades_unsupported_segment_to_text() -> None:
    """A6: degradation path must produce a deliverable message."""

    class NarrowAdapter(OneBot11Adapter):
        capabilities = frozenset({Capability.TEXT})

    adapter = NarrowAdapter(account_id="1")
    out = adapter.degrade(
        [MessageSegment.text("ok "), MessageSegment.image(url="http://x/y.png")]
    )
    assert all(s.type is SegmentType.TEXT for s in out)
    assert out[0].plain() == "ok "
    assert out[1].plain() == "[图片]"


def test_adapter_degrades_to_never_empty() -> None:
    class NoCapAdapter(OneBot11Adapter):
        capabilities = frozenset()

    adapter = NoCapAdapter(account_id="1")
    out = adapter.degrade([MessageSegment.image(url="http://x/y.png")])
    assert len(out) == 1
    assert out[0].type is SegmentType.TEXT


async def test_onebot_full_roundtrip_send() -> None:
    """A1: real WebSocket round-trip against the mock protocol implementation."""
    server = MockOneBot11Server()
    await server.start()
    adapter = OneBot11Adapter(account_id="10000", mode="forward", ws_url=server.url)

    received: list = []
    adapter.on_event(lambda e: _collect(e, received))

    await adapter.start()
    await server.wait_connected()

    me = await adapter.get_self()
    assert me.self_id == "10000"
    assert me.nickname == "soapbot-mock"

    await server.push_group_message(text="hello bot")
    for _ in range(50):
        if received:
            break
        await asyncio.sleep(0.02)
    assert len(received) == 1
    event = received[0]
    assert event.scene is MessageScene.GROUP
    assert event.group_id == "123456"
    assert event.text == "hello bot"
    assert event.session_key == "onebot11:group:123456"

    receipt = await adapter.send(
        OutgoingMessage(
            scene=MessageScene.GROUP,
            segments=[MessageSegment.text("pong")],
            group_id="123456",
        )
    )
    assert receipt.ok is True
    assert server.last_sent_text() == "pong"

    await adapter.stop()
    await server.stop()


async def test_guild_message_is_ignored() -> None:
    """频道功能明确不实现：guild 事件必须被丢弃。"""
    server = MockOneBot11Server()
    await server.start()
    adapter = OneBot11Adapter(account_id="10000", mode="forward", ws_url=server.url)
    received: list = []
    adapter.on_event(lambda e: _collect(e, received))
    await adapter.start()
    await server.wait_connected()

    await server.push_guild_message(text="guild msg")
    await asyncio.sleep(0.1)
    assert received == []

    await adapter.stop()
    await server.stop()


async def test_private_message_session_key() -> None:
    server = MockOneBot11Server()
    await server.start()
    adapter = OneBot11Adapter(account_id="10000", mode="forward", ws_url=server.url)
    received: list = []
    adapter.on_event(lambda e: _collect(e, received))
    await adapter.start()
    await server.wait_connected()

    await server.push_private_message(user_id="30001", text="dm")
    for _ in range(50):
        if received:
            break
        await asyncio.sleep(0.02)
    assert received[0].scene is MessageScene.PRIVATE
    assert received[0].session_key == "onebot11:private:30001"

    await adapter.stop()
    await server.stop()


async def _collect(event, bucket: list) -> None:
    bucket.append(event)
