"""OneBot v11 adapter.

Two connection modes, both supported:

* **Forward (client)**: soapbot dials the protocol implementation
  (NapCat / Lagrange) at ``ws://host:port`` and consumes its event stream.
* **Reverse (server)**: soapbot listens and the protocol implementation dials
  us. This is the recommended mode behind NAT.

Design constraints:
- We implement the *protocol client* only. No QQ protocol reverse engineering.
- OneBot v11 message arrays are mapped to ``MessageSegment``; anything we do not
  understand degrades to plain text rather than raising.
- API calls are correlated by ``echo`` so concurrent sends cannot cross wires.
"""

from __future__ import annotations

import asyncio
import contextlib
import hmac
import json
import logging
import time
import uuid
from typing import Any

from websockets.asyncio.client import connect as ws_connect
from websockets.asyncio.server import serve as ws_serve

from soapbot.core.adapter import Adapter, AdapterMeta, Capability
from soapbot.core.message import (
    EventType,
    IncomingMessage,
    MessageReceipt,
    MessageScene,
    MessageSegment,
    OutgoingMessage,
    SegmentType,
    Sender,
)

logger = logging.getLogger(__name__)

_CAPABILITIES = frozenset(
    {
        Capability.TEXT,
        Capability.IMAGE,
        Capability.AT,
        Capability.REPLY,
        Capability.FACE,
        Capability.RECORD,
        Capability.VIDEO,
        Capability.FILE,
        Capability.FORWARD,
        Capability.RECALL,
        Capability.MUTE,
        Capability.KICK,
        Capability.GROUP_LIST,
        # OneBot has no rate limit of its own beyond the reported 5 msg/s, and each
        # send is an ordinary message, so sentence-by-sentence delivery is safe here.
        Capability.PROGRESSIVE,
    }
)

_SEG_TYPE_MAP = {
    "text": SegmentType.TEXT,
    "image": SegmentType.IMAGE,
    "at": SegmentType.AT,
    "reply": SegmentType.REPLY,
    "face": SegmentType.FACE,
    "record": SegmentType.RECORD,
    "video": SegmentType.VIDEO,
    "file": SegmentType.FILE,
    "forward": SegmentType.FORWARD,
}


def parse_message_array(raw: Any) -> list[MessageSegment]:
    """Convert a OneBot message array (or CQ string) into segments."""
    segments: list[MessageSegment] = []

    if isinstance(raw, str):
        # Protocol implementations may return a CQ-code string. We do not parse
        # CQ codes exhaustively; text passes through so nothing is lost.
        if raw:
            segments.append(MessageSegment.text(raw))
        return segments

    if not isinstance(raw, list):
        return segments

    for item in raw:
        if not isinstance(item, dict):
            continue
        raw_type = str(item.get("type", ""))
        data = item.get("data") or {}
        if not isinstance(data, dict):
            data = {}
        seg_type = _SEG_TYPE_MAP.get(raw_type)
        if seg_type is None:
            text = data.get("text")
            if text:
                segments.append(MessageSegment.text(str(text)))
            continue
        segments.append(MessageSegment(seg_type, dict(data)))
    return segments


def segments_to_message_array(segments: list[MessageSegment]) -> list[dict[str, Any]]:
    out: list[dict[str, Any]] = []
    for seg in segments:
        out.append({"type": str(seg.type), "data": dict(seg.data)})
    return out


