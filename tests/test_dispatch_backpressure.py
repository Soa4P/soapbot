"""Dispatch must have a ceiling, and a dropped @mention must not be silent.

Two failures motivated this. First, ``emit`` derived one task per subscriber per event
with no cap: a burst produced unbounded tasks, each running a full pipeline and possibly
a paid model call. Second, the obvious fix — dropping over the cap — reintroduces the
exact symptom this project keeps being reported for: an @mention that gets no answer is
indistinguishable from a dead bot.
"""

from __future__ import annotations

import asyncio

import pytest

from soapbot.config import settings
from soapbot.core.adapter import AccountInfo, Adapter, AdapterMeta
from soapbot.core.message import (
    EventType,
    IncomingMessage,
    MessageReceipt,
    MessageScene,
    MessageSegment,
    OutgoingMessage,
    Sender,
)


class _RecordingAdapter(Adapter):
    """Minimal adapter that records what it was asked to send.

    Deliberately not the mock adapter: this test is about ``Adapter.emit`` itself, and
    borrowing a concrete implementation would make it pass or fail for reasons that
    have nothing to do with dispatch.
    """

    meta = AdapterMeta(name="mock", display_name="Mock", protocol="mock")
    capabilities = frozenset()

    def __init__(self) -> None:
        super().__init__()
        self.sent: list[OutgoingMessage] = []

    async def start(self) -> None:
        return None

    async def stop(self) -> None:
        return None

    async def get_self(self) -> AccountInfo:
        return AccountInfo(self_id="10000", adapter="mock")

    async def send(self, message: OutgoingMessage) -> MessageReceipt:
        self.sent.append(message)
        return MessageReceipt(ok=True, message_id=str(len(self.sent)))


def _event(
    trace: str = "t1",
    *,
    scene: MessageScene = MessageScene.GROUP,
    at_me: bool = False,
    self_id: str = "10000",
) -> IncomingMessage:
    segments = [MessageSegment.text("hello")]
    if at_me:
        segments.insert(0, MessageSegment.at(self_id))
    return IncomingMessage(
        event_type=EventType.MESSAGE,
        scene=scene,
        adapter="mock",
        self_id=self_id,
        sender=Sender(user_id="42", nickname="tester"),
        segments=segments,
        message_id=trace,
        group_id="777" if scene is MessageScene.GROUP else "",
        trace_id=trace,
    )


@pytest.fixture(autouse=True)
def _restore_settings(monkeypatch: pytest.MonkeyPatch) -> None:
    """Every test sets the cap explicitly; restore afterwards so nothing leaks."""
    yield


