"""Logging setup: JSON structured logs + in-memory ring buffer for the WebUI stream."""

from __future__ import annotations

import logging
import sys
from collections import deque
from datetime import UTC, datetime
from typing import Any

from soapbot.config import settings

_RING: deque[dict[str, Any]] = deque(maxlen=settings.log_ring_size)


def get_ring() -> deque[dict[str, Any]]:
    """Expose the in-memory log ring buffer (consumed by the WebUI WebSocket)."""
    return _RING


class RingBufferHandler(logging.Handler):
    """Keeps the last N records in memory so the WebUI can stream them."""

    def emit(self, record: logging.LogRecord) -> None:
        try:
            _RING.append(
                {
                    "ts": datetime.fromtimestamp(record.created, UTC).isoformat(),
                    "level": record.levelname,
                    "logger": record.name,
                    "msg": record.getMessage(),
                }
            )
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
        fmt = '{"ts":"%(asctime)s","level":"%(levelname)s","logger":"%(name)s","msg":"%(message)s"}'
    else:
        fmt = "%(asctime)s %(levelname)-7s %(name)s | %(message)s"
    stream.setFormatter(logging.Formatter(fmt))
    root.addHandler(stream)
    root.addHandler(RingBufferHandler())

    # Trim noisy third-party loggers.
    for noisy in ("httpx", "httpcore", "websockets.client", "websockets.server"):
        logging.getLogger(noisy).setLevel(logging.WARNING)
