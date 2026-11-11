"""Contract tests for the QQ official adapter.

The adapter had zero coverage while advertising IMAGE/RECORD/FILE and replacing
every image with ``[图片已省略]``. These cases exist so the two claims that matter
are measured, not asserted in prose:

* rich media really is two platform calls (upload, then ``msg_type=7``);
* a reply really carries the inbound ``msg_id`` and an increasing ``msg_seq``,
  because otherwise it is a proactive message and burns the relationship quota.

No network and no real ``botpy``: a stand-in module is installed in
``sys.modules`` for the duration of each test, so CI does not need the optional
extra and cannot start passing because a live API happened to answer.
"""

from __future__ import annotations

import sys
from types import ModuleType, SimpleNamespace

import pytest

from soapbot.adapters.qq_official import (
    PASSIVE_REPLIES_PER_MESSAGE,
    STATE_CAPACITY,
    QQOfficialAdapter,
    split_leading_at,
)
from soapbot.core.message import MessageScene, MessageSegment, OutgoingMessage


class _FakeApi:
    def __init__(self) -> None:
        self.calls: list[tuple[str, dict]] = []
        self.uploaded = SimpleNamespace(file_info="FILE-INFO")
        self.fail_upload = False
        self.fail_send = False

    async def post_group_file(self, **kwargs):
        self.calls.append(("post_group_file", kwargs))
        if self.fail_upload:
            raise RuntimeError("upload refused")
        return self.uploaded

    async def post_c2c_file(self, **kwargs):
        self.calls.append(("post_c2c_file", kwargs))
        if self.fail_upload:
            raise RuntimeError("upload refused")
        return self.uploaded

    async def post_group_message(self, **kwargs):
        self.calls.append(("post_group_message", kwargs))
        if self.fail_send:
            raise RuntimeError("send refused")

    async def post_c2c_message(self, **kwargs):
        self.calls.append(("post_c2c_message", kwargs))
        if self.fail_send:
            raise RuntimeError("send refused")


class _FakeClient:
    def __init__(self, intents=None) -> None:
        self.intents = intents
        self.api = _FakeApi()
        self.closed = False
        self.started_with: dict = {}

    async def start(self, **kwargs) -> None:
        self.started_with = kwargs

    async def close(self) -> None:
        self.closed = True


def _install_fake_botpy(monkeypatch: pytest.MonkeyPatch) -> ModuleType:
    module = ModuleType("botpy")
    module.Client = _FakeClient  # type: ignore[attr-defined]
    module.Intents = lambda **kwargs: SimpleNamespace(**kwargs)  # type: ignore[attr-defined]
    monkeypatch.setitem(sys.modules, "botpy", module)
    return module


def _adapter(monkeypatch: pytest.MonkeyPatch) -> QQOfficialAdapter:
    _install_fake_botpy(monkeypatch)
    adapter = QQOfficialAdapter(account_id="BOT", app_id="app", app_secret="secret")
    adapter._client = _FakeClient()
    return adapter


def _group_message(**kwargs) -> SimpleNamespace:
    values = {
        "content": "<@!BOT> 你好",
        "group_openid": "GROUP-1",
        "id": "MSG-1",
        "author": SimpleNamespace(member_openid="USER-1"),
        "attachments": [],
    }
    values.update(kwargs)
    return SimpleNamespace(**values)


async def _capture(adapter: QQOfficialAdapter):
    events = []

    async def handler(event) -> None:
        events.append(event)

    adapter.on_event(handler)
    return events


