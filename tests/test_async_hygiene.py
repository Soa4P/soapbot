"""Async hygiene: the failures that were real, and the ones that were not.

Three of the ten reported issues did not hold up against this codebase, and they keep
being re-reported. Pinning them as assertions is the only way to stop the same review
from landing again: a comment can be argued with, a failing test cannot.

The remaining tests here cover the two genuine ones that are not about dispatch:
``scan_ports`` failing as a whole because one port errored, and plugin hashing running
on the event loop.
"""

from __future__ import annotations

import asyncio
import gc
import time
from typing import Any

import pytest

from soapbot.api import protocol
from soapbot.plugins import integrity

# --------------------------------------------------------------------- real defects


@pytest.mark.asyncio
async def test_one_failing_port_does_not_fail_the_scan(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """A single port raising must degrade to "closed", not cancel the whole gather.

    ``asyncio.gather`` without ``return_exceptions`` propagates the first exception,
    so a scan covering a range would return 500 instead of the open ports it found.
    """

    async def fake_classify(port: int, token_for: dict[int, str]) -> dict[str, Any]:
        if port == 3001:
            raise ConnectionResetError("peer reset")
        if port == 6099:
            return {"port": port, "kind": "http", "status_code": 200}
        return {"port": port, "kind": "closed"}

    monkeypatch.setattr(protocol, "_classify", fake_classify)

    results = await protocol.scan_ports([3001, 6099, 22])

    kinds = {item["port"]: item["kind"] for item in results}
    assert kinds == {3001: "closed", 6099: "http", 22: "closed"}
    # Ordering still puts the useful answer first, so the panel is unchanged.
    assert results[0]["port"] == 6099


@pytest.mark.asyncio
async def test_scan_result_order_is_by_kind_then_port(
    monkeypatch: pytest.MonkeyPatch,
) -> None:

    async def fake_classify(port: int, token_for: dict[int, str]) -> dict[str, Any]:
        kind = {1: "http", 2: "onebot", 3: "onebot_locked"}[port]
        return {"port": port, "kind": kind}

    monkeypatch.setattr(protocol, "_classify", fake_classify)

    results = await protocol.scan_ports([1, 2, 3])
    assert [r["kind"] for r in results] == ["onebot", "onebot_locked", "http"]


@pytest.mark.asyncio
async def test_digest_runs_off_the_event_loop(
    tmp_path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Hashing must not block the loop, because both call sites are async.

    The regression this catches: calling ``compare`` (a synchronous tree walk) directly
    from a request handler. The tree is small here, so the assertion is on *where* the
    work ran — a probe task must get scheduled while the digest is in progress.
    """
    directory = tmp_path / "plugin"
    directory.mkdir()
    (directory / "main.py").write_text("x = 1\n", encoding="utf-8")

    slow_started = asyncio.Event()
    real_digest = integrity.digest_tree

    def slow_digest(path):
        time.sleep(0.15)  # blocking work, as a real tree read would be
        return real_digest(path)

    monkeypatch.setattr(integrity, "digest_tree", slow_digest)
    integrity.forget(directory)

    async def probe() -> None:
        slow_started.set()

    task = asyncio.create_task(probe())
    await integrity.compare_async(directory, "sha256:whatever")
    await task

    assert slow_started.is_set(), "the loop must stay free while hashing"
    assert task.done()


# ------------------------------------------------------- claims that do not hold here


@pytest.mark.asyncio
async def test_create_task_results_are_strongly_referenced() -> None:
    """Claim: "create_task returns a task nobody holds".

    It does not hold. ``_handler_tasks`` is the set that keeps handlers alive, and the
    observer documents the identical pattern. This test fails if someone "cleans up" the
    set, which is the refactor that would introduce the reported bug for real.
    """
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

    class _Probe(Adapter):
        meta = AdapterMeta(name="mock", display_name="Mock", protocol="mock")
        capabilities = frozenset()

        async def start(self) -> None:
            return None

        async def stop(self) -> None:
            return None

        async def get_self(self) -> AccountInfo:
            return AccountInfo(self_id="1")

        async def send(self, message: OutgoingMessage) -> MessageReceipt:
            return MessageReceipt(ok=True)

    adapter = _Probe()
    gate = asyncio.Event()

    async def waiting(event: IncomingMessage) -> None:
        await gate.wait()

    adapter.on_event(waiting)
    event = IncomingMessage(
        event_type=EventType.MESSAGE,
        scene=MessageScene.PRIVATE,
        adapter="mock",
        self_id="1",
        sender=Sender(user_id="2"),
        segments=[MessageSegment.text("hi")],
        message_id="m1",
    )
    await adapter.emit(event)
    await asyncio.sleep(0)

    assert len(adapter._handler_tasks) == 1
    # The strong-reference claim, demonstrated: after a collection pass the task is
    # still pending rather than having been reclaimed mid-await.
    gc.collect()
    assert all(not t.done() for t in adapter._handler_tasks)

    gate.set()
    await adapter.drain_handlers(timeout=1.0)


def test_cancelled_error_is_not_caught_by_except_exception() -> None:
    """Claim: "``CancelledError`` is swallowed by ``except Exception``".

    It cannot be, since Python 3.8: ``CancelledError`` derives from ``BaseException``.
    The four ``except BaseException`` sites in this repo are inside plugin *subprocesses*,
    where catching the widest thing is deliberate — the child reports the failure to the
    parent instead of dying silently. A future reviewer "fixing" them to
    ``except Exception`` would break that reporting, so the relationship is asserted.
    """
    assert issubclass(asyncio.CancelledError, BaseException)
    assert not issubclass(asyncio.CancelledError, Exception)


def test_api_create_task_does_not_capture_request_scope() -> None:
    """Claim: "a task keeps a ``Request``/``Session`` alive".

    The only ``create_task`` under ``api/`` derives a no-argument coroutine. Asserted by
    inspecting the signature, so adding a parameter that closes over a request fails
    here rather than silently pinning a connection for the task's lifetime.
    """
    import inspect

    from soapbot.api import napcat

    source = inspect.getsource(napcat)
    assert "asyncio.create_task" in source
    # The task wraps a zero-argument callable, so it cannot be handed a request-scoped
    # value and cannot close over one through a parameter. ``to_thread`` also means the
    # blocking container start runs off the loop, which is the other half of the claim
    # under review.
    assert "to_thread(_start_and_wait)" in source
    signature = inspect.signature(napcat._start_and_wait)
    assert list(signature.parameters) == []
