"""OneBot 11 WebSocket server.

What this is: a bridge that lets an OneBot 11 client drive an adapter which does
not speak OneBot (currently ``qq_official``). What this is **not**: a QQ protocol
end. It never logs in to an account, never speaks NTQQ, and cannot grant
permissions the official platform did not.

Security posture, stated because this is a new listening socket:

* no token means no listener — unlike the OneBot client adapter there is no
  "unauthenticated but network-isolated" escape hatch here;
* bind defaults to loopback; exposing it is an explicit configuration change;
* the token is compared with :func:`hmac.compare_digest` over either the
  ``Authorization: Bearer`` header or ``?access_token=``;
* actions are rate limited per connection and every refused connection is audited;
* message content and the token are never written to logs.
"""

from __future__ import annotations

import asyncio
import contextlib
import hmac
import json
import logging
from collections.abc import Callable
from typing import Any
from urllib.parse import parse_qs

from websockets.asyncio.server import serve as ws_serve
from websockets.exceptions import ConnectionClosed

from soapbot.core.adapter import Adapter
from soapbot.core.message import IncomingMessage
from soapbot.gateway.actions import ActionError, dispatch
from soapbot.gateway.events import to_event
from soapbot.security.audit import AuditLog, get_audit_log
from soapbot.security.ratelimit import SlidingWindowLimiter

logger = logging.getLogger(__name__)

DEFAULT_PATH = "/onebot/v11/ws"
DEFAULT_MAX_CLIENTS = 16
DEFAULT_MAX_SIZE = 1024 * 1024
DEFAULT_ACTIONS_PER_MINUTE = 600


class GatewayError(RuntimeError):
    """Configuration or lifecycle problem that must not be silently swallowed."""


