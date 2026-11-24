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
async def test_boot_while_protocol_end_is_down_recovers_when_it_returns(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """The production outage that made a NapCat restart look like a dead bot.

    ``start()`` used to create the supervisor only *after* a successful first dial.
    When NapCat was down at boot, the exception escaped before any supervisor existed;
    ``runtime.start`` logged "adapter start failed" and the adapter then never tried
    again. Bringing NapCat back did nothing — the bot needed a human restart.

    This is a distinct failure from a socket that drops *after* connecting (covered
    above): here the connection has never succeeded at all.
    """
    available = False
    attempts: list[str] = []

    async def fake_connect(url: str, **_kwargs: Any) -> _FakeWS:
        attempts.append(url)
        if not available:
            raise ConnectionRefusedError("nothing listening")
        return _FakeWS(fail=False)

    monkeypatch.setattr(onebot11, "ws_connect", fake_connect)
    monkeypatch.setattr(onebot11, "_RECONNECT_BASE_S", 0.01)

    adapter = OneBot11Adapter(account_id="1", mode="forward", ws_url="ws://x:1")
    adapter._refresh_self_info = _noop  # type: ignore[method-assign]

    with pytest.raises(ConnectionRefusedError):
        await adapter.start()

    # Startup must stay loud, but a supervisor has to exist despite it.
    assert adapter._tasks, "no reconnect supervisor was created"
    assert not adapter.health.online

    available = True
    try:
        for _ in range(300):
            if adapter.health.online:
                break
            await asyncio.sleep(0.01)
        assert adapter.health.online, "bot never came back after NapCat returned"
        assert len(attempts) >= 2
    finally:
        await adapter.stop()


@pytest.mark.asyncio
async def test_a_long_outage_escalates_to_an_actionable_error(
    monkeypatch: pytest.MonkeyPatch, caplog: pytest.LogCaptureFixture
) -> None:
    """A 1000-line wall of identical WARNINGs is why the outage felt "inexplicable".

    The real incident produced 1025 `WinError 1225` warnings and not one line saying
    what to check. Escalation must name the protocol end and QQ login, and must not
    repeat on every attempt.
    """
    import logging

    real_sleep = asyncio.sleep

    async def fake_sleep(seconds: float) -> None:
        if adapter.health.reconnect_attempts >= 6:
            raise asyncio.CancelledError
        await real_sleep(0)

    async def always_fail(_url: str, **_kwargs: Any) -> _FakeWS:
        raise ConnectionRefusedError("down")

    monkeypatch.setattr(onebot11, "_RECONNECT_BASE_S", 0.01)
    monkeypatch.setattr(onebot11.asyncio, "sleep", fake_sleep)
    monkeypatch.setattr(onebot11, "ws_connect", always_fail)

    adapter = OneBot11Adapter(account_id="1", mode="forward", ws_url="ws://x:1")
    adapter._refresh_self_info = _noop  # type: ignore[method-assign]

    with (
        caplog.at_level(logging.ERROR, logger="soapbot.adapters.onebot11"),
        pytest.raises(asyncio.CancelledError),
    ):
        await adapter._supervise_forward()

    escalations = [r for r in caplog.records if "protocol end still unreachable" in r.message]
    assert len(escalations) == 1, "escalate once at the threshold, not on every retry"
    text = escalations[0].getMessage()
    assert "6099" in text and "ExecutionTimeLimit" in text


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
    redialled = asyncio.Event()

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
        if len(attempts) >= 2:
            redialled.set()
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
        # An event, not a polling loop.  fake_connect sets it synchronously on the
        # second dial, so there is no scheduling gap between "the dial happened" and
        # "the test can see it" — the race that made this flaky under full-suite load.
        await asyncio.wait_for(redialled.wait(), timeout=5.0)
        assert adapter.health.reconnect_attempts >= 1, (
            "a silent socket never triggered a reconnect"
        )
        assert len(attempts) >= 2, "the adapter never dialled a second connection"
    finally:
        await adapter.stop()


async def _noop() -> None:
    return None


# --------------------------------------------------------------- reverse transport


class _FakeRequest:
    """Just the two attributes ``_client_authorized`` reads."""

    def __init__(self, token: str) -> None:
        self.headers = {"Authorization": f"Bearer {token}"}
        self.path = "/onebot/v11/ws"


class _AuthorisedWS(_FakeWS):
    """A reverse-WS client that has already passed the token check."""

    def __init__(self, *, fail: bool = False, token: str = "t0ken") -> None:
        super().__init__(fail=fail)
        self.request = _FakeRequest(token)
        self.remote_address = ("127.0.0.1", 12345)


class _HeldWS(_AuthorisedWS):
    """Stays connected: the read loop blocks until the test cancels it."""

    async def __anext__(self) -> Any:
        await asyncio.Event().wait()  # never set
        raise StopAsyncIteration  # pragma: no cover - unreachable


class _HandoverWS(_AuthorisedWS):
    """A socket that hands its slot to a replacement mid-read.

    The takeover has to happen inside the read loop: the handler's own guard refuses
    a second live client, so nothing can legitimately evict the slot from outside.
    """

    def __init__(self, adapter: Any, replacement: Any) -> None:
        super().__init__()
        self._adapter = adapter
        self._replacement = replacement

    async def __anext__(self) -> Any:
        self._adapter._ws = self._replacement
        raise StopAsyncIteration


async def _reverse_handler(monkeypatch: pytest.MonkeyPatch):
    """Start a reverse adapter and hand back the connection handler it registered."""
    captured: dict[str, Any] = {}

    async def fake_serve(handler: Any, *_args: Any, **_kwargs: Any) -> Any:
        captured["handler"] = handler

        class _Server:
            def close(self) -> None:
                return None

            async def wait_closed(self) -> None:
                return None

        return _Server()

    monkeypatch.setattr(onebot11, "ws_serve", fake_serve)
    adapter = OneBot11Adapter(
        account_id="1", mode="reverse", access_token="t0ken", port=6700
    )
    adapter._refresh_self_info = _noop  # type: ignore[method-assign]
    await adapter.start()
    return adapter, captured["handler"]


@pytest.mark.asyncio
async def test_reverse_slot_is_released_when_the_client_disconnects(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """S-MSG-09: a normal disconnect used to leave the slot filled.

    The handler never cleared ``self._ws``, so the *next* reverse connection — a NapCat
    restart, a network blip, a protocol-side reconnect — was refused with 1013 "already
    connected" and the bot stayed offline until the process was restarted. The audit
    called this a reconnect bug; it was an ownership bug.
    """
    adapter, handler = await _reverse_handler(monkeypatch)
    try:
        await handler(_AuthorisedWS())  # connects, reads nothing, ends
        assert adapter._ws is None, "the closed socket stayed in the slot"
        assert adapter.health.online is False

        # The regression: this second client must be accepted, not 1013'd.
        second = _HeldWS()
        task = asyncio.create_task(handler(second))
        for _ in range(100):
            if adapter._ws is second:
                break
            await asyncio.sleep(0.01)
        assert adapter._ws is second, "a fresh client was refused after a clean disconnect"
        task.cancel()
        with pytest.raises(asyncio.CancelledError):
            await task
    finally:
        await adapter.stop()


@pytest.mark.asyncio
async def test_reverse_handler_does_not_clear_a_newer_clients_slot(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Only the socket that owns the slot may clear it.

    Cleared unconditionally in ``finally``, a handler that finishes late would evict
    the replacement client that took the slot while it was winding down — trading one
    stuck slot for one silently unplugged session. The guard normally prevents two
    live clients, so the takeover has to be simulated: the old socket hands the slot
    over mid-read.
    """
    adapter, handler = await _reverse_handler(monkeypatch)
    try:
        newer = _HeldWS()
        await handler(_HandoverWS(adapter, newer))
        assert adapter._ws is newer, "an obsolete handler evicted the live client"
    finally:
        await adapter.stop()
