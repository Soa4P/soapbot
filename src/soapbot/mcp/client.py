"""A minimal MCP client over stdio.

Why not the official SDK
------------------------
The plan named the ``mcp`` Python SDK. This implementation does the three calls that
are actually used — ``initialize``, ``tools/list``, ``tools/call`` — over the stdio
transport, which is newline-delimited JSON-RPC 2.0. That is about 150 lines, has no
transitive dependencies, and can be exercised in tests against a fake server process.

The SDK would pull a dependency tree into an *optional* capability, and an MCP server
tool list is hostile input by definition (a server is third-party code), so the parsing
surface wants to be small and visible rather than delegated. If a future MCP feature
needs sampling/roots/prompts, adopting the SDK then is the right call.

Trust model
-----------
A tool exposed by an MCP server runs **in that server's process**, so the host cannot
sandbox it. What the host controls is which callers may see and call it: every tool
carries a ``min_role`` taken from configuration, and the filter runs on every request
rather than once at start-up.
"""

from __future__ import annotations

import asyncio
import contextlib
import json
import logging
import os
import shutil
from dataclasses import dataclass, field
from typing import Any

logger = logging.getLogger(__name__)

PROTOCOL_VERSION = "2024-11-05"

#: Tool names are namespaced so one server cannot shadow another's tool, and so a
#: model-issued name can be routed without consulting a global registry.
NAME_PREFIX = "mcp"


class McpError(RuntimeError):
    """Any failure talking to a server: spawn, protocol, or timeout."""


@dataclass(slots=True)
class McpServer:
    name: str
    command: tuple[str, ...]
    env: dict[str, str] = field(default_factory=dict)
    timeout: float = 20.0
    min_role: str = "member"
    """Lowest role allowed to see and call this server's tools."""

    description: str = ""


@dataclass(slots=True)
class McpTool:
    server: str
    name: str
    qualified_name: str
    description: str
    parameters: dict[str, Any]


class McpClient:
    """One server process. Connects lazily, restarts on the next call if it died."""

    def __init__(self, server: McpServer) -> None:
        self.server = server
        self._proc: asyncio.subprocess.Process | None = None
        self._next_id = 0
        self._lock = asyncio.Lock()
        self.last_error = ""

    # ------------------------------------------------------------------ lifecycle
    async def _ensure_started(self) -> None:
        if self._proc is not None and self._proc.returncode is None:
            # A ``None`` return code does not prove the child is usable: asyncio only
            # sets it once the watcher has reaped the process, so a child that died a
            # moment ago still looks alive here. Writing to it then raises
            # ``ConnectionResetError`` from the transport — not an ``McpError`` — and
            # that used to escape every ``except McpError`` up the stack. The pipe is
            # the honest liveness signal: if stdin is closed, restart.
            if self._proc.stdin is not None and not self._proc.stdin.is_closing():
                return
            self._proc = None

        command = self.server.command
        if not command:
            raise McpError(f"server {self.server.name} has no command")
        executable = shutil.which(command[0])
        if executable is None:
            # Resolved through PATH rather than passed to a shell: a configured
            # command is never interpreted by /bin/sh, so a value from a config file
            # cannot chain a second command.
            raise McpError(f"server {self.server.name}: {command[0]!r} not found on PATH")

        env = {**os.environ, **self.server.env}
        try:
            self._proc = await asyncio.create_subprocess_exec(
                executable,
                *command[1:],
                stdin=asyncio.subprocess.PIPE,
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.DEVNULL,
                env=env,
            )
        except OSError as exc:
            raise McpError(f"server {self.server.name} failed to start: {exc}") from exc

        # Handshake inline rather than through _request: _request would try to start
        # the server first, which is the call we are already inside.
        self._next_id += 1
        await self._send(
            {
                "jsonrpc": "2.0",
                "id": self._next_id,
                "method": "initialize",
                "params": {
                    "protocolVersion": PROTOCOL_VERSION,
                    "capabilities": {},
                    "clientInfo": {"name": "soapbot", "version": "0.1.0"},
                },
            }
        )
        await asyncio.wait_for(
            self._await_response(self._next_id), timeout=self.server.timeout
        )
        await self._notify("notifications/initialized", {})
        # Cleared on success, not only set on failure. Without this a server that went
        # down and came back keeps reporting the old error, so "reconnect" appears to
        # have done nothing and the operator restarts the whole process for nothing.
        self.last_error = ""
        logger.info("mcp server up name=%s pid=%s", self.server.name, self._proc.pid)

    async def close(self) -> None:
        proc, self._proc = self._proc, None
        if proc is None or proc.returncode is not None:
            return
        proc.terminate()
        with contextlib.suppress(asyncio.TimeoutError):
            await asyncio.wait_for(proc.wait(), timeout=3.0)
        if proc.returncode is None:  # pragma: no cover - stubborn child
            proc.kill()

    # -------------------------------------------------------------------- protocol
    async def _send(self, payload: dict[str, Any]) -> None:
        proc = self._proc
        if proc is None or proc.stdin is None:
            raise McpError(f"server {self.server.name} is not running")
        line = json.dumps(payload, ensure_ascii=False).encode("utf-8") + b"\n"
        try:
            proc.stdin.write(line)
            await proc.stdin.drain()
        except (ConnectionResetError, BrokenPipeError, RuntimeError) as exc:
            # A child that exited between the liveness check and this write. Translated
            # here so callers see the same error type as every other failure: a refresh
            # must report "this server is down", not crash the endpoint.
            self.last_error = "connection lost"
            self._proc = None
            raise McpError(f"server {self.server.name} is not running: {exc}") from exc

    async def _notify(self, method: str, params: dict[str, Any]) -> None:
        await self._send({"jsonrpc": "2.0", "method": method, "params": params})

    async def _request(self, method: str, params: dict[str, Any]) -> dict[str, Any]:
        """Send a request and wait for its response, ignoring server notifications."""
        async with self._lock:
            await self._ensure_started()
            self._next_id += 1
            request_id = self._next_id
            await self._send(
                {"jsonrpc": "2.0", "id": request_id, "method": method, "params": params}
            )
            try:
                result = await asyncio.wait_for(
                    self._await_response(request_id), timeout=self.server.timeout
                )
            except TimeoutError as exc:
                self.last_error = f"timeout after {self.server.timeout:.0f}s"
                raise McpError(f"server {self.server.name}: {method} timed out") from exc
            # Cleared on success. A timeout followed by a working call is the normal
            # shape of a recovering server, and the panel must stop reporting the old
            # error once calls succeed again.
            self.last_error = ""
            return result

    async def _await_response(self, request_id: int) -> dict[str, Any]:
        proc = self._proc
        if proc is None or proc.stdout is None:
            raise McpError(f"server {self.server.name} is not running")
        while True:
            line = await proc.stdout.readline()
            if not line:
                self.last_error = "connection closed"
                raise McpError(f"server {self.server.name} closed the connection")
            try:
                message = json.loads(line)
            except json.JSONDecodeError:
                # Servers may print diagnostic noise on stdout; a debug line must not
                # kill an otherwise healthy session.
                logger.debug("mcp %s: non-JSON line %r", self.server.name, line[:120])
                continue
            if message.get("id") != request_id:
                continue
            if "error" in message:
                raise McpError(
                    f"server {self.server.name}: {message['error'].get('message', 'error')}"
                )
            return message.get("result") or {}

    # ------------------------------------------------------------------------ api
    async def list_tools(self) -> list[McpTool]:
        result = await self._request("tools/list", {})
        tools: list[McpTool] = []
        for raw in result.get("tools") or []:
            name = str(raw.get("name") or "")
            if not name:
                continue
            tools.append(
                McpTool(
                    server=self.server.name,
                    name=name,
                    qualified_name=f"{NAME_PREFIX}__{self.server.name}__{name}",
                    description=str(raw.get("description") or ""),
                    parameters=raw.get("inputSchema") or {"type": "object", "properties": {}},
                )
            )
        return tools

    async def call_tool(self, name: str, arguments: dict[str, Any]) -> str:
        result = await self._request("tools/call", {"name": name, "arguments": arguments})
        parts: list[str] = []
        for item in result.get("content") or []:
            if isinstance(item, dict) and item.get("type") == "text":
                parts.append(str(item.get("text", "")))
        text = "\n".join(p for p in parts if p).strip()
        if result.get("isError"):
            raise McpError(text or "tool reported an error")
        return text