class OneBot11Gateway:
    def __init__(
        self,
        adapter: Adapter,
        *,
        access_token: str,
        host: str = "127.0.0.1",
        port: int = 6700,
        path: str = DEFAULT_PATH,
        audit: AuditLog | None = None,
        max_clients: int = DEFAULT_MAX_CLIENTS,
        max_size: int = DEFAULT_MAX_SIZE,
        actions_per_minute: int = DEFAULT_ACTIONS_PER_MINUTE,
    ) -> None:
        self.adapter = adapter
        self.access_token = access_token
        self.host = host
        self.port = port
        self.path = path
        self.max_clients = max_clients
        self.max_size = max_size
        self.actions_per_minute = actions_per_minute
        self._audit_log = audit or get_audit_log()
        self._clients: set[Any] = set()
        self._server: Any = None
        self._unsubscribe: Callable[[], None] | None = None

    # ------------------------------------------------------------------ lifecycle
    async def start(self) -> None:
        if not self.access_token:
            raise GatewayError(
                "OneBot 网关拒绝以无鉴权模式启动：请设置 SOAPBOT_ONEBOT_GATEWAY_TOKEN。"
                "开放端口等于把发送能力交给任意网络对端。"
            )
        if self.adapter.meta.name == "onebot11":
            raise GatewayError(
                "OneBot 网关不能挂在 onebot11 适配器上：那只是把客户端再桥接一次，"
                "不会增加任何能力。"
            )
        self._server = await ws_serve(
            self._handler,
            self.host,
            self.port,
            max_size=self.max_size,
        )
        self._unsubscribe = self.adapter.on_event(self._on_event)
        logger.info(
            "onebot gateway listening on %s:%s%s (adapter=%s, auth=token)",
            self.host,
            self.port,
            self.path,
            self.adapter.meta.name,
        )

    async def stop(self) -> None:
        if self._unsubscribe is not None:
            self._unsubscribe()
            self._unsubscribe = None
        for ws in list(self._clients):
            with contextlib.suppress(Exception):
                await ws.close(code=1001, reason="shutdown")
        self._clients.clear()
        if self._server is not None:
            self._server.close()
            with contextlib.suppress(Exception):
                await self._server.wait_closed()
            self._server = None
        logger.info("onebot gateway stopped")

    # ------------------------------------------------------------------ transport
    def _authorized(self, ws: Any) -> bool:
        if not self.access_token:
            return False
        request = getattr(ws, "request", None)
        token = ""
        if request is not None:
            headers = getattr(request, "headers", None)
            header = ""
            if headers is not None:
                with contextlib.suppress(Exception):
                    header = headers.get("Authorization", "") or ""
            if header.lower().startswith("bearer "):
                token = header[7:].strip()
            if not token:
                path = getattr(request, "path", "") or ""
                if "?" in path:
                    query = parse_qs(path.split("?", 1)[1])
                    token = (query.get("access_token") or [""])[0]
        return bool(token) and hmac.compare_digest(token, self.access_token)

    async def _handler(self, ws: Any) -> None:
        if not self._authorized(ws):
            self._audit("connect", "deny", "missing or invalid token")
            await ws.close(code=1008, reason="unauthorized")
            return
        if len(self._clients) >= self.max_clients:
            self._audit("connect", "deny", "client limit reached")
            await ws.close(code=1013, reason="too many clients")
            return

        self._clients.add(ws)
        self._audit("connect", "allow", "client connected")
        limiter = SlidingWindowLimiter(
            limit=self.actions_per_minute, window_seconds=60.0
        )
        try:
            async for raw in ws:
                await self._handle_frame(ws, raw, limiter)
        except ConnectionClosed:
            # Expected: the client went away. The finally block removes it and writes
            # the audit entry, so this is not a swallowed failure — it is the normal
            # end of a WebSocket session.
            logger.debug("onebot gateway client disconnected")
        finally:
            self._clients.discard(ws)
            self._audit("disconnect", "allow", "client disconnected")

    async def _handle_frame(
        self, ws: Any, raw: str | bytes, limiter: SlidingWindowLimiter
    ) -> None:
        try:
            payload = json.loads(raw)
        except (ValueError, TypeError):
            await self._reply(ws, 1400, "invalid json", None, None)
            return
        if not isinstance(payload, dict):
            await self._reply(ws, 1400, "payload must be an object", None, None)
            return

        echo = payload.get("echo")
        action = str(payload.get("action") or "")
        params = payload.get("params") or {}
        if not limiter.check(str(id(ws))).allowed:
            self._audit("action", "deny", "rate limited")
            await self._reply(ws, 1200, "action rate limited", None, echo)
            return

        try:
            data = await dispatch(self.adapter, action, params)
        except ActionError as exc:
            self._audit("action", "deny", f"{action}: {exc.wording}"[:200])
            await self._reply(ws, exc.retcode, exc.wording, None, echo)
            return
        except Exception as exc:
            logger.exception("onebot gateway action failed action=%s", action)
            self._audit("action", "deny", f"{action}: {type(exc).__name__}")
            await self._reply(ws, 1200, f"internal error: {type(exc).__name__}", None, echo)
            return

        self._audit("action", "allow", action)
        await self._reply(ws, 0, "", data, echo)

    async def _reply(
        self,
        ws: Any,
        retcode: int,
        wording: str,
        data: Any,
        echo: Any,
    ) -> None:
        payload: dict[str, Any] = {
            "status": "ok" if retcode == 0 else "failed",
            "retcode": retcode,
            "data": data,
        }
        if wording:
            payload["wording"] = wording
        if echo is not None:
            payload["echo"] = echo
        await self._safe_send(ws, payload)

    async def _safe_send(self, ws: Any, payload: dict[str, Any]) -> None:
        try:
            await ws.send(json.dumps(payload, ensure_ascii=False))
        except Exception:
            # A dead client is removed on the next successful read or on broadcast;
            # raising here would take down the handler for a client that already left.
            self._clients.discard(ws)

    # ------------------------------------------------------------------ broadcast
    async def _on_event(self, message: IncomingMessage) -> None:
        if not self._clients:
            return
        payload = json.dumps(to_event(message), ensure_ascii=False)
        clients = list(self._clients)
        results = await asyncio.gather(
            *(client.send(payload) for client in clients), return_exceptions=True
        )
        for client, result in zip(clients, results, strict=False):
            if isinstance(result, Exception):
                self._clients.discard(client)
                self._audit("broadcast", "deny", type(result).__name__)

    # ------------------------------------------------------------------ audit
    def _audit(self, action: str, outcome: str, detail: str) -> None:
        if self._audit_log is None:
            return
        with contextlib.suppress(Exception):
            self._audit_log.record(
                kind="gateway", action=action, outcome=outcome, detail=detail
            )


__all__ = ["DEFAULT_PATH", "GatewayError", "OneBot11Gateway"]
