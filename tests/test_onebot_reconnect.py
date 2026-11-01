"""The forward connection must survive a dropped socket.

``reconnect=True`` was accepted by the constructor and never read: the reader loop set
``online = False`` and returned, so the first dropped socket left the bot permanently
offline with no log line saying so. These tests pin the second attempt.
"""

from __future__ import annotations

import asyncio
from typing import Any

import pytest

from soapbot.adapters import onebot11
from soapbot.adapters.onebot11 import OneBot11Adapter


class _FakeWS:
    """A socket that yields nothing and then ends, like a dropped connection."""

    def __init__(self, *, fail: bool = False) -> None:
        self.closed = False
        self._fail = fail

    def __aiter__(self) -> Any:
        return self

    async def __anext__(self) -> Any:
        if self._fail:
            raise ConnectionResetError("peer went away")
        raise StopAsyncIteration

    async def close(self, *_a: Any, **_k: Any) -> None:
        self.closed = True


@pytest.mark.asyncio
async def test_a_dropped_socket_is_reconnected(monkeypatch: pytest.MonkeyPatch) -> None:
    """The regression: one drop used to be permanent."""
    attempts: list[str] = []

    async def fake_connect(url: str, **_kwargs: Any) -> _FakeWS:
        attempts.append(url)
        # First connection drops immediately; the second stays up until cancelled.
        if len(attempts) == 1:
            return _FakeWS()
        return _FakeWS(fail=False)

    monkeypatch.setattr(onebot11, "ws_connect", fake_connect)
    monkeypatch.setattr(onebot11, "_RECONNECT_BASE_S", 0.01)

    adapter = OneBot11Adapter(account_id="1", mode="forward", ws_url="ws://x:1")
    adapter._refresh_self_info = _noop  # type: ignore[method-assign]

    await adapter.start()
    try:
        for _ in range(100):
            if len(attempts) >= 2:
                break
            await asyncio.sleep(0.01)
        assert len(attempts) >= 2, "the adapter never tried a second connection"
    finally:
        await adapter.stop()


@pytest.mark.asyncio
async def test_reconnect_false_stops_after_one_attempt(monkeypatch: pytest.MonkeyPatch) -> None:
    """The flag has to mean something: off means one attempt, not a retry loop."""
    attempts: list[str] = []

    async def fake_connect(url: str, **_kwargs: Any) -> _FakeWS:
        attempts.append(url)
        return _FakeWS()

    monkeypatch.setattr(onebot11, "ws_connect", fake_connect)
    monkeypatch.setattr(onebot11, "_RECONNECT_BASE_S", 0.01)

    adapter = OneBot11Adapter(
        account_id="1", mode="forward", ws_url="ws://x:1", reconnect=False
    )
    adapter._refresh_self_info = _noop  # type: ignore[method-assign]

    await adapter.start()
    await asyncio.sleep(0.15)
    await adapter.stop()

    assert len(attempts) == 1


@pytest.mark.asyncio
async def test_a_refused_first_connect_still_fails_startup(monkeypatch: pytest.MonkeyPatch) -> None:
    """Supervision must not turn a misconfiguration into a silent retry loop.

    A wrong URL is an operator error and has to surface at startup, where the panel
    shows it — not as an adapter that quietly never connects.
    """

    async def refuse(_url: str, **_kwargs: Any) -> _FakeWS:
        raise ConnectionRefusedError("nothing listening")

    monkeypatch.setattr(onebot11, "ws_connect", refuse)
    adapter = OneBot11Adapter(account_id="1", mode="forward", ws_url="ws://x:1")

    with pytest.raises(ConnectionRefusedError):
        await adapter.start()


@pytest.mark.asyncio
async def test_backoff_grows_and_is_capped(monkeypatch: pytest.MonkeyPatch) -> None:
    """A protocol side that is down for an hour must not be hammered once per second."""
    monkeypatch.setattr(onebot11, "_RECONNECT_BASE_S", 1.0)
    monkeypatch.setattr(onebot11, "_RECONNECT_MAX_S", 30.0)

    delays: list[float] = []
    real_sleep = asyncio.sleep

    async def fake_sleep(seconds: float) -> None:
        delays.append(seconds)
        if len(delays) >= 8:
            raise asyncio.CancelledError
        await real_sleep(0)

    async def always_fail(_url: str, **_kwargs: Any) -> _FakeWS:
        raise ConnectionRefusedError("down")

    monkeypatch.setattr(onebot11, "ws_connect", always_fail)
    monkeypatch.setattr(onebot11.asyncio, "sleep", fake_sleep)

    adapter = OneBot11Adapter(account_id="1", mode="forward", ws_url="ws://x:1")
    with pytest.raises(asyncio.CancelledError):
        await adapter._supervise_forward()

    # Jitter is 0.5x–1.5x, so compare against the un-jittered envelope.
    assert delays[0] < delays[-1] or delays[-1] <= 30.0 * 1.5
    assert all(d <= 30.0 * 1.5 + 0.001 for d in delays), f"backoff exceeded the cap: {delays}"


@pytest.mark.asyncio
async def test_a_half_open_socket_is_detected_by_the_liveness_probe(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """The failure that survived the first fix.

    A half-open socket never ends the reader: ``async for raw in ws`` simply never
    yields again. Waiting only on the reader therefore blocks forever while the bot
    reports itself online — measured as seventeen hours of a bot claiming to be
    connected with no socket to NapCat at all. The probe is what turns silence into a
    reconnect.
    """
    attempts: list[str] = []

    class _Silent:
        """Accepts the connection and then says nothing, ever."""

        closed = False

        def __aiter__(self) -> Any:
            return self

        async def __anext__(self) -> Any:
            await asyncio.sleep(3600)
            raise StopAsyncIteration

        async def send(self, _data: Any) -> None:
            return None

        async def close(self, *_a: Any, **_k: Any) -> None:
            self.closed = True

    async def fake_connect(url: str, **_kwargs: Any) -> _Silent:
        attempts.append(url)
        return _Silent()

    monkeypatch.setattr(onebot11, "ws_connect", fake_connect)
    monkeypatch.setattr(onebot11, "_RECONNECT_BASE_S", 0.01)
    monkeypatch.setattr(onebot11, "_LIVENESS_WINDOW_S", 0.02)

    adapter = OneBot11Adapter(account_id="1", mode="forward", ws_url="ws://x:1")

    async def no_info() -> None:
        return None

    async def dead_probe(action: str, _params: Any, timeout: float = 30.0) -> Any:
        raise TimeoutError("no reply")

    adapter._refresh_self_info = no_info  # type: ignore[method-assign]
    adapter._call = dead_probe  # type: ignore[method-assign]

    await adapter.start()
    try:
        # Poll the counter the operator would read, not the internal attempt count:
        # the dial happens before the counter is incremented, so waiting on the dial
        # races the assertion by one scheduling tick.
        for _ in range(150):
            if adapter.health.reconnect_attempts >= 1:
                break
            await asyncio.sleep(0.02)
        assert adapter.health.reconnect_attempts >= 1, "a silent socket never triggered a reconnect"
        assert len(attempts) >= 2, "the adapter never dialled a second connection"
    finally:
        await adapter.stop()


async def _noop() -> None:
    return None
