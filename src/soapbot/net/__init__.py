"""Outbound HTTP: one client per process, one place that decides how it is built."""

from soapbot.net.client import (
    DRAIN_LIMIT_BYTES,
    MAX_RESPONSE_BYTES,
    TRACE_HEADER,
    ResponseTooLargeError,
    build_limits,
    build_timeout,
    current_trace_id,
    drain_capped,
    get_outbound,
    outbound_client,
    read_capped,
    reset_outbound,
    reset_trace_id,
    set_trace_id,
    trace_headers,
)

__all__ = [
    "DRAIN_LIMIT_BYTES",
    "MAX_RESPONSE_BYTES",
    "TRACE_HEADER",
    "ResponseTooLargeError",
    "build_limits",
    "build_timeout",
    "current_trace_id",
    "drain_capped",
    "get_outbound",
    "outbound_client",
    "read_capped",
    "reset_outbound",
    "reset_trace_id",
    "set_trace_id",
    "trace_headers",
]
