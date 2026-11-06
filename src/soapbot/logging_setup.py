"""Logging setup: structured JSON lines + a sanitised in-memory ring for the panel."""

from __future__ import annotations

import json
import logging
import sys
from collections import deque
from datetime import UTC, datetime
from typing import Any

from soapbot.config import settings
from soapbot.core import log_context

_RING: deque[dict[str, Any]] = deque(maxlen=settings.log_ring_size)

#: A log line is one event. A newline inside a message used to create a second,
#: entirely plausible-looking line: ``INFO ... ok`` followed by a forged
#: ``ERROR ... token=...``. Serialising the whole record with json.dumps closes the
#: JSON side; stripping controls closes the human-readable and ring-buffer sides.
MAX_LOG_CHARS = 2000
_LOCATING_FIELDS = ("request_id", "trace_id", "message_id", "plugin", "provider")


def get_ring() -> deque[dict[str, Any]]:
    """Expose the in-memory log ring buffer (consumed by the WebUI WebSocket)."""
    return _RING


def _clean_text(value: Any, *, limit: int = MAX_LOG_CHARS) -> str:
    """Escape control characters and bound the length of any log-bound string.

    Quotes and backslashes are left alone: ``json.dumps`` handles those. Escaping
    them here as well would produce double-escaped text in the human-readable format.
    """
    text = str(value)[:limit]
    return "".join(
        char if char >= " " and char != "\x7f" else f"\\u{ord(char):04x}" for char in text
    )


def _clean_and_redact(value: Any, *, limit: int = MAX_LOG_CHARS) -> str:
    """Control characters first, then credential-shaped substrings.

    The local import avoids a cycle: ``security.injection`` reads settings, and
    ``security.audit`` imports this module through the logging context.
    """
    from soapbot.security.injection import redact

    return _clean_text(redact(_clean_text(value, limit=limit)), limit=limit)


class _PlainFormatter(logging.Formatter):
    """Human-readable format whose traceback is cleaned too.

    ``logging.Formatter.format()`` appends ``record.exc_text`` *after* the format
    string has been applied, so a filter that only rewrites ``record.msg`` leaves
    the raw traceback — with an attacker's newline — on the next line.
    """

    def formatException(self, ei) -> str:  # noqa: N802 - stdlib signature
        return _clean_and_redact(logging.Formatter.formatException(self, ei), limit=4000)


class _SanitisingFilter(logging.Filter):
    """Clean the message once, before any handler sees it.

    ``record.args`` is cleared after ``getMessage()``: a second formatting pass with
    the original args could reintroduce a newline that was just escaped.
    """

    def filter(self, record: logging.LogRecord) -> bool:
        record.msg = _clean_and_redact(record.getMessage())
        record.args = ()
        present = log_context.fields()
        for name in _LOCATING_FIELDS:
            value = present.get(name, "")
            setattr(record, name, _clean_and_redact(value, limit=128) if value else "")
        return True


class StructuredFormatter(logging.Formatter):
    """One JSON object per line, with the request context as real fields."""

    def format(self, record: logging.LogRecord) -> str:
        payload: dict[str, Any] = {
            "ts": datetime.fromtimestamp(record.created, UTC).isoformat(),
            "level": record.levelname,
            "logger": record.name,
            "msg": _clean_and_redact(record.getMessage()),
        }
        for name in _LOCATING_FIELDS:
            value = getattr(record, name, "") or log_context.fields().get(name, "")
            if value:
                payload[name] = _clean_and_redact(value, limit=128)
        if record.exc_info:
            # Server-side stream only. The ring buffer deliberately omits the
            # traceback: it is readable from the panel and routinely contains paths.
            payload["exc"] = _clean_and_redact(self.formatException(record.exc_info), limit=4000)
        return json.dumps(payload, ensure_ascii=False)


class RingBufferHandler(logging.Handler):
    """Keeps the last N records in memory so the WebUI can stream them."""

    def emit(self, record: logging.LogRecord) -> None:
        try:
            entry: dict[str, Any] = {
                "ts": datetime.fromtimestamp(record.created, UTC).isoformat(),
                "level": record.levelname,
                "logger": record.name,
                "msg": _clean_and_redact(record.getMessage()),
            }
            present = log_context.fields()
            for name in _LOCATING_FIELDS:
                if present.get(name):
                    entry[name] = _clean_and_redact(present[name], limit=128)
            _RING.append(entry)
        except Exception:  # pragma: no cover - logging must never raise
            self.handleError(record)


def _safe_stdout() -> Any:
    """A stdout that cannot fail on a character it was not asked to encode.

    On Windows the console code page is GBK by default, and a group message containing
    an emoji reached the log as ``UnicodeEncodeError: 'gbk' codec can't encode
    character '\\u203c'``. Two consequences, both bad: the log line was lost, and — worse
    — the exception was raised inside ``StreamHandler.emit``, so the traceback printed
    was the *logging* failure, not the database error that was being reported. The
    operator saw a codec error where the real fault was ``database is locked``.

    Reconfiguring the stream to UTF-8 with ``backslashreplace`` keeps the message and
    makes an unencodable character a visible escape (``\\u203c``) instead of a crash.
    """
    stream = sys.stdout
    reconfigure = getattr(stream, "reconfigure", None)
    if reconfigure is None:  # pragma: no cover - a replaced stream in tests
        return stream
    try:
        reconfigure(encoding="utf-8", errors="backslashreplace")
    except (ValueError, OSError):  # pragma: no cover - closed or exotic stream
        return stream
    return stream


def setup_logging() -> None:
    root = logging.getLogger()
    root.setLevel(settings.log_level.upper())
    root.handlers.clear()

    stream = logging.StreamHandler(_safe_stdout())
    if settings.log_json:
        stream.setFormatter(StructuredFormatter())
    else:
        stream.setFormatter(_PlainFormatter("%(asctime)s %(levelname)-7s %(name)s | %(message)s"))

    sanitising = _SanitisingFilter()
    for handler in (stream, RingBufferHandler()):
        handler.addFilter(sanitising)
        root.addHandler(handler)

    # uvicorn installs its own handlers with propagate=False when started with the
    # default logging config. Those lines would bypass the filter above, so give
    # their handlers the same cleaning rather than assuming every logger reaches root.
    for name in ("uvicorn", "uvicorn.error", "uvicorn.access"):
        third_party = logging.getLogger(name)
        for handler in third_party.handlers:
            handler.addFilter(sanitising)

    # Trim noisy third-party loggers.
    for noisy in ("httpx", "httpcore", "websockets.client", "websockets.server"):
        logging.getLogger(noisy).setLevel(logging.WARNING)