@pytest.mark.asyncio
async def test_over_the_cap_ordinary_messages_are_dropped(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """The cap must actually stop work, not merely log about it."""
    monkeypatch.setattr(settings, "max_inflight_handlers", 1)
    monkeypatch.setattr(settings, "handler_timeout_seconds", 0.0)

    adapter = _RecordingAdapter()
    started: list[str] = []
    release = asyncio.Event()

    async def slow(event: IncomingMessage) -> None:
        started.append(event.trace_id)
        await release.wait()

    adapter.on_event(slow)

    await adapter.emit(_event("first"))
    await asyncio.sleep(0)  # let the handler start and occupy the slot
    await adapter.emit(_event("second"))
    await adapter.emit(_event("third"))

    # Only the first ran: the cap is checked before a task is derived, so the
    # dropped events never reached the pipeline at all.
    assert started == ["first"]
    assert adapter.dropped_events == 2
    assert adapter.busy_notices == 0, "ordinary chatter must be dropped quietly"

    release.set()
    await adapter.drain_handlers(timeout=1.0)


@pytest.mark.asyncio
async def test_dropped_mention_gets_one_busy_notice(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Silence is the one answer an @mention must never get."""
    monkeypatch.setattr(settings, "max_inflight_handlers", 1)
    monkeypatch.setattr(settings, "handler_timeout_seconds", 0.0)
    monkeypatch.setattr(settings, "busy_notice", "busy, try later")

    adapter = _RecordingAdapter()
    release = asyncio.Event()

    async def slow(event: IncomingMessage) -> None:
        await release.wait()

    adapter.on_event(slow)
    await adapter.emit(_event("first"))
    await asyncio.sleep(0)

    await adapter.emit(_event("mention", at_me=True))
    await adapter.drain_handlers(timeout=1.0)

    assert adapter.dropped_events == 1
    assert adapter.busy_notices == 1
    assert len(adapter.sent) == 1
    assert adapter.sent[0].text == "busy, try later"
    # Sent to the group that asked, not to the bot's own account.
    assert adapter.sent[0].group_id == "777"

    release.set()


@pytest.mark.asyncio
async def test_private_message_counts_as_addressed(monkeypatch: pytest.MonkeyPatch) -> None:
    """A private message is directed at the bot even without an AT segment."""
    monkeypatch.setattr(settings, "max_inflight_handlers", 1)
    monkeypatch.setattr(settings, "handler_timeout_seconds", 0.0)
    monkeypatch.setattr(settings, "busy_notice", "busy")

    adapter = _RecordingAdapter()
    release = asyncio.Event()

    async def slow(event: IncomingMessage) -> None:
        await release.wait()

    adapter.on_event(slow)
    await adapter.emit(_event("first"))
    await asyncio.sleep(0)
    await adapter.emit(_event("dm", scene=MessageScene.PRIVATE))
    await adapter.drain_handlers(timeout=1.0)

    assert adapter.busy_notices == 1
    release.set()


@pytest.mark.asyncio
async def test_mention_of_someone_else_is_not_addressed(monkeypatch: pytest.MonkeyPatch) -> None:
    """``@all`` and other people's mentions must not trigger a busy notice."""
    monkeypatch.setattr(settings, "max_inflight_handlers", 1)
    monkeypatch.setattr(settings, "handler_timeout_seconds", 0.0)
    monkeypatch.setattr(settings, "busy_notice", "busy")

    other = IncomingMessage(
        event_type=EventType.MESSAGE,
        scene=MessageScene.GROUP,
        adapter="mock",
        self_id="10000",
        sender=Sender(user_id="42", nickname="tester"),
        segments=[MessageSegment.at("all"), MessageSegment.text("hi")],
        message_id="other",
        group_id="777",
        trace_id="other",
    )

    adapter = _RecordingAdapter()
    release = asyncio.Event()

    async def slow(event: IncomingMessage) -> None:
        await release.wait()

    adapter.on_event(slow)
    await adapter.emit(_event("first"))
    await asyncio.sleep(0)
    await adapter.emit(other)
    await adapter.drain_handlers(timeout=1.0)

    assert adapter.busy_notices == 0, "@all is not a direct mention"
    release.set()


@pytest.mark.asyncio
async def test_zero_disables_the_cap(monkeypatch: pytest.MonkeyPatch) -> None:
    """``max_inflight_handlers=0`` must mean unlimited, not "drop everything".

    The distinction matters: a falsy config default silently becoming "cap of zero"
    would stop all message handling, and every test above would still pass because
    they all set a positive limit.
    """
    monkeypatch.setattr(settings, "max_inflight_handlers", 0)
    monkeypatch.setattr(settings, "handler_timeout_seconds", 0.0)

    adapter = _RecordingAdapter()
    started: list[str] = []
    release = asyncio.Event()

    async def slow(event: IncomingMessage) -> None:
        started.append(event.trace_id)
        await release.wait()

    adapter.on_event(slow)
    for i in range(5):
        await adapter.emit(_event(f"e{i}"))
    await asyncio.sleep(0.05)

    assert len(started) == 5
    assert adapter.dropped_events == 0

    release.set()
    await adapter.drain_handlers(timeout=1.0)


def test_backpressure_status_is_reported() -> None:
    """The counters exist for the panel; they must be readable without a message."""
    adapter = _RecordingAdapter()
    status = adapter.backpressure_status()
    assert set(status) == {"inflight", "dropped", "busy_notices", "handler_timeouts"}
    assert status["inflight"] == 0