class OneBot11Adapter(Adapter):
    meta = AdapterMeta(
        name="onebot11",
        display_name="OneBot v11",
        protocol="OneBot v11",
        docs_url="https://github.com/botuniverse/onebot-11",
        notes="需自备协议端（NapCat / Lagrange）。个人号有封号风险。",
    )
    capabilities = _CAPABILITIES

    def __init__(
        self,
        *,
        account_id: str,
        mode: str = "forward",
        ws_url: str = "",
        host: str = "127.0.0.1",
        port: int = 6700,
        access_token: str = "",
        reconnect: bool = True,
        allow_unauthenticated_reverse: bool = False,
    ) -> None:
        super().__init__()
        self.account_id = account_id
        self.mode = mode
        self.ws_url = ws_url
        self.host = host
        self.port = port
        self.access_token = access_token
        self.reconnect = reconnect
        self.allow_unauthenticated_reverse = allow_unauthenticated_reverse

        self._ws: Any = None
        self._server: Any = None
        self._pending: dict[str, asyncio.Future[dict[str, Any]]] = {}
        self._send_lock = asyncio.Lock()
        self._tasks: set[asyncio.Task[Any]] = set()
        self._closed = False
        self._self_info = {"user_id": account_id, "nickname": ""}
        self._transport_authenticated = bool(access_token) or mode != "reverse"
        """Reverse mode without a token is an unauthenticated transport."""

    # ------------------------------------------------------------------ lifecycle
    async def start(self) -> None:
        self._closed = False
        if self.mode == "reverse":
            await self._start_reverse()
        else:
            await self._start_forward()

    async def _start_forward(self) -> None:
        url = self.ws_url or f"ws://{self.host}:{self.port}"
        headers = {}
        if self.access_token:
            headers["Authorization"] = f"Bearer {self.access_token}"
        self._ws = await ws_connect(url, additional_headers=headers, max_size=16 * 1024 * 1024)
        self.health.online = True
        self.health.connected_at = time.time()
        self.health.last_error = ""
        logger.info("onebot11 forward connected url=%s account=%s", url, self.account_id)
        task = asyncio.create_task(self._reader_loop(self._ws))
        self._tasks.add(task)
        task.add_done_callback(self._tasks.discard)
        await self._refresh_self_info()

    async def _start_reverse(self) -> None:
        """Listen for a reverse-WS client and *authenticate it before trusting it*.

        SECURITY — this was the single most dangerous hole in the system:

        A reverse listener that accepts any client lets an arbitrary network peer
        speak the OneBot protocol directly. Such a peer can fabricate a message
        with ``role="owner"``, ``user_id`` of the real operator, or a group id that
        is on the allow-list, and the bot would then run the full pipeline on it.
        Every downstream control — whitelist, roles, memory scope — assumes the
        transport told the truth about *who* sent what. If the transport is open,
        all of those controls are advisory only.

        So the client must present ``Authorization: Bearer <access_token>`` (or
        ``?access_token=`` as OneBot implementations commonly send it). With no
        token configured the listener refuses to start unless the operator has
        explicitly opted in via ``allow_unauthenticated_reverse`` — and even then
        events are marked ``transport_authenticated=False`` so the guard stage
        refuses to grant them any permission.
        """
        if not self.access_token and not self.allow_unauthenticated_reverse:
            raise RuntimeError(
                "反向 WebSocket 拒绝以无鉴权模式启动：请设置 access_token（推荐），"
                "或显式设置 allow_unauthenticated_reverse=True 并自行确保网络隔离。"
                "开放的反向端口等于把整个流水线暴露给任意网络对端。"
            )
        if not self.access_token:
            logger.warning(
                "onebot11 reverse listener starting WITHOUT authentication; "
                "events will be treated as unauthenticated and denied by the guard stage"
            )

        async def handler(ws: Any) -> None:
            if not self._client_authorized(ws):
                logger.warning(
                    "onebot11 reverse connection rejected: missing/invalid access token "
                    "peer=%s",
                    getattr(ws, "remote_address", "?"),
                )
                await ws.close(code=1008, reason="unauthorized")
                return

            if self._ws is not None and not self._closed:
                # A second live client would race on self._ws and interleave API
                # responses. Only one protocol implementation may be attached.
                logger.warning("onebot11 reverse: rejecting second concurrent client")
                await ws.close(code=1013, reason="already connected")
                return

            logger.info("onebot11 reverse client connected account=%s", self.account_id)
            self._ws = ws
            self.health.online = True
            self.health.connected_at = time.time()
            self.health.last_error = ""
            await self._refresh_self_info()
            await self._reader_loop(ws)

        self._server = await ws_serve(handler, self.host, self.port, max_size=16 * 1024 * 1024)
        logger.info("onebot11 reverse listening on %s:%s", self.host, self.port)

    def _client_authorized(self, ws: Any) -> bool:
        """Constant-time token comparison over header or query string."""
        if not self.access_token:
            return False
        header = ""
        request = getattr(ws, "request", None)
        if request is not None:
            try:
                header = request.headers.get("Authorization", "") or ""
            except Exception:  # pragma: no cover - defensive
                header = ""

        token = ""
        if header.lower().startswith("bearer "):
            token = header[7:].strip()
        if not token and request is not None:
            try:
                from urllib.parse import parse_qs

                qs = parse_qs(request.path.split("?", 1)[1] if "?" in request.path else "")
                token = (qs.get("access_token") or [""])[0]
            except Exception:  # pragma: no cover - defensive
                token = ""

        if not token:
            return False
        return hmac.compare_digest(token, self.access_token)

    async def stop(self) -> None:
        self._closed = True
        # Let in-flight pipelines finish before tearing down the socket: a
        # half-finished reply would otherwise be dropped silently.
        await self.drain_handlers(timeout=3.0)
        for task in list(self._tasks):
            task.cancel()
        for task in list(self._tasks):
            with contextlib.suppress(asyncio.CancelledError, Exception):
                await task
        if self._ws is not None:
            with contextlib.suppress(Exception):
                await self._ws.close()
            self._ws = None
        if self._server is not None:
            self._server.close()
            with contextlib.suppress(Exception):
                await self._server.wait_closed()
            self._server = None
        self.health.online = False
        logger.info("onebot11 stopped account=%s", self.account_id)

    # ------------------------------------------------------------------ io
    async def _reader_loop(self, ws: Any) -> None:
        try:
            async for raw in ws:
                try:
                    payload = json.loads(raw)
                except json.JSONDecodeError:
                    logger.warning("onebot11 non-json frame dropped")
                    continue
                await self._dispatch(payload)
        except asyncio.CancelledError:
            raise
        except Exception as exc:
            self.health.last_error = str(exc)
            self.health.online = False
            logger.warning("onebot11 reader ended account=%s err=%s", self.account_id, exc)
        finally:
            self.health.online = False

    async def _dispatch(self, payload: dict[str, Any]) -> None:
        # API responses carry ``echo``; events carry ``post_type``.
        echo = payload.get("echo")
        if echo is not None and echo in self._pending:
            fut = self._pending.pop(echo)
            if not fut.done():
                fut.set_result(payload)
            return

        post_type = payload.get("post_type")
        if post_type == "meta_event":
            meta_type = payload.get("meta_event_type")
            if meta_type == "lifecycle" and payload.get("sub_type") == "connect":
                await self._refresh_self_info()
            return
        if post_type == "notice":
            notice = self._to_notice(payload)
            if notice is not None:
                await self.emit(notice)
            return
        if post_type != "message":
            return

        event = self._to_incoming(payload)
        if event is not None:
            await self.emit(event)

    def _to_notice(self, payload: dict[str, Any]) -> IncomingMessage | None:
        """Translate a OneBot ``notice`` post into the shared event model.

        Previously every notice was discarded by ``if post_type != "message":
        return``. That single line meant a plugin declaring the ``notice``
        capability could register ``ctx.on_notice`` and never be called: the
        adapter never produced a notice, the adapter base never forwarded one, and
        ``PluginManager.on_notice`` had no caller. Three independent breaks, each
        invisible because the other two also failed.

        Scope: group notices only. A OneBot notice also covers friend recalls and
        private file uploads; those name a user rather than a group, and the plugin
        API's ``CallerContext`` is built around a session that a group notice can
        describe unambiguously. Refusing the rest keeps "who is in this session"
        answerable instead of guessed.
        """
        notice_type = str(payload.get("notice_type", ""))
        group_id = str(payload.get("group_id", "") or "")
        if not group_id:
            return None

        user_id = str(payload.get("user_id", "") or "")
        operator_id = str(payload.get("operator_id", "") or "")
        target_id = str(payload.get("target_id", "") or "")

        # ``notice`` is what a plugin hook receives: a flat, JSON-safe dict with a
        # stable key set. The raw payload stays on ``.raw`` but is not the contract,
        # so a protocol quirk cannot silently change what plugins see.
        notice: dict[str, Any] = {
            "type": notice_type,
            "sub_type": str(payload.get("sub_type", "") or ""),
            "group_id": group_id,
            "user_id": user_id,
            "operator_id": operator_id,
            "target_id": target_id,
            "adapter": self.meta.name,
            "self_id": str(payload.get("self_id", self.account_id)),
        }
        if notice_type == "group_upload":
            notice["file_name"] = str((payload.get("file") or {}).get("name", ""))

        return IncomingMessage(
            adapter=self.meta.name,
            # Notices have no message id; using one would collide with the real
            # message table and make reply-quoting point at nothing.
            message_id="",
            scene=MessageScene.GROUP,
            sender=Sender(user_id=user_id or operator_id),
            segments=[],
            group_id=group_id,
            self_id=str(payload.get("self_id", self.account_id)),
            timestamp=float(payload.get("time", time.time())),
            raw={"payload": payload, "notice": notice},
            event_type=EventType.NOTICE,
            transport_authenticated=self._transport_authenticated,
        )

    def _to_incoming(self, payload: dict[str, Any]) -> IncomingMessage | None:
        message_type = payload.get("message_type")
        sender_raw = payload.get("sender") or {}
        user_id = str(payload.get("user_id", ""))
        sender = Sender(
            user_id=user_id,
            nickname=str(sender_raw.get("nickname", "")),
            card=str(sender_raw.get("card", "")),
            role=str(sender_raw.get("role", "member")),
        )

        if message_type == "group":
            scene = MessageScene.GROUP
        elif message_type == "private":
            scene = MessageScene.PRIVATE
        else:
            return None  # guild/channel messages are out of scope by design

        return IncomingMessage(
            adapter=self.meta.name,
            message_id=str(payload.get("message_id", "")),
            scene=scene,
            sender=sender,
            segments=parse_message_array(payload.get("message")),
            group_id=str(payload.get("group_id", "")),
            group_name=str((payload.get("sender") or {}).get("group_name", "")),
            self_id=str(payload.get("self_id", self.account_id)),
            timestamp=float(payload.get("time", time.time())),
            raw=payload,
            event_type=EventType.MESSAGE,
            transport_authenticated=self._transport_authenticated,
        )

    async def _call(self, action: str, params: dict[str, Any], timeout: float = 30.0) -> dict[str, Any]:
        if self._ws is None:
            raise RuntimeError("onebot11 not connected")
        echo = uuid.uuid4().hex
        fut: asyncio.Future[dict[str, Any]] = asyncio.get_running_loop().create_future()
        self._pending[echo] = fut
        try:
            async with self._send_lock:
                await self._ws.send(json.dumps({"action": action, "params": params, "echo": echo}))
            return await asyncio.wait_for(fut, timeout=timeout)
        finally:
            self._pending.pop(echo, None)

    async def _refresh_self_info(self) -> None:
        try:
            resp = await self._call("get_login_info", {}, timeout=10.0)
            data = resp.get("data") or {}
            if data:
                self._self_info = {"user_id": str(data.get("user_id", self.account_id)),
                                   "nickname": str(data.get("nickname", ""))}
        except Exception as exc:  # protocol implementation may not be ready yet
            logger.debug("onebot11 get_login_info failed: %s", exc)

    async def get_self(self) -> Any:
        from soapbot.core.adapter import AccountInfo

        return AccountInfo(
            self_id=str(self._self_info.get("user_id", self.account_id)),
            nickname=str(self._self_info.get("nickname", "")),
            adapter=self.meta.name,
        )

    async def send(self, message: OutgoingMessage) -> MessageReceipt:
        segments = self.degrade(message.segments)
        array = segments_to_message_array(segments)

        if message.reply_to and self.supports(Capability.REPLY):
            array.insert(0, {"type": "reply", "data": {"id": message.reply_to}})

        try:
            if message.scene is MessageScene.GROUP:
                resp = await self._call(
                    "send_group_msg", {"group_id": int(message.group_id), "message": array}
                )
            else:
                resp = await self._call(
                    "send_private_msg", {"user_id": int(message.user_id), "message": array}
                )
        except Exception as exc:
            logger.error("onebot11 send failed target=%s err=%s", message.target_id, exc)
            return MessageReceipt(ok=False, error=str(exc))

        if resp.get("status") == "failed" or resp.get("retcode") not in (0, 1, None):
            return MessageReceipt(ok=False, error=str(resp.get("wording") or resp.get("retcode")))
        data = resp.get("data") or {}
        return MessageReceipt(ok=True, message_id=str(data.get("message_id", "")))

    # -------------------------------------------------------------- moderation
    async def recall(self, message_id: str) -> MessageReceipt:
        """Delete one message by id.

        OneBot's ``delete_msg`` is group-agnostic: the id alone identifies the
        message, so this method cannot itself verify that the message belongs to
        the group the command came from. That check lives in the command handler,
        which looks the id up in this session's archive first — see
        ``MemoryStore.find_message``. Stated here because a reader of this file
        would otherwise reasonably assume the protocol enforced it.
        """
        try:
            resp = await self._call("delete_msg", {"message_id": int(message_id)})
        except ValueError:
            return MessageReceipt(ok=False, error="消息 ID 格式不正确")
        except Exception as exc:
            logger.warning("onebot11 delete_msg failed id=%s err=%s", message_id, exc)
            return MessageReceipt(ok=False, error=str(exc))
        if resp.get("retcode") not in (0, 1, None):
            return MessageReceipt(ok=False, error=str(resp.get("wording") or resp.get("retcode")))
        return MessageReceipt(ok=True)

    async def set_group_ban(
        self, group_id: str, user_id: str, duration_seconds: int
    ) -> MessageReceipt:
        """Mute for ``duration_seconds``; ``0`` unmutes.

        The duration is clamped here as well as in the command layer. Two clamps is
        not redundancy for its own sake: this method is also reachable from an HTTP
        admin route and from a plugin surface, and the one guarantee that must hold
        regardless of the caller is "nobody gets muted for a decade because a
        caller passed a raw number".
        """
        duration = max(0, min(int(duration_seconds), 30 * 24 * 3600))
        try:
            resp = await self._call(
                "set_group_ban",
                {
                    "group_id": int(group_id),
                    "user_id": int(user_id),
                    "duration": duration,
                },
            )
        except ValueError:
            return MessageReceipt(ok=False, error="群号或 QQ 号格式不正确")
        except Exception as exc:
            logger.warning("onebot11 set_group_ban failed group=%s err=%s", group_id, exc)
            return MessageReceipt(ok=False, error=str(exc))
        if resp.get("retcode") not in (0, 1, None):
            return MessageReceipt(ok=False, error=str(resp.get("wording") or resp.get("retcode")))
        return MessageReceipt(ok=True)

    async def set_group_kick(
        self, group_id: str, user_id: str, *, reject_add_request: bool = False
    ) -> MessageReceipt:
        """Remove a member. ``reject_add_request`` also blocks re-entry.

        Defaults to False: a kick is reversible by re-joining, a block is not, and
        the reversible option is the right default for an action triggered from a
        chat message where the caller may have misread a nickname.
        """
        try:
            resp = await self._call(
                "set_group_kick",
                {
                    "group_id": int(group_id),
                    "user_id": int(user_id),
                    # OneBot spellings differ across implementations
                    # (``reject_add_request`` vs ``reject_add`` vs nothing at all).
                    # Sending the common one and tolerating rejection is worse than
                    # sending nothing: a protocol端 that ignores the key silently
                    # downgrades a block to a kick.
                    "reject_add_request": bool(reject_add_request),
                },
            )
        except ValueError:
            return MessageReceipt(ok=False, error="群号或 QQ 号格式不正确")
        except Exception as exc:
            logger.warning("onebot11 set_group_kick failed group=%s err=%s", group_id, exc)
            return MessageReceipt(ok=False, error=str(exc))
        if resp.get("retcode") not in (0, 1, None):
            return MessageReceipt(ok=False, error=str(resp.get("wording") or resp.get("retcode")))
        return MessageReceipt(ok=True)

    async def get_group_list(self) -> list[dict[str, Any]]:
        try:
            resp = await self._call("get_group_list", {}, timeout=10.0)
        except Exception as exc:
            logger.warning("onebot11 get_group_list failed: %s", exc)
            return []
        out: list[dict[str, Any]] = []
        for row in resp.get("data") or []:
            if not isinstance(row, dict):
                continue
            out.append(
                {
                    "group_id": str(row.get("group_id", "")),
                    "group_name": str(row.get("group_name", "")),
                }
            )
        return out
