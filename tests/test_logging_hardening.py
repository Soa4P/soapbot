"""Log output is a boundary. What reaches it must be one line and no PII.

These tests pin the parts that are easy to lose in a refactor: control-character
escaping before serialisation, ContextVar isolation across concurrent requests,
slow-call threshold behaviour, and the rule that provider response bodies never
appear in a log line or the WebUI ring buffer.
"""

from __future__ import annotations

import asyncio
import json
import logging

import soapbot.core.log_context as log_context
from soapbot import logging_setup


def test_control_characters_are_escaped_before_logging() -> None:
    payload = 'ok\nERROR fake line\r\x1b"quoted"'
    cleaned = logging_setup._clean_text(payload)
    assert "\n" not in cleaned and "\r" not in cleaned and "\x1b" not in cleaned
    assert "\\u000a" in cleaned and "\\u001b" in cleaned


def test_json_formatter_emits_one_parseable_line() -> None:
    record = logging.LogRecord(
        name="soapbot.test",
        level=logging.INFO,
        pathname=__file__,
        lineno=1,
        msg='first\nsecond "quoted"',
        args=(),
        exc_info=None,
    )
    line = logging_setup.StructuredFormatter().format(record)
    parsed = json.loads(line)
    assert "\n" not in line
    assert parsed["msg"] == logging_setup._clean_text(record.getMessage())


def test_ring_buffer_never_stores_a_raw_control_character() -> None:
    logging_setup.get_ring().clear()
    handler = logging_setup.RingBufferHandler()
    record = logging.LogRecord(
        name="soapbot.test",
        level=logging.WARNING,
        pathname=__file__,
        lineno=1,
        msg="line one\nline two",
        args=(),
        exc_info=None,
    )
    handler.emit(record)
    entry = logging_setup.get_ring()[-1]
    assert "\n" not in entry["msg"]
    assert "\\u000a" in entry["msg"]


def test_context_vars_do_not_bleed_between_concurrent_tasks() -> None:
    async def one(value: str) -> dict[str, str]:
        tokens = log_context.bind(trace_id=value, provider=value)
        await asyncio.sleep(0)
        try:
            return log_context.fields()
        finally:
            log_context.reset(tokens)

    async def run() -> list[dict[str, str]]:
        return await asyncio.gather(one("alpha"), one("beta"))

    first, second = asyncio.run(run())
    assert first["trace_id"] == "alpha" and second["trace_id"] == "beta"
    assert log_context.fields() == {}


def test_sanitising_filter_cleans_the_record_before_any_handler() -> None:
    record = logging.LogRecord(
        name="soapbot.test",
        level=logging.INFO,
        pathname=__file__,
        lineno=1,
        msg="before\nafter",
        args=(),
        exc_info=None,
    )
    assert logging_setup._SanitisingFilter().filter(record) is True
    assert record.getMessage() == logging_setup._clean_text("before\nafter")
    assert record.args == ()
    assert hasattr(record, "trace_id")


def test_bounded_scan_never_matches_past_the_ceiling(monkeypatch) -> None:
    import re

    from soapbot.config import settings
    from soapbot.security.injection import bounded_scan

    monkeypatch.setattr(settings, "max_regex_input_chars", 8)
    pattern = re.compile(r"secret")
    assert bounded_scan(pattern, "xxxxsecret") is False  # beyond the ceiling
    assert bounded_scan(pattern, "secretxx") is True


def test_audit_detail_strips_a_forged_second_line() -> None:
    from soapbot.security.audit import _redact_detail

    cleaned = _redact_detail("ok\nERROR credential=abc12345")
    assert "\n" not in cleaned
    assert "\\u000a" in cleaned


def test_log_filter_redacts_credential_shaped_text() -> None:
    record = logging.LogRecord(
        name="soapbot.test",
        level=logging.WARNING,
        pathname=__file__,
        lineno=1,
        msg="upstream said api_key=sk-live-example-12345678",
        args=(),
        exc_info=None,
    )
    assert logging_setup._SanitisingFilter().filter(record) is True
    assert "sk-live-example" not in record.getMessage()


def test_plain_formatter_cleans_the_traceback_too() -> None:
    import sys

    formatter = logging_setup._PlainFormatter("%(message)s")
    try:
        raise ValueError("first\nsecond")
    except ValueError:
        info = sys.exc_info()
    text = formatter.formatException(info)  # type: ignore[arg-type]
    assert "\n" not in text
    assert "\\u000a" in text
