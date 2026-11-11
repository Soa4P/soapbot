"""OneBot 11 action dispatch.

The action table is explicit on purpose. A generic "forward whatever the client
sent" would make every typo look like a supported call and every platform
limitation look like a transient failure. Unknown actions return ``1404`` with a
wording, so the client sees "this is not implemented" rather than an empty
success.

Capability ceiling is enforced by the platform, not by wishful mapping: the
official bot has no group list and no friend list, so those actions are refused
here instead of returning an empty array that reads like "you have no groups".
"""

from __future__ import annotations

from collections.abc import Awaitable, Callable
from typing import Any

from soapbot import __version__
from soapbot.adapters.onebot11 import parse_message_array
from soapbot.core.adapter import Adapter
from soapbot.core.message import MessageScene, MessageSegment, OutgoingMessage, SegmentType

UNKNOWN_ACTION = 1404
BAD_PARAMS = 1400
SEND_FAILED = 1200


class ActionError(Exception):
    """An action that cannot be completed, with the retcode the client should see."""

    def __init__(self, retcode: int, wording: str) -> None:
        super().__init__(wording)
        self.retcode = retcode
        self.wording = wording


def _require(params: dict[str, Any], key: str) -> str:
    value = params.get(key)
    if value is None or value == "":
        raise ActionError(BAD_PARAMS, f"{key} is required")
    return str(value)


def _segments(params: dict[str, Any]) -> list[MessageSegment]:
    raw = params.get("message")
    if raw is None:
        raw = params.get("raw_message", "")
    if params.get("auto_escape"):
        return [MessageSegment.text(str(raw))]
    return parse_message_array(raw)


async def _send(adapter: Adapter, params: dict[str, Any], *, scene: MessageScene) -> dict[str, Any]:
    segments = _segments(params)
    if scene is MessageScene.GROUP:
        message = OutgoingMessage(
            scene=scene, segments=segments, group_id=_require(params, "group_id")
        )
    else:
        message = OutgoingMessage(
            scene=scene, segments=segments, user_id=_require(params, "user_id")
        )
    receipt = await adapter.send(message)
    if not receipt.ok:
        raise ActionError(SEND_FAILED, receipt.error or "send failed")
    return {"message_id": receipt.message_id}


async def _send_group_msg(adapter: Adapter, params: dict[str, Any]) -> dict[str, Any]:
    return await _send(adapter, params, scene=MessageScene.GROUP)


async def _send_private_msg(adapter: Adapter, params: dict[str, Any]) -> dict[str, Any]:
    return await _send(adapter, params, scene=MessageScene.PRIVATE)


async def _send_msg(adapter: Adapter, params: dict[str, Any]) -> dict[str, Any]:
    """Route by ``message_type``, inferring it from the id that was supplied.

    Inference is limited to the unambiguous case: a caller that sends ``group_id``
    without ``message_type`` means the group. If both ids are present, the explicit
    ``message_type`` wins and a missing one is an error rather than a guess.
    """
    message_type = str(params.get("message_type") or "").strip().lower()
    if not message_type:
        has_group = bool(params.get("group_id"))
        has_user = bool(params.get("user_id"))
        if has_group and not has_user:
            message_type = "group"
        elif has_user and not has_group:
            message_type = "private"
        else:
            raise ActionError(BAD_PARAMS, "message_type is required")
    if message_type == "group":
        return await _send_group_msg(adapter, params)
    if message_type == "private":
        return await _send_private_msg(adapter, params)
    raise ActionError(BAD_PARAMS, f"unknown message_type: {message_type}")


async def _get_login_info(adapter: Adapter, params: dict[str, Any]) -> dict[str, Any]:
    info = await adapter.get_self()
    return {
        "user_id": getattr(info, "self_id", ""),
        "nickname": getattr(info, "nickname", ""),
    }


async def _get_status(adapter: Adapter, params: dict[str, Any]) -> dict[str, Any]:
    online = bool(getattr(adapter.health, "online", False))
    return {"online": online, "good": online}


async def _get_version_info(adapter: Adapter, params: dict[str, Any]) -> dict[str, Any]:
    return {
        "app_name": "soapbot",
        "app_version": __version__,
        "protocol_version": "v11",
        "adapter": adapter.meta.name,
    }


async def _can_send(adapter: Adapter, params: dict[str, Any], *, seg: SegmentType) -> dict[str, Any]:
    return {"yes": adapter.supports_segment(seg)}


async def _can_send_image(adapter: Adapter, params: dict[str, Any]) -> dict[str, Any]:
    return await _can_send(adapter, params, seg=SegmentType.IMAGE)


async def _can_send_record(adapter: Adapter, params: dict[str, Any]) -> dict[str, Any]:
    return await _can_send(adapter, params, seg=SegmentType.RECORD)


async def _unavailable(adapter: Adapter, params: dict[str, Any]) -> dict[str, Any]:
    raise ActionError(
        UNKNOWN_ACTION,
        "not available on the official QQ bot platform (no group/friend listing)",
    )


Handler = Callable[[Adapter, dict[str, Any]], Awaitable[dict[str, Any]]]

_HANDLERS: dict[str, Handler] = {
    "send_msg": _send_msg,
    "send_group_msg": _send_group_msg,
    "send_private_msg": _send_private_msg,
    "get_login_info": _get_login_info,
    "get_status": _get_status,
    "get_version_info": _get_version_info,
    "can_send_image": _can_send_image,
    "can_send_record": _can_send_record,
    # Explicitly refused rather than silently empty.
    "get_group_list": _unavailable,
    "get_friend_list": _unavailable,
}


async def dispatch(
    adapter: Adapter, action: str, params: dict[str, Any] | None = None
) -> dict[str, Any]:
    """Run one action. Raises :class:`ActionError` for anything the client should see."""
    handler = _HANDLERS.get(action)
    if handler is None:
        raise ActionError(UNKNOWN_ACTION, f"unsupported action: {action or '(empty)'}")
    payload = params if isinstance(params, dict) else {}
    return await handler(adapter, payload)


__all__ = ["BAD_PARAMS", "SEND_FAILED", "UNKNOWN_ACTION", "ActionError", "dispatch"]
