"""Plugin events: read-only by default, one writable event, and failures stay local."""

from __future__ import annotations

import asyncio
from typing import Any

import pytest

from soapbot.plugins.context import PluginContext
from soapbot.plugins.events import EVENTS, WRITABLE_EVENTS, dispatch_event
from soapbot.plugins.manifest import Capability


class _Guard:
    def __init__(self, allow: bool = True) -> None:
        self.allow = allow
        self.checked: list[Any] = []

    def check(self, capability: Any, detail: str = "") -> None:
        self.checked.append(capability)
        if not self.allow:
            raise PermissionError("capability not granted")


def _ctx(allow: bool = True) -> PluginContext:
    """A real context with only the attributes ``on`` touches.

    Building it through ``__init__`` would drag in storage, crypto and an audit log
    that have nothing to do with event registration.
    """
    ctx = PluginContext.__new__(PluginContext)
    ctx.plugin = "demo"
    ctx._guard = _Guard(allow)
    ctx._event_handlers = {}
    return ctx


class _Loaded:
    def __init__(self, name: str, handlers: dict[str, list[Any]]) -> None:
        self.name = name
        self.context = type("Ctx", (), {"_event_handlers": handlers})()


class _Loader:
    def __init__(self, *items: _Loaded) -> None:
        self.loaded = {item.name: item for item in items}


def test_every_event_declares_writability() -> None:
    assert set(EVENTS) == {
        "message_received",
        "reply_ready",
        "tool_before",
        "tool_after",
        "plugin_loaded",
        "plugin_unloaded",
        "schedule_tick",
    }
    assert {"reply_ready"} == WRITABLE_EVENTS


def test_unknown_event_is_refused() -> None:
    with pytest.raises(ValueError, match="unknown plugin event"):
        _ctx().on("message_rewritten")


def test_writable_event_needs_send_capability() -> None:
    ctx = _ctx()
    ctx.on("reply_ready")(lambda payload: payload)
    assert Capability.SEND in ctx._guard.checked

    with pytest.raises(PermissionError):
        _ctx(allow=False).on("reply_ready")(lambda payload: payload)


def test_read_only_event_needs_only_message_capability() -> None:
    ctx = _ctx()
    ctx.on("tool_after")(lambda payload: payload)
    assert ctx._guard.checked == [Capability.MESSAGE]


def test_observer_cannot_change_the_value() -> None:
    loader = _Loader(_Loaded("a", {"tool_after": [lambda payload: "mutated"]}))

    result = asyncio.run(dispatch_event(loader, "tool_after", {"tool": "x"}))

    assert result is None


def test_writable_event_applies_the_last_string() -> None:
    loader = _Loader(
        _Loaded("a", {"reply_ready": [lambda payload: "first"]}),
        _Loaded("b", {"reply_ready": [lambda payload: "second"]}),
    )

    result = asyncio.run(dispatch_event(loader, "reply_ready", {"text": "original"}))

    assert result == "second"


def test_a_failing_handler_does_not_block_the_others() -> None:
    def boom(payload: dict[str, Any]) -> str:
        raise RuntimeError("handler broke")

    loader = _Loader(
        _Loaded("bad", {"reply_ready": [boom]}),
        _Loaded("good", {"reply_ready": [lambda payload: "kept"]}),
    )

    result = asyncio.run(dispatch_event(loader, "reply_ready", {"text": "original"}))

    assert result == "kept"


def test_a_slow_handler_is_dropped_at_the_budget(monkeypatch) -> None:
    monkeypatch.setattr("soapbot.plugins.events.EVENT_TIMEOUT", 0.05)

    async def slow(payload: dict[str, Any]) -> str:
        await asyncio.sleep(30)
        return "late"

    loader = _Loader(_Loaded("slow", {"reply_ready": [slow]}))

    # The handler budget is 50ms here; waiting 30s would mean it was ignored.
    result = asyncio.run(dispatch_event(loader, "reply_ready", {"text": "original"}))

    assert result == {"text": "original"}
