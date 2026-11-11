"""OneBot 11 gateway: event shape, action routing, and the listening-socket guards.

The gateway is a new remote surface that can send messages as the bot. These cases
therefore cover both directions and the refusal paths: what an event looks like,
what an action does to the adapter, and what happens when a caller has the wrong
token, an unknown action, or too many calls per minute.

No socket is opened. The server object is exercised through its handler methods
with fake clients, so the suite cannot pass because a port happened to be free.
"""

from __future__ import annotations

import json
from types import SimpleNamespace

import pytest

from soapbot.core.adapter import AccountInfo
from soapbot.core.message import (
    IncomingMessage,
    MessageReceipt,
    MessageScene,
    MessageSegment,
    SegmentType,
    Sender,
)
from soapbot.gateway.actions import ActionError, dispatch
from soapbot.gateway.events import to_event
from soapbot.gateway.onebot11 import GatewayError, OneBot11Gateway
from soapbot.security.ratelimit import SlidingWindowLimiter


class _FakeAdapter:
    def __init__(self, name: str = "qq_official") -> None:
        self.meta = SimpleNamespace(name=name)
        self.health = SimpleNamespace(online=True)
        self.sent = []
        self._handlers = []

    def on_event(self, handler):
        self._handlers.append(handler)

        def _remove() -> None:
            if handler in self._handlers:
                self._handlers.remove(handler)

        return _remove

    async def send(self, message):
        self.sent.append(message)
        return MessageReceipt(ok=True, message_id="OUT-1")

    async def get_self(self):
        return AccountInfo(self_id="BOT", nickname="bot", adapter=self.meta.name)

    def supports_segment(self, seg_type):
        return seg_type in (SegmentType.TEXT, SegmentType.IMAGE)


def _incoming(scene=MessageScene.GROUP) -> IncomingMessage:
    return IncomingMessage(
        adapter="qq_official",
        message_id="MSG-1",
        scene=scene,
        sender=Sender(user_id="USER-1", nickname="nick", card="", role="member"),
        segments=[MessageSegment.at("BOT"), MessageSegment.text("你好")],
        group_id="GROUP-1" if scene is MessageScene.GROUP else "",
        self_id="BOT",
    )


class _FakeWs:
    def __init__(self, *, headers=None, path="", fail_send=False) -> None:
        self.request = SimpleNamespace(headers=headers or {}, path=path)
        self.sent: list[str] = []
        self.closed: list[dict] = []
        self.fail_send = fail_send

    async def send(self, payload) -> None:
        if self.fail_send:
            raise RuntimeError("client gone")
        self.sent.append(payload)

    async def close(self, **kwargs) -> None:
        self.closed.append(kwargs)


def test_group_event_has_group_fields_and_segments() -> None:
    event = to_event(_incoming())

    assert event["post_type"] == "message"
    assert event["message_type"] == "group"
    assert event["sub_type"] == "normal"
    assert event["group_id"] == "GROUP-1"
    assert [seg["type"] for seg in event["message"]] == ["at", "text"]
    assert event["message"][0]["data"]["qq"] == "BOT"
    assert event["sender"]["user_id"] == "USER-1"


def test_private_event_uses_user_id() -> None:
    event = to_event(_incoming(MessageScene.PRIVATE))

    assert event["message_type"] == "private"
    assert event["sub_type"] == "friend"
    assert event["user_id"] == "USER-1"
    assert "group_id" not in event


@pytest.mark.asyncio
async def test_send_group_msg_builds_an_outgoing_message() -> None:
    adapter = _FakeAdapter()
    data = await dispatch(
        adapter,
        "send_group_msg",
        {"group_id": "G", "message": [{"type": "text", "data": {"text": "hi"}}]},
    )

    assert data["message_id"] == "OUT-1"
    sent = adapter.sent[0]
    assert sent.scene is MessageScene.GROUP
    assert sent.group_id == "G"
    assert [seg.type for seg in sent.segments] == ["text"]