@pytest.mark.asyncio
async def test_missing_botpy_error_names_the_pip_package(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delitem(sys.modules, "botpy", raising=False)
    adapter = QQOfficialAdapter(account_id="BOT", app_id="app", app_secret="secret")

    with pytest.raises(RuntimeError) as raised:
        await adapter.start()
    assert "qq-botpy" in str(raised.value), "the install hint must name the real package"


@pytest.mark.asyncio
async def test_start_requests_group_and_c2c_intents_only(monkeypatch: pytest.MonkeyPatch) -> None:
    _install_fake_botpy(monkeypatch)
    adapter = QQOfficialAdapter(account_id="BOT", app_id="app", app_secret="secret")

    await adapter.start()
    assert adapter.health.online is True
    assert vars(adapter._client.intents) == {"public_messages": True, "direct_message": True}
    await adapter.stop()


@pytest.mark.asyncio
async def test_group_message_becomes_an_at_plus_text_event(monkeypatch: pytest.MonkeyPatch) -> None:
    adapter = _adapter(monkeypatch)
    events = await _capture(adapter)

    await adapter._on_group_message(_group_message())
    await adapter.drain_handlers(timeout=1.0)

    assert len(events) == 1
    event = events[0]
    assert event.scene is MessageScene.GROUP
    assert event.group_id == "GROUP-1"
    assert event.message_id == "MSG-1"
    assert [seg.type for seg in event.segments] == ["at", "text"]
    assert event.segments[0].data["qq"] == "BOT"


@pytest.mark.asyncio
async def test_c2c_message_maps_to_private_scene(monkeypatch: pytest.MonkeyPatch) -> None:
    adapter = _adapter(monkeypatch)
    events = await _capture(adapter)
    message = SimpleNamespace(
        content="hi",
        id="MSG-2",
        author=SimpleNamespace(user_openid="USER-9"),
        attachments=[],
    )

    await adapter._on_c2c_message(message)
    await adapter.drain_handlers(timeout=1.0)

    assert events[0].scene is MessageScene.PRIVATE
    assert events[0].sender.user_id == "USER-9"


@pytest.mark.asyncio
async def test_image_attachment_becomes_an_image_segment(monkeypatch: pytest.MonkeyPatch) -> None:
    adapter = _adapter(monkeypatch)
    events = await _capture(adapter)
    message = _group_message(
        attachments=[SimpleNamespace(url="https://cdn.example/a.png", content_type="image/png")]
    )

    await adapter._on_group_message(message)
    await adapter.drain_handlers(timeout=1.0)

    image = [seg for seg in events[0].segments if seg.type == "image"]
    assert image and image[0].data["url"] == "https://cdn.example/a.png"


@pytest.mark.asyncio
async def test_text_send_uses_msg_type_zero(monkeypatch: pytest.MonkeyPatch) -> None:
    adapter = _adapter(monkeypatch)
    receipt = await adapter.send(
        OutgoingMessage(scene=MessageScene.GROUP, segments=[MessageSegment.text("hi")], group_id="G")
    )

    assert receipt.ok is True
    name, kwargs = adapter._client.api.calls[-1]
    assert name == "post_group_message"
    assert kwargs["msg_type"] == 0
    assert kwargs["content"] == "hi"
    assert "msg_id" not in kwargs, "no inbound message means this is a proactive send"


@pytest.mark.asyncio
async def test_media_send_uploads_then_sends_msg_type_seven(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    adapter = _adapter(monkeypatch)
    receipt = await adapter.send(
        OutgoingMessage(
            scene=MessageScene.GROUP,
            segments=[MessageSegment.image(url="https://cdn.example/a.png")],
            group_id="G",
        )
    )

    assert receipt.ok is True
    names = [name for name, _ in adapter._client.api.calls]
    assert names == ["post_group_file", "post_group_message"]
    upload = adapter._client.api.calls[0][1]
    assert upload == {"group_openid": "G", "file_type": 1, "url": "https://cdn.example/a.png"}
    sent = adapter._client.api.calls[1][1]
    assert sent["msg_type"] == 7
    assert sent["media"] is adapter._client.api.uploaded, "the upload result is what gets sent"


@pytest.mark.asyncio
async def test_media_upload_failure_falls_back_to_text(monkeypatch: pytest.MonkeyPatch) -> None:
    adapter = _adapter(monkeypatch)
    adapter._client.api.fail_upload = True

    receipt = await adapter.send(
        OutgoingMessage(
            scene=MessageScene.GROUP,
            segments=[MessageSegment.image(url="https://cdn.example/a.png")],
            group_id="G",
        )
    )

    assert receipt.ok is True, "a failed image must not fail the whole reply"
    name, kwargs = adapter._client.api.calls[-1]
    assert name == "post_group_message"
    assert kwargs["msg_type"] == 0
    assert "图片发送失败" in kwargs["content"]


@pytest.mark.asyncio
async def test_passive_reply_carries_msg_id_and_increments_seq(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    adapter = _adapter(monkeypatch)
    await adapter._on_group_message(_group_message())
    await adapter.drain_handlers(timeout=1.0)

    for _ in range(2):
        await adapter.send(
            OutgoingMessage(
                scene=MessageScene.GROUP,
                segments=[MessageSegment.text("ok")],
                group_id="GROUP-1",
            )
        )

    first = adapter._client.api.calls[-2][1]
    second = adapter._client.api.calls[-1][1]
    assert first["msg_id"] == "MSG-1"
    assert first["msg_seq"] == 1
    assert second["msg_seq"] == 2


@pytest.mark.asyncio
async def test_passive_reply_stops_after_five(monkeypatch: pytest.MonkeyPatch) -> None:
    adapter = _adapter(monkeypatch)
    await adapter._on_group_message(_group_message())
    await adapter.drain_handlers(timeout=1.0)

    for _ in range(PASSIVE_REPLIES_PER_MESSAGE + 1):
        await adapter.send(
            OutgoingMessage(
                scene=MessageScene.GROUP,
                segments=[MessageSegment.text("ok")],
                group_id="GROUP-1",
            )
        )

    last = adapter._client.api.calls[-1][1]
    assert "msg_id" not in last, "the sixth reply must not claim a passive slot"
    hint = adapter.quota_hint(MessageScene.GROUP, "GROUP-1")
    assert hint["passive_replies_left"] == 0
    assert hint["per_relation_qpm"] == 20
    assert hint["per_group_daily_receive"] == 1000


@pytest.mark.asyncio
async def test_state_maps_are_bounded(monkeypatch: pytest.MonkeyPatch) -> None:
    adapter = _adapter(monkeypatch)
    for index in range(STATE_CAPACITY + 100):
        adapter._remember(f"group:{index}", f"MSG-{index}")

    assert len(adapter._last_user_msg) == STATE_CAPACITY
    assert len(adapter._last_message) == STATE_CAPACITY
    assert "group:0" not in adapter._last_message, "the oldest key is evicted"


@pytest.mark.asyncio
async def test_stop_drains_handlers_before_closing(monkeypatch: pytest.MonkeyPatch) -> None:
    adapter = _adapter(monkeypatch)
    order: list[str] = []

    async def _drain(timeout: float = 5.0) -> None:
        order.append("drain")

    async def _close() -> None:
        order.append("close")

    monkeypatch.setattr(adapter, "drain_handlers", _drain)
    adapter._client.close = _close  # type: ignore[method-assign]
    adapter._task = None

    await adapter.stop()

    assert order == ["drain", "close"]
    assert adapter.health.online is False


def test_split_leading_at_reports_the_mention() -> None:
    assert split_leading_at("<@!BOT> 你好") == (True, "你好")
    assert split_leading_at("  你好") == (False, "你好")
    assert split_leading_at("") == (False, "")
