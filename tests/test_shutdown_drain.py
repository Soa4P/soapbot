"""Shutdown must let in-flight work finish before it closes the resources it uses.

The failure this pins: ``PassiveObserver.drain`` existed and had **no call site in src/**,
and ``qq_official.stop`` cancelled its reader without draining the handlers that reader
had dispatched. Both look like a clean shutdown and both silently lose the last replies
and the last archived messages.
"""

from __future__ import annotations

import pytest

from soapbot.core.adapter import AccountInfo, Adapter, AdapterMeta
from soapbot.core.message import MessageReceipt, OutgoingMessage
from soapbot.core.runtime import BotRuntime


class _DrainingAdapter(Adapter):
    """Records that it was drained, and in what order relative to ``stop``."""

    meta = AdapterMeta(name="mock", display_name="Mock", protocol="mock")
    capabilities = frozenset()

    def __init__(self, order: list[str]) -> None:
        super().__init__()
        self._order = order

    async def start(self) -> None:
        return None

    async def stop(self) -> None:
        self._order.append("stop")

    async def get_self(self) -> AccountInfo:
        return AccountInfo(self_id="10000", adapter="mock")

    async def send(self, message: OutgoingMessage) -> MessageReceipt:
        return MessageReceipt(ok=True)

    async def drain_handlers(self, timeout: float = 5.0) -> None:
        self._order.append("drain")


class _DrainingObserver:
    def __init__(self, order: list[str]) -> None:
        self._order = order

    async def drain(self, timeout: float = 5.0) -> None:
        self._order.append("observer-drain")


@pytest.mark.asyncio
async def test_runtime_drain_visits_adapters_then_observer() -> None:
    """Handlers produce the archive payloads, so they drain first."""
    order: list[str] = []
    runtime = BotRuntime(passive=_DrainingObserver(order))
    await runtime.add_adapter(_DrainingAdapter(order))

    await runtime.drain(timeout=1.0)

    assert order == ["drain", "observer-drain"]


@pytest.mark.asyncio
async def test_runtime_drain_survives_a_failing_adapter() -> None:
    """One adapter that refuses to drain must not skip the others."""

    class _Broken(_DrainingAdapter):
        async def drain_handlers(self, timeout: float = 5.0) -> None:
            raise RuntimeError("drain exploded")

    order: list[str] = []
    runtime = BotRuntime(passive=_DrainingObserver(order))
    adapter = _Broken(order)
    await runtime.add_adapter(adapter)

    await runtime.drain(timeout=1.0)

    assert "observer-drain" in order, "the observer must still be drained"


@pytest.mark.asyncio
async def test_runtime_drain_without_observer_is_safe() -> None:
    """A hand-built runtime has no passive observer; drain must not raise."""
    order: list[str] = []
    runtime = BotRuntime()
    await runtime.add_adapter(_DrainingAdapter(order))

    await runtime.drain(timeout=1.0)

    assert order == ["drain"]


@pytest.mark.asyncio
async def test_shutdown_drains_before_stop() -> None:
    """``_shutdown`` must drain the runtime before ``stop()`` closes adapters.

    Asserted on the calls rather than on internal state because the failure being
    prevented is an *ordering* one: draining after stop would flush work onto closed
    sockets, which raises inside cancelled tasks and looks like a clean exit.
    """
    from soapbot import app as app_module

    order: list[str] = []
    runtime = BotRuntime(passive=_DrainingObserver(order))

    class _StopRecording(_DrainingAdapter):
        async def stop(self) -> None:
            order.append("stop")

    await runtime.add_adapter(_StopRecording(order))

    original_stop = runtime.stop

    async def tracked_stop() -> None:
        order.append("runtime-stop")
        await original_stop()

    runtime.stop = tracked_stop  # type: ignore[method-assign]

    original_runtime = app_module._RUNTIME
    app_module._RUNTIME = runtime
    try:
        await app_module._shutdown()
    finally:
        app_module._RUNTIME = original_runtime

    assert order.index("drain") < order.index("runtime-stop")
    assert order.index("observer-drain") < order.index("runtime-stop")


@pytest.mark.asyncio
async def test_qq_official_stop_drains_dispatched_handlers() -> None:
    """Cancelling the reader is not enough: it leaves its handler tasks running."""
    from soapbot.adapters.qq_official import QQOfficialAdapter

    drained: list[float] = []

    class _Probe(QQOfficialAdapter):
        async def drain_handlers(self, timeout: float = 5.0) -> None:
            drained.append(timeout)

    adapter = _Probe(app_id="a", app_secret="s", account_id="1")
    adapter._task = None
    adapter._client = None

    await adapter.stop()

    assert drained, "stop() must drain handlers before releasing the client"