class McpManager:
    """All configured servers, exposed as one tool source for the registry."""

    def __init__(self, servers: list[McpServer], *, role_rank=None) -> None:
        self._clients = {s.name: McpClient(s) for s in servers}
        self._servers = {s.name: s for s in servers}
        self._tools: dict[str, list[McpTool]] = {}
        self._role_rank = role_rank

    @property
    def configured(self) -> bool:
        return bool(self._clients)

    async def ensure_tools(self) -> None:
        """Refresh the tool list. A dead server is retried on the next refresh.

        Only ``Exception`` is caught, not just ``McpError``: one broken server must not
        abort the refresh for the others. The failure is recorded as an empty list plus
        an error string, so the endpoint can report *which* server is down instead of
        failing the whole request.
        """
        for name, client in self._clients.items():
            try:
                self._tools[name] = await client.list_tools()
            except Exception as exc:
                self._tools[name] = []
                logger.warning("mcp tool listing failed server=%s: %s", name, exc)

    async def close(self) -> None:
        for client in self._clients.values():
            with contextlib.suppress(Exception):
                await client.close()

    def status(self) -> dict[str, Any]:
        return {
            "servers": [
                {
                    "name": name,
                    "min_role": server.min_role,
                    "tools": len(self._tools.get(name) or []),
                    "error": self._clients[name].last_error,
                }
                for name, server in self._servers.items()
            ],
            "tools": sum(len(v) for v in self._tools.values()),
        }

    # --------------------------------------------------------------- tool source
    def schemas(self, principal) -> list[dict[str, Any]]:
        """Tool schemas this caller may see, in the registry's own shape."""
        out: list[dict[str, Any]] = []
        for server_name, tools in self._tools.items():
            server = self._servers[server_name]
            if not self._allowed(server, principal):
                continue
            for tool in tools:
                out.append(
                    {
                        "name": tool.qualified_name,
                        "description": tool.description or f"{server_name}: {tool.name}",
                        "parameters": tool.parameters,
                    }
                )
        return out

    async def call(self, name: str, arguments: dict[str, Any], *, principal) -> str | None:
        """Execute a namespaced call. Returns ``None`` when the name is not ours."""
        parts = name.split("__", 2)
        if len(parts) != 3 or parts[0] != NAME_PREFIX:
            return None
        _, server_name, tool_name = parts
        server = self._servers.get(server_name)
        client = self._clients.get(server_name)
        if server is None or client is None:
            raise McpError(f"unknown MCP server {server_name}")
        if not self._allowed(server, principal):
            raise McpError(f"not permitted to call {server_name} tools")
        return await client.call_tool(tool_name, arguments)

    def _allowed(self, server: McpServer, principal) -> bool:
        if self._role_rank is None:
            return True
        role = getattr(principal, "role", None)
        current = self._role_rank(role)
        return current >= self._role_rank(server.min_role)

