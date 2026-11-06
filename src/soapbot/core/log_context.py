"""Request-scoped locating fields for logs.

The chat pipeline already had ``ctx.event.trace_id``. HTTP requests had nothing, so
a line in the log ring could not be tied back to the request that produced it, and
a concurrent request's fields had nowhere to live but a global. ContextVar keeps the
two mechanisms from becoming three: the middleware binds the HTTP ids, the pipeline
bridges its own trace id into the same variable, and the formatter reads one dict.

Nothing here holds a Request object. A context that captured the request would keep
the whole body and headers alive until the task was collected.
"""

from __future__ import annotations

from contextvars import ContextVar, Token
from typing import Any

_request_id: ContextVar[str] = ContextVar("soapbot_request_id", default="")
_trace_id: ContextVar[str] = ContextVar("soapbot_trace_id", default="")
_message_id: ContextVar[str] = ContextVar("soapbot_message_id", default="")
_plugin: ContextVar[str] = ContextVar("soapbot_plugin", default="")
_provider: ContextVar[str] = ContextVar("soapbot_provider", default="")

_VARIABLES: dict[str, ContextVar[str]] = {
    "request_id": _request_id,
    "trace_id": _trace_id,
    "message_id": _message_id,
    "plugin": _plugin,
    "provider": _provider,
}


def bind(**fields: str) -> dict[str, Token[str]]:
    """Bind non-empty fields for the current task. Caller must :func:`reset` them."""
    tokens: dict[str, Token[str]] = {}
    for name, value in fields.items():
        var = _VARIABLES.get(name)
        if var is not None and value:
            tokens[name] = var.set(str(value))
    return tokens


def reset(tokens: dict[str, Token[str]]) -> None:
    for name, token in tokens.items():
        _VARIABLES[name].reset(token)


def fields() -> dict[str, str]:
    """Only present fields are returned: an all-empty dict would be log noise."""
    return {name: var.get() for name, var in _VARIABLES.items() if var.get()}


def bridge_trace_id(trace_id: str) -> dict[str, Token[str]]:
    """Let the chat pipeline reuse the HTTP trace id instead of inventing another."""
    return bind(trace_id=trace_id)


def current_trace_id() -> str:
    return _trace_id.get()


def describe() -> dict[str, Any]:
    """Small helper for tests and the doctor command."""
    return {"names": list(_VARIABLES), "values": fields()}
