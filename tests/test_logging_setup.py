"""Logging must not be the thing that breaks.

The bug these tests pin: on Windows the console code page is GBK, and a group message
containing an emoji reached ``StreamHandler.emit`` and raised
``UnicodeEncodeError: 'gbk' codec can't encode character '\\u203c'``. The exception was
raised while *reporting* another error, so the traceback the operator saw was the codec
failure — the real fault ("database is locked") was never printed.

A test that only asserted "logging works" would have passed throughout. These assert the
specific property: a record the stream cannot encode must still be recorded, and must not
raise.
"""

from __future__ import annotations

import codecs
import io
import logging
import sys

import pytest

from soapbot.logging_setup import _safe_stdout, get_ring, setup_logging


class _GBKStdout(io.TextIOWrapper):
    """A stdout that behaves like a Windows console: GBK, strict.

    ``_safe_stdout`` is expected to *reconfigure* this stream, so the bytes it ends up
    holding are UTF-8 — the assertion below reads them back that way. What this class
    reproduces is the starting state: a stream that would have raised on the emoji.
    """

    def __init__(self) -> None:
        super().__init__(io.BytesIO(), encoding="gbk", errors="strict", newline="")

    def text_written(self) -> str:
        """Whatever was written, decoded the way the stream is *currently* configured."""
        return self.buffer.getvalue().decode(self.encoding or "utf-8", errors="replace")


def test_a_gbk_console_would_reject_the_emoji_this_reproduces() -> None:
    """Guard the reproducer itself.

    Without this the two tests below could stop testing anything — if ``_GBKStdout``
    silently started accepting emoji (a Python default change, say), they would pass
    while the real failure returned.
    """
    stream = _GBKStdout()
    with pytest.raises(UnicodeEncodeError):
        stream.write("顺带一提 ❗️")
        stream.flush()


def test_setup_logging_does_not_raise_on_an_unencodable_record(
    monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    """The regression: the record is reported, and nothing raises."""
    stream = _GBKStdout()
    monkeypatch.setattr(sys, "stdout", stream)

    setup_logging()
    logger = logging.getLogger("soapbot.test.emoji")

    logger.error("群消息里带了表情 \u2757\ufe0f 也不该让日志崩掉")

    for handler in logging.getLogger().handlers:
        handler.flush()
    written = stream.text_written()

    # The bug's actual signature is not a raised exception — ``Handler.handleError``
    # swallows it — it is the "--- Logging error ---" banner printed to stderr in place
    # of the record. That banner is what the operator saw where "database is locked"
    # should have been, so its absence is the assertion that matters. ``handleError``
    # writes to the real ``sys.stderr``, which is what ``capsys`` captures.
    captured = capsys.readouterr()
    assert "Logging error" not in captured.err, captured.err

    assert "群消息里带了表情" in written, written
    assert "\u2757" in written, written

    logging.getLogger().handlers.clear()


def test_the_ring_buffer_keeps_the_message_even_when_stdout_cannot(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """The WebUI stream is a second consumer, and it is not encoded at all.

    Worth its own test because it is the one place the operator can *see* the record
    after the console has mangled it.
    """
    stream = _GBKStdout()
    monkeypatch.setattr(sys, "stdout", stream)

    ring = get_ring()
    ring.clear()
    setup_logging()
    logging.getLogger("soapbot.test.ring").warning("内存里的日志 ❗️ 是完整的")

    messages = [entry["msg"] for entry in ring]
    assert any("内存里的日志" in message for message in messages), messages
    assert any("\u2757" in message for message in messages), "the emoji was lost in the ring"

    logging.getLogger().handlers.clear()
    ring.clear()


def test_a_stream_without_reconfigure_is_left_alone(monkeypatch: pytest.MonkeyPatch) -> None:
    """pytest replaces stdout with something that has no ``reconfigure``.

    ``_safe_stdout`` must return it untouched rather than raising, or every test that
    touches logging would fail in a way that looks like a logging bug.
    """

    class _Bare:
        def write(self, _text: str) -> int:
            return 0

        def flush(self) -> None:
            return None

    bare = _Bare()
    monkeypatch.setattr(sys, "stdout", bare)
    assert _safe_stdout() is bare


def test_reconfigure_failure_is_not_fatal(monkeypatch: pytest.MonkeyPatch) -> None:
    """A closed or exotic stream raises from ``reconfigure``; logging must survive it.

    Not hypothetical: this is what happens when the process is shutting down and the
    console handle is already gone. Raising there would turn a clean exit into a
    traceback.
    """

    class _Hostile:
        def reconfigure(self, **_kwargs: object) -> None:
            raise ValueError("I/O operation on closed file")

        def write(self, _text: str) -> int:
            return 0

        def flush(self) -> None:
            return None

    hostile = _Hostile()
    monkeypatch.setattr(sys, "stdout", hostile)
    assert _safe_stdout() is hostile


def test_backslashreplace_is_what_makes_the_escape() -> None:
    """Pin the encoding choice separately from the wiring.

    ``errors="replace"`` would also avoid a raise, but it loses the character (becomes
    ``?``), and a log that says "a message with ?" is not evidence of anything. Only
    ``backslashreplace`` preserves it as an escape the operator can read back.
    """
    assert codecs.lookup_error("backslashreplace") is not None
    emoji = "\u2757\ufe0f"
    assert emoji.encode("gbk", errors="backslashreplace") == b"\\u2757\\ufe0f"
    # ...whereas the default — what the console did before the fix — raises.
    with pytest.raises(UnicodeEncodeError):
        emoji.encode("gbk")
