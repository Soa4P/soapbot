"""Mock OneBot v11 protocol implementation for tests.

This is a *first-class* verification tool, not a stub: it speaks real OneBot v11
JSON over WebSocket, records every action the bot calls, and can inject events.
Because no real QQ credentials exist in this environment, this mock is how the
end-to-end path (inbound message -> persona -> model -> persist -> send) is
proven.
"""

from __future__ import annotations

import asyncio
import contextlib
import json
import logging
import time
import uuid
from typing import Any

from websockets.asyncio.server import serve as ws_serve

logger = logging.getLogger(__name__)


class MockOneBot11Server:
    """A minimal but protocol-faithful OneBot v11 endpoint."""

    def __init__(self, host: str = "127.0.0.1", port: int = 0) -> None:
        self.host = host
        self.port = port
        self._server: Any = None
        self._ws: Any = None
        self.received_actions: list[dict[str, Any]] = []
        self._connected = asyncio.Event()
        self.self_id = "10000"
        self._handler_tasks: set[asyncio.Task[Any]] = set()

    @property
    def url(self) -> str:
        port = self._server.sockets[0].getsockname()[1] if self._server else self.port
        return f"ws://{self.host}:{port}"

    async def start(self) -> None:
        async def handler(ws: Any) -> None:
            self._ws = ws
            self._connected.set()
            logger.info("mock onebot client connected")
            try:
                async for raw in ws:
                    try:
                        payload = json.loads(raw)
                    except json.JSONDecodeError:
                        continue
                    await self._handle_action(payload)
            except Exception:
                logger.debug("mock onebot handler ended", exc_info=True)
            finally:
                if self._ws is ws:
                    self._ws = None

        self._server = await ws_serve(handler, self.host, self.port)

    async def stop(self) -> None:
        self._connected.clear()
        if self._ws is not None:
            with contextlib.suppress(Exception):
                await self._ws.close()
            self._ws = None
        if self._server is not None:
            self._server.close()
            with contextlib.suppress(Exception):
                await self._server.wait_closed()
            self._server = None
        for task in list(self._handler_tasks):
            task.cancel()
        self._handler_tasks.clear()
        # Let connection handlers unwind before the test's event loop closes.
        await asyncio.sleep(0)

    async def wait_connected(self, timeout: float = 5.0) -> None:
        await asyncio.wait_for(self._connected.wait(), timeout=timeout)

    async def _handle_action(self, payload: dict[str, Any]) -> None:
        action = str(payload.get("action", ""))
        params = payload.get("params") or {}
        echo = payload.get("echo")
        self.received_actions.append({"action": action, "params": params, "echo": echo})

        if action == "get_login_info":
            data: Any = {"user_id": int(self.self_id), "nickname": "soapbot-mock"}
        elif action in ("send_group_msg", "send_private_msg"):
            data = {"message_id": int(uuid.uuid4().int % 100000)}
        else:
            data = {}

        if self._ws is not None:
            await self._ws.send(
                json.dumps({"status": "ok", "retcode": 0, "data": data, "echo": echo})
            )

    async def push_group_message(
        self,
        *,
        group_id: str = "123456",
        user_id: str = "20001",
        nickname: str = "tester",
        text: str = "",
        segments: list[dict[str, Any]] | None = None,
        role: str = "member",
        message_id: str = "",
    ) -> str:
        message_id = message_id or str(uuid.uuid4().int % 1000000)
        message = segments if segments is not None else [{"type": "text", "data": {"text": text}}]
        payload = {
            "post_type": "message",
            "message_type": "group",
            "sub_type": "normal",
            "time": int(time.time()),
            "self_id": int(self.self_id),
            "message_id": message_id,
            "group_id": int(group_id),
            "user_id": int(user_id),
            "message": message,
            "raw_message": text,
            "sender": {"user_id": int(user_id), "nickname": nickname, "card": "", "role": role},
        }
        await self._push(payload)
        return message_id

    async def push_private_message(
        self, *, user_id: str = "20001", nickname: str = "tester", text: str = ""
    ) -> str:
        message_id = str(uuid.uuid4().int % 1000000)
        payload = {
            "post_type": "message",
            "message_type": "private",
            "sub_type": "friend",
            "time": int(time.time()),
            "self_id": int(self.self_id),
            "message_id": message_id,
            "user_id": int(user_id),
            "message": [{"type": "text", "data": {"text": text}}],
            "raw_message": text,
            "sender": {"user_id": int(user_id), "nickname": nickname, "card": "", "role": "member"},
        }
        await self._push(payload)
        return message_id

    async def push_guild_message(self, *, text: str = "guild msg") -> None:
        """Guild messages must be ignored by the bot (频道功能明确不实现)."""
        payload = {
            "post_type": "message",
            "message_type": "guild",
            "time": int(time.time()),
            "self_id": int(self.self_id),
            "message_id": "g-1",
            "message": [{"type": "text", "data": {"text": text}}],
            "sender": {"user_id": 1, "nickname": "guild-user"},
        }
        await self._push(payload)

    async def _push(self, payload: dict[str, Any]) -> None:
        if self._ws is None:
            raise RuntimeError("mock onebot: no client connected")
        await self._ws.send(json.dumps(payload))

    def sent_messages(self) -> list[dict[str, Any]]:
        return [a for a in self.received_actions if a["action"].startswith("send_")]

    def last_sent_text(self) -> str:
        sent = self.sent_messages()
        if not sent:
            return ""
        message = sent[-1]["params"].get("message") or []
        parts: list[str] = []
        for item in message:
            if isinstance(item, dict) and item.get("type") == "text":
                parts.append(str((item.get("data") or {}).get("text", "")))
        return "".join(parts)
