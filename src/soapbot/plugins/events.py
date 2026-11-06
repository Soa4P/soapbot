"""Named plugin events beyond message observation.

The original message and notice hooks are read-only on purpose: a plugin that could
rewrite an inbound message would run *after* sanitisation and injection screening
and could undo both. This module keeps that distinction explicit rather than
relaxing it. Every event declares whether a handler may change the value; the one
writable event (``reply_ready``) requires the stronger ``SEND`` capability and its
output is re-scrubbed by the caller before delivery.

Handlers receive one read-only dict. They do not receive the pipeline context, the
message object, or the adapter, so a handler cannot reach past the event.
"""

from __future__ import annotations

import asyncio
import inspect
import logging
from dataclasses import dataclass
from typing import Any

from soapbot.plugins.context import bind_caller

logger = logging.getLogger(__name__)

#: Same budget as the message hooks. A slow observer must not become the latency of
#: every reply, and a hung one must not hold the pipeline open.
EVENT_TIMEOUT = 2.0


@dataclass(frozen=True, slots=True)
class EventSpec:
    name: str
    writable: bool
    capability: str
    """``message`` for observers, ``send`` for the one event that can change text."""
    description: str


EVENTS: dict[str, EventSpec] = {
    "message_received": EventSpec(
        "message_received", False, "message", "一条已通过准入的消息"
    ),
    "reply_ready": EventSpec(
        "reply_ready", True, "send", "回复文本已生成，可在投递前改写"
    ),
    "tool_before": EventSpec("tool_before", False, "message", "工具调用之前"),
    "tool_after": EventSpec("tool_after", False, "message", "工具调用之后"),
    "plugin_loaded": EventSpec(
        "plugin_loaded", False, "message", "插件加载完成（含其它插件）"
    ),
    "plugin_unloaded": EventSpec("plugin_unloaded", False, "message", "插件卸载"),
    "schedule_tick": EventSpec("schedule_tick", False, "message", "定时任务触发"),
}

WRITABLE_EVENTS = frozenset(name for name, spec in EVENTS.items() if spec.writable)


async def _maybe_await(value: Any) -> Any:
    if inspect.isawaitable(value):
        return await value
    return value


async def dispatch_event(
    loader: Any,
    name: str,
    payload: dict[str, Any],
    *,
    caller: Any = None,
) -> Any:
    """Fan ``name`` out to every loaded plugin.

    Returns the final value for writable events, ``None`` for observers. A handler
    that raises, times out, or returns a non-string for a writable event is skipped
    with a warning: an observer must never break the reply it is watching.
    """
    spec = EVENTS.get(name)
    if spec is None:
        raise ValueError(f"unknown plugin event {name!r}")
    # Every handler sees the same original payload; only ``value`` accumulates the
    # rewrites. Passing the accumulated value instead would break the next handler
    # as soon as one of them returned a string.
    base = dict(payload)
    value: Any = base
    for loaded in list(loader.loaded.values()):
        handlers = loaded.context._event_handlers.get(name) or []
        for handler in list(handlers):
            try:
                with bind_caller(caller):
                    result = await asyncio.wait_for(
                        _maybe_await(handler(dict(base))), timeout=EVENT_TIMEOUT
                    )
            except Exception as exc:
                logger.warning(
                    "plugin event failed plugin=%s event=%s err=%s",
                    loaded.name,
                    name,
                    type(exc).__name__,
                )
                continue
            if spec.writable and isinstance(result, str) and result.strip():
                value = result
    return value if spec.writable else None
