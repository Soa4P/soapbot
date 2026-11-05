"""Outbound HTTP: one client per process, one place that decides how it is built."""

from soapbot.net.client import (
    TRACE_HEADER,
    build_limits,
    build_timeout,
    current_trace_id,
    get_outbound,
    outbound_client,
    reset_outbound,
    reset_trace_id,
    set_trace_id,
    trace_headers,
)

__all__ = [
    "TRACE_HEADER",
    "build_limits",
    "build_timeout",
    "current_trace_id",
    "get_outbound",
    "outbound_client",
    "reset_outbound",
    "reset_trace_id",
    "set_trace_id",
    "trace_headers",
]
