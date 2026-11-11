"""``IncomingMessage`` -> OneBot 11 event.

Only the message post type is produced. Notice and request events are not
forwarded: the official platform does not emit group join/leave events, and the
adapter itself drops the protocol handshakes before they reach a handler. Saying
"we forward everything" while emitting nothing for those types would make the
gateway look more capable than the platform is.
"""

from __future__ import annotations

from typing import Any

from soapbot.core.message import (
    IncomingMessage,
    MessageScene,
    MessageSegment,
    SegmentType,
    segments_to_plain,
)


def _segments(segments: list[MessageSegment]) -> list[dict[str, Any]]:
    out: list[dict[str, Any]] = []
    for seg in segments:
        if seg.type is SegmentType.TEXT:
            out.append({"type": "text", "data": {"text": str(seg.data.get("text", ""))}})
        elif seg.type is SegmentType.IMAGE:
            out.append({"type": "image", "data": {"file": _url(seg)}})
        elif seg.type is SegmentType.RECORD:
            out.append({"type": "record", "data": {"file": _url(seg)}})
        elif seg.type is SegmentType.AT:
            out.append({"type": "at", "data": {"qq": str(seg.data.get("qq", ""))}})
        elif seg.type is SegmentType.REPLY:
            out.append({"type": "reply", "data": {"id": str(seg.data.get("id", ""))}})
        else:
            # OneBot clients are expected to handle unknown types gracefully, but a
            # plain-text fallback is more useful than an empty segment with a name
            # the client may not know.
            out.append({"type": "text", "data": {"text": seg.plain()}})
    return out


def _url(seg: MessageSegment) -> str:
    return str(seg.data.get("url") or seg.data.get("file") or seg.data.get("path") or "")


def to_event(message: IncomingMessage) -> dict[str, Any]:
    """Build the OneBot 11 ``post_type=message`` payload.

    IDs stay strings. Official group/user openids are opaque tokens, not numbers;
    coercing them to ``int`` would either raise or silently truncate, and an
    OneBot client that requires integers is already incompatible with this
    platform's identifiers.
    """
    is_group = message.scene is MessageScene.GROUP
    event: dict[str, Any] = {
        "time": int(message.timestamp),
        "self_id": message.self_id,
        "post_type": "message",
        "message_type": "group" if is_group else "private",
        "sub_type": "normal" if is_group else "friend",
        "message_id": message.message_id,
        "message": _segments(message.segments),
        "raw_message": segments_to_plain(message.segments),
        "font": 0,
        "sender": {
            "user_id": message.sender.user_id,
            "nickname": message.sender.nickname,
            "card": message.sender.card,
            "role": message.sender.role,
        },
    }
    if is_group:
        event["group_id"] = message.group_id
    else:
        event["user_id"] = message.sender.user_id
    return event