@pytest.mark.asyncio
async def test_send_msg_routes_by_message_type() -> None:
    adapter = _FakeAdapter()
    await dispatch(
        adapter,
        "send_msg",
        {"message_type": "private", "user_id": "U", "message": "hi"},
    )

    assert adapter.sent[0].scene is MessageScene.PRIVATE
    assert adapter.sent[0].user_id == "U"


@pytest.mark.asyncio
async def test_unknown_action_is_refused_with_1404() -> None:
    with pytest.raises(ActionError) as raised:
        await dispatch(_FakeAdapter(), "set_group_kick", {})

    assert raised.value.retcode == 1404
    assert "unsupported action" in raised.value.wording


@pytest.mark.asyncio
async def test_login_info_and_version_are_reported() -> None:
    adapter = _FakeAdapter()

    login = await dispatch(adapter, "get_login_info", {})
    version = await dispatch(adapter, "get_version_info", {})

    assert login == {"user_id": "BOT", "nickname": "bot"}
    assert version["protocol_version"] == "v11"
    assert version["adapter"] == "qq_official"


@pytest.mark.asyncio
async def test_can_send_image_reflects_the_adapter_capabilities() -> None:
    adapter = _FakeAdapter()
    image = await dispatch(adapter, "can_send_image", {})
    record = await dispatch(adapter, "can_send_record", {})

    assert image == {"yes": True}
    assert record == {"yes": False}


@pytest.mark.asyncio
async def test_gateway_refuses_to_start_without_a_token() -> None:
    gateway = OneBot11Gateway(_FakeAdapter(), access_token="")

    with pytest.raises(GatewayError) as raised:
        await gateway.start()
    assert "SOAPBOT_ONEBOT_GATEWAY_TOKEN" in str(raised.value)


@pytest.mark.asyncio
async def test_gateway_refuses_to_bridge_an_onebot_adapter() -> None:
    gateway = OneBot11Gateway(_FakeAdapter("onebot11"), access_token="t")

    with pytest.raises(GatewayError) as raised:
        await gateway.start()
    assert "onebot11" in str(raised.value)


def test_authorization_accepts_bearer_and_query_but_not_a_wrong_token() -> None:
    gateway = OneBot11Gateway(_FakeAdapter(), access_token="secret")

    assert gateway._authorized(_FakeWs(headers={"Authorization": "Bearer secret"})) is True
    assert gateway._authorized(_FakeWs(path="/onebot/v11/ws?access_token=secret")) is True
    assert gateway._authorized(_FakeWs(headers={"Authorization": "Bearer nope"})) is False
    assert gateway._authorized(_FakeWs()) is False


@pytest.mark.asyncio
async def test_broadcast_fans_out_and_drops_a_broken_client() -> None:
    gateway = OneBot11Gateway(_FakeAdapter(), access_token="secret")
    good = _FakeWs()
    also_good = _FakeWs()
    broken = _FakeWs(fail_send=True)
    gateway._clients = {good, also_good, broken}

    await gateway._on_event(_incoming())

    assert len(good.sent) == 1 and len(also_good.sent) == 1
    payload = json.loads(good.sent[0])
    assert payload["group_id"] == "GROUP-1"
    assert broken not in gateway._clients


@pytest.mark.asyncio
async def test_action_rate_limit_returns_1200() -> None:
    gateway = OneBot11Gateway(_FakeAdapter(), access_token="secret")
    ws = _FakeWs()
    limiter = SlidingWindowLimiter(limit=2, window_seconds=60.0)
    frame = json.dumps({"action": "get_status", "echo": "e"})

    for _ in range(2):
        await gateway._handle_frame(ws, frame, limiter)
    await gateway._handle_frame(ws, frame, limiter)

    assert json.loads(ws.sent[-1])["retcode"] == 1200
    assert json.loads(ws.sent[0])["retcode"] == 0
    assert json.loads(ws.sent[0])["echo"] == "e"
