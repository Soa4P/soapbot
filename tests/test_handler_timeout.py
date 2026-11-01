"""One stuck handler must not hold a slot forever.

Without a bound, a handler waiting on a model that never answers keeps its task alive
indefinitely; combined with the dispatch cap, a handful of such handlers stop the bot
from accepting anything at all while still looking "online".
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


class _Adapter(Adapter):
    meta = AdapterMeta(name="mock", display_name="Mock", protocol="mock")
    capabilities = frozenset()

    async def start(self) -> None:
        return None

    async def stop(self) -> None:
        return None

    async def get_self(self) -> AccountInfo:
        return AccountInfo(self_id="10000", adapter="mock")

    async def send(self, message: OutgoingMessage) -> MessageReceipt:
        return MessageReceipt(ok=True)


def _event(trace: str = "t1") -> IncomingMessage:
    return IncomingMessage(
        event_type=EventType.MESSAGE,
        scene=MessageScene.GROUP,
        adapter="mock",
        self_id="10000",
        sender=Sender(user_id="42", nickname="tester"),
        segments=[MessageSegment.text("hello")],
        message_id=trace,
        group_id="777",
        trace_id=trace,
    )


@pytest.mark.asyncio
async def test_a_stuck_handler_is_cancelled_and_counted(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """The timeout must cancel the work, not merely log that it is slow."""
    monkeypatch.setattr(settings, "handler_timeout_seconds", 0.05)
    monkeypatch.setattr(settings, "max_inflight_handlers", 0)

    adapter = _Adapter()
    cancelled = asyncio.Event()

    async def stuck(event: IncomingMessage) -> None:
        try:
            await asyncio.sleep(30)
        except asyncio.CancelledError:
            cancelled.set()
            raise

    adapter.on_event(stuck)
    await adapter.emit(_event())
    await adapter.drain_handlers(timeout=2.0)

    assert adapter.handler_timeouts == 1
    assert cancelled.is_set(), "the task must be cancelled, not abandoned"
    assert adapter._handler_tasks == set(), "a timed-out task must not linger"


@pytest.mark.asyncio
async def test_a_normal_handler_is_unaffected(monkeypatch: pytest.MonkeyPatch) -> None:
    """The bound must not turn ordinary work into a timeout."""
    monkeypatch.setattr(settings, "handler_timeout_seconds", 5.0)
    monkeypatch.setattr(settings, "max_inflight_handlers", 0)

    adapter = _Adapter()
    seen: list[str] = []

    async def quick(event: IncomingMessage) -> None:
        await asyncio.sleep(0)
        seen.append(event.trace_id)

    adapter.on_event(quick)
    await adapter.emit(_event("ok"))
    await adapter.drain_handlers(timeout=2.0)

    assert seen == ["ok"]
    assert adapter.handler_timeouts == 0


@pytest.mark.asyncio
async def test_a_timed_out_slot_is_released(monkeypatch: pytest.MonkeyPatch) -> None:
    """The point of cancelling: the cap must free up again.

    This is the interaction that made the two fixes one change. A timeout that left
    the task alive would keep the slot occupied, so the cap would fill with dead
    handlers and the bot would stop answering while reporting itself healthy.
    """
    monkeypatch.setattr(settings, "handler_timeout_seconds", 0.05)
    monkeypatch.setattr(settings, "max_inflight_handlers", 1)

    adapter = _Adapter()
    served: list[str] = []

    async def stuck(event: IncomingMessage) -> None:
        if event.trace_id == "first":
            await asyncio.sleep(30)
        served.append(event.trace_id)

    adapter.on_event(stuck)
    await adapter.emit(_event("first"))
    await asyncio.sleep(0.15)  # let the first one time out

    await adapter.emit(_event("second"))
    await adapter.drain_handlers(timeout=2.0)

    assert adapter.handler_timeouts == 1
    assert "second" in served, "the slot must be free again after a timeout"


@pytest.mark.asyncio
async def test_a_handler_timeout_error_is_not_counted_as_ours(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """The handler's own ``TimeoutError`` is a handler failure, not a dispatch timeout.

    ``wait_for`` raises the same ``TimeoutError`` for its own expiry as a provider or
    socket deadline inside the pipeline, so a plain ``except TimeoutError`` would report
    every slow provider as "handler stuck" and inflate the counter the panel uses to
    decide whether dispatch is healthy.
    """
    monkeypatch.setattr(settings, "handler_timeout_seconds", 5.0)
    monkeypatch.setattr(settings, "max_inflight_handlers", 0)

    adapter = _Adapter()

    async def provider_timed_out(event: IncomingMessage) -> None:
        raise TimeoutError("provider deadline exceeded")

    adapter.on_event(provider_timed_out)
    await adapter.emit(_event())
    await adapter.drain_handlers(timeout=2.0)

    assert adapter.handler_timeouts == 0, "a provider timeout is not a dispatch timeout"


@pytest.mark.asyncio
async def test_zero_disables_the_timeout(monkeypatch: pytest.MonkeyPatch) -> None:
    """``handler_timeout_seconds=0`` must mean unbounded, not immediate."""
    monkeypatch.setattr(settings, "handler_timeout_seconds", 0.0)
    monkeypatch.setattr(settings, "max_inflight_handlers", 0)

    adapter = _Adapter()
    seen: list[str] = []

    async def slowish(event: IncomingMessage) -> None:
        await asyncio.sleep(0.1)
        seen.append(event.trace_id)

    adapter.on_event(slowish)
    await adapter.emit(_event("slow"))
    await adapter.drain_handlers(timeout=2.0)

    assert seen == ["slow"]
    assert adapter.handler_timeouts == 0
