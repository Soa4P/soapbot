"""What happens to input that is not a message.

Every case here is something a real protocol end can send and a real group can produce:
``content: null``, a wall of whitespace, a 5 MB paste, a lone ``\\ud800`` escape, a frame
nested ten thousand deep. None of them are attacks in the criminal sense and none of them
are rare — they are what happens when a bot is in a busy group.

The property under test is the same in every case: the bad input is stopped at the
boundary, the bot stays up, and the operator can see that it happened. Silently dropping
is the failure mode that matters, because a bot that ignores a message and a bot that is
broken look identical from the group.
"""

from __future__ import annotations

import json

import pytest

from soapbot.config import settings
from soapbot.core.jsonguard import JsonTooDeepError, check_depth, depth_of
from soapbot.core.message import (
    EventType,
    IncomingMessage,
    MessageScene,
    MessageSegment,
    SegmentType,
    Sender,
    scrub_surrogates,
)


def _message(segments: list[MessageSegment], **kwargs) -> IncomingMessage:
    return IncomingMessage(
        adapter="test",
        message_id="m1",
        scene=MessageScene.GROUP,
        sender=Sender(user_id="10001", nickname="tester"),
        segments=segments,
        group_id="20002",
        event_type=EventType.MESSAGE,
        **kwargs,
    )


# --------------------------------------------------------------------- blank input


def test_null_content_is_blank() -> None:
    """``content: null`` arrives as an empty segment list, not as an error."""
    assert _message([]).is_blank


def test_whitespace_only_is_blank() -> None:
    """A message of spaces and newlines has nothing to answer."""
    assert _message([MessageSegment.text("   \n\t  ")]).is_blank


def test_a_bare_mention_is_blank() -> None:
    """``@bot`` with no text is an addressing gesture, not a question."""
    assert _message([MessageSegment(SegmentType.AT, {"qq": "999"})]).is_blank


def test_an_image_is_not_blank() -> None:
    """A picture with no caption is a real message: the model can describe it.

    This is the case that makes "blank means no segments" wrong. Treating an image as
    blank would silently drop every screenshot anyone ever sent.
    """
    assert not _message([MessageSegment.image(url="https://example.invalid/a.png")]).is_blank


def test_a_sticker_alone_is_blank_but_a_caption_is_not() -> None:
    face = MessageSegment(SegmentType.FACE, {"id": "1"})
    assert _message([face]).is_blank
    assert not _message([face, MessageSegment.text("看这个")]).is_blank


# ------------------------------------------------------------------- length limits


def test_one_huge_segment_is_cut_to_the_per_segment_limit(monkeypatch) -> None:
    monkeypatch.setattr(settings, "max_segment_chars", 100)
    monkeypatch.setattr(settings, "max_incoming_chars", 10_000)

    message = _message([MessageSegment.text("x" * 5_000)])

    assert message.truncated
    assert len(message.text) == 100


def test_the_total_budget_wins_over_the_per_segment_limit(monkeypatch) -> None:
    """Many legal segments must not add up to an illegal message."""
    monkeypatch.setattr(settings, "max_segment_chars", 1_000)
    monkeypatch.setattr(settings, "max_incoming_chars", 250)

    message = _message([MessageSegment.text("y" * 200) for _ in range(10)])

    assert message.truncated
    assert len(message.text) <= 250


def test_too_many_segments_keeps_the_head(monkeypatch) -> None:
    """The mention and the first line are at the front, so the head is what survives.

    Truncating from the front would drop the ``@bot`` and turn an addressed message into
    an unaddressed one — the message would be kept and the reason for it lost.
    """
    monkeypatch.setattr(settings, "max_segments", 3)
    monkeypatch.setattr(settings, "max_incoming_chars", 10_000)
    monkeypatch.setattr(settings, "max_segment_chars", 1_000)

    segments = [MessageSegment(SegmentType.AT, {"qq": "999"})]
    segments += [MessageSegment.text(f"part{i}") for i in range(10)]
    message = _message(segments)

    assert message.truncated
    assert len(message.segments) == 3
    assert message.segments[0].type is SegmentType.AT
    assert "part0" in message.text


def test_a_message_within_limits_is_untouched(monkeypatch) -> None:
    """The normal case must not be marked truncated, or the flag means nothing."""
    monkeypatch.setattr(settings, "max_segments", 64)
    monkeypatch.setattr(settings, "max_incoming_chars", 8_000)
    monkeypatch.setattr(settings, "max_segment_chars", 4_000)

    message = _message([MessageSegment.text("今天部署吗")])

    assert not message.truncated
    assert message.text == "今天部署吗"


# ------------------------------------------------------------------------ encoding


def test_a_lone_surrogate_is_replaced_not_raised() -> None:
    """A legal JSON escape can produce an illegal code point.

    ``"\\ud800"`` parses fine and then makes ``.encode("utf-8")`` raise — inside whatever
    tries to persist or log the message, far from the parse that admitted it.
    """
    broken = "前置\ud800后置"

    fixed = scrub_surrogates(broken)

    assert "\ud800" not in fixed
    assert fixed.startswith("前置")
    assert fixed.endswith("后置")
    # The point of the fix: it can now be encoded and logged.
    assert fixed.encode("utf-8")


def test_a_valid_surrogate_pair_survives() -> None:
    """Astral-plane emoji are surrogate *pairs* in UTF-16 terms and must not be mangled."""
    assert scrub_surrogates("🎉") == "🎉"


def test_surrogates_are_scrubbed_at_construction() -> None:
    message = _message([MessageSegment.text("坏\udfff字符")])

    assert "\udfff" not in message.text
    assert message.text.encode("utf-8")


# --------------------------------------------------------------------- JSON depth


def test_depth_of_counts_nesting_not_length() -> None:
    assert depth_of(b"[]") == 1
    assert depth_of(b"[[[]]]") == 3
    assert depth_of(b'{"a": {"b": 1}}') == 2
    assert depth_of(b"123") == 0


def test_an_unbalanced_close_does_not_go_negative() -> None:
    """A stray ``}`` is a syntax error the parser reports; it must not hide later opens."""
    assert depth_of(b"}}[[") == 2


def test_a_deep_payload_is_rejected_before_the_parser_sees_it() -> None:
    """The whole point: this would raise ``RecursionError``, which is not a ``ValueError``."""
    payload = "[" * 5_000 + "]" * 5_000

    with pytest.raises(JsonTooDeepError) as excinfo:
        check_depth(payload)

    # The message has to say both numbers, or the operator cannot tell how far off it was.
    assert "5000" in str(excinfo.value)
    assert str(settings.max_json_depth) in str(excinfo.value)


def test_a_shallow_payload_passes_and_reports_its_depth() -> None:
    assert check_depth(json.dumps({"a": [1, 2]})) == 2


def test_the_limit_is_read_from_settings(monkeypatch) -> None:
    monkeypatch.setattr(settings, "max_json_depth", 4)

    with pytest.raises(JsonTooDeepError):
        check_depth("[[[[[1]]]]]")

    assert check_depth("[[[1]]]") == 3


def test_the_error_is_a_value_error_so_existing_handlers_catch_it() -> None:
    """Callers already wrap decodes in ``except ValueError``; a new base class would
    silently bypass every one of them."""
    assert issubclass(JsonTooDeepError, ValueError)
