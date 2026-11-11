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
import hashlib
import json
import logging
import shutil
from dataclasses import dataclass, field
from typing import Any

from soapbot import __version__
from soapbot.core.proc_env import sanitize_env
from soapbot.security.audit import get_audit_log
from soapbot.security.injection import scrub_schema, scrub_tool_text

logger = logging.getLogger(__name__)

#: The newest version this client speaks. The server answers with the version *it*
#: supports and that answer wins, so sending our newest and accepting the reply is the
#: negotiation the spec describes. Pinning one old version instead means the day a
#: server drops it we fail a handshake we could have survived.
PROTOCOL_VERSION = "2025-06-18"

#: Versions whose wire format has been exercised against this client. An answer outside
#: this set is accepted rather than refused — ``initialize``/``tools/list``/``tools/call``
#: have not changed shape in any published version, and refusing would fail a server
#: that works — but it is logged, because "we are guessing" is worth knowing.
KNOWN_PROTOCOL_VERSIONS = frozenset({"2024-11-05", "2025-03-26", "2025-06-18"})

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

    #: Optional supply-chain pin. When set, the server's reported
    #: ``serverInfo.version`` must match exactly at handshake or the connection is
    #: refused. Empty means "record the version, do not enforce one": pinning every
    #: server would break the common case where an operator upgrades a package and
    #: expects the next start to work.
    pinned_version: str = ""

    #: Optional integrity pin for the *tool metadata* (names, descriptions and input
    #: schemas) returned by ``tools/list``. A server can change what the model is told
    #: without changing its implementation version or its argv — that is a silent
    #: capability change. When set, a digest mismatch refuses the tool list instead of
    #: treating it as an update; the operator must re-approve the new digest explicitly.
    pinned_tools_digest: str = ""


@dataclass(slots=True)
class McpTool:
    server: str
    name: str
    qualified_name: str
    description: str
    parameters: dict[str, Any]
    suspicious: bool = False
    """Whether the server's metadata tripped the injection screen.

    Kept on the record so the panel can show it *before* the tool is called. A refusal
    that only appears in the audit log after the model has already been fed the text is
    a post-mortem, not a control.
    """
    metadata_digest: str = ""
    """SHA-256 over the *raw* name / description / inputSchema, before scrubbing.

    Scrubbing is a presentation control: two different payloads can sanitise to the
    same displayed text. Hashing the original is what makes a silent edit detectable.
    """


def _canonical_digest(payload: Any) -> str:
    """Stable SHA-256 over JSON with sorted keys, independent of dict insertion order.

    Metadata arrives from a third-party process. Hashing its *serialised* form rather
    than the Python object's repr means the digest is comparable across restarts and
    across machines, which is what an approval snapshot needs.
    """
    blob = json.dumps(payload, ensure_ascii=False, sort_keys=True, separators=(",", ":"))
    return hashlib.sha256(blob.encode("utf-8")).hexdigest()


class McpClient:
    """One server process. Connects lazily, restarts on the next call if it died."""

    def __init__(self, server: McpServer) -> None:
        self.server = server
        self._proc: asyncio.subprocess.Process | None = None
        self._next_id = 0
        self._lock = asyncio.Lock()
        self.last_error = ""
        #: What the server answered to ``initialize``. Empty until a handshake succeeds.
        self.protocol_version = ""
        #: Identity the server reported in ``serverInfo``. Kept even when no pin is
        #: configured, so the running set of third-party implementations is observable.
        self.implementation_name = ""
        self.implementation_version = ""
        #: Digest of the last approved tool metadata set. Empty until ``list_tools``
        #: has run; exposed in ``McpManager.status()`` so an operator can copy the value
        #: into ``pinned_tools_digest`` and make a future silent change fail loudly.
        self.tools_digest = ""
        self._stderr_tail = b""
        self._stderr_task: asyncio.Task[None] | None = None

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

        # A new child means a new buffer. The tail describes *one* process, and reload()
        # reuses this client when only the command changed — so the object can start
        # twice, and without the reset the second failure quotes the first attempt's
        # stderr. The old reader is stopped first: it can otherwise append one more
        # chunk after the reset and reintroduce exactly the leak this prevents.
        await self._stop_stderr()
        self._stderr_tail = b""

        # An MCP server is third-party code, so it gets the same allowlist a plugin
        # gets: `SECURITY.md` grades MCP servers as untrusted, and handing them the
        # host environment contradicted that grade — an MCP server could read the
        # master key and every provider API key from `os.environ`. Only the variables
        # the operator declared for this server (`self.server.env`) are forwarded.
        env = sanitize_env(extra=self.server.env, prefix="")
        try:
            self._proc = await asyncio.create_subprocess_exec(
                executable,
                *command[1:],
                stdin=asyncio.subprocess.PIPE,
                stdout=asyncio.subprocess.PIPE,
                # Kept rather than silenced: when a start fails, the child's last words
                # are usually the entire diagnosis ("404 Not Found" for a package that
                # never downloaded). Nothing reads it unless something goes wrong.
                stderr=asyncio.subprocess.PIPE,
                env=env,
            )
        except OSError as exc:
            raise McpError(f"server {self.server.name} failed to start: {exc}") from exc
        self._stderr_task = asyncio.create_task(self._drain_stderr())

        # Handshake inline rather than through _request: _request would try to start
        # the server first, which is the call we are already inside.
        self._next_id += 1
        request_id = self._next_id
        try:
            await self._send(
                {
                    "jsonrpc": "2.0",
                    "id": request_id,
                    "method": "initialize",
                    "params": {
                        "protocolVersion": PROTOCOL_VERSION,
                        "capabilities": {},
                        "clientInfo": {"name": "soapbot", "version": __version__},
                    },
                }
            )
            result = await asyncio.wait_for(
                self._await_response(request_id), timeout=self.server.timeout
            )
            self._accept_protocol(result)
            await self._notify("notifications/initialized", {})
        except (McpError, TimeoutError, OSError, ValueError, TypeError) as exc:
            # Every failure here — a dead pipe, a timeout, a protocol disagreement or a
            # version pin mismatch — must leave no live child, no stderr reader and no
            # half-negotiated state. Previously only McpError from _await_response was
            # handled, and even that path merely settled stderr without terminating the
            # child; _accept_protocol and _notify sat outside the try entirely. Adding
            # a pin check that can reject would otherwise leak a subprocess on every
            # mismatch.
            failure = await self._abort_handshake(exc)
            raise failure from exc
        # Cleared on success, not only set on failure. Without this a server that went
        # down and came back keeps reporting the old error, so "reconnect" appears to
        # have done nothing and the operator restarts the whole process for nothing.
        self.last_error = ""
        logger.info("mcp server up name=%s pid=%s", self.server.name, self._proc.pid)

    async def _drain_stderr(self) -> None:
        """Keep the tail of what the child said, for error messages only.

        Bounded at 2 KB: a server that logs every request must not grow this for the
        life of the process, and the last screenful is what explains a failure anyway.
        """
        proc = self._proc
        if proc is None or proc.stderr is None:
            return
        try:
            while True:
                chunk = await proc.stderr.read(1024)
                if not chunk:
                    return
                self._stderr_tail = (self._stderr_tail + chunk)[-2048:]
        except asyncio.CancelledError:
            raise
        except Exception:  # the pipe closing under us is not worth reporting
            return

    async def _settle_stderr(self) -> None:
        """Give the stderr reader a moment to catch up before reporting a failure.

        The child writes its last line and exits; the pipe closes one scheduler tick
        later. Reading the tail without waiting would produce "it said nothing" for the
        exact failure where what it said is the whole answer.
        """
        task = self._stderr_task
        if task is None:
            return
        with contextlib.suppress(Exception):
            await asyncio.wait_for(asyncio.shield(task), timeout=1.0)

    def _handshake_failure(self, cause: McpError) -> McpError:
        """Say which half broke: the server never came up, or it refused us.

        On the wire both look like "the pipe closed", and they need opposite fixes — one
        is a package that never downloaded, the other a protocol we do not speak. The
        exit code and the child's stderr are the only things that tell them apart.
        """
        proc = self._proc
        code = None if proc is None else proc.returncode
        tail = self._stderr_tail.decode("utf-8", "replace").strip()
        said = f"; stderr: {tail[-400:]}" if tail else ""
        # EOF counts as death even when the watcher has not reaped the child yet: at
        # that instant `returncode` is still None, and the honest reading of "the pipe
        # closed" is that the process is gone, not that it argued with us.
        if code is not None or "closed the connection" in str(cause):
            where = f"exit code {code}" if code is not None else "the pipe closed"
            return McpError(
                f"server {self.server.name} exited during the handshake ({where}){said}"
            )
        return McpError(f"server {self.server.name} rejected the handshake: {cause}{said}")

    async def _abort_handshake(self, cause: BaseException) -> McpError:
        """Turn any failed handshake into one error and a clean, empty client.

        The child is already spawned and its stderr reader already running when this is
        reached. Leaving either behind is worse than the failure being diagnosed: the
        next call sees a live ``_proc`` with a closed pipe, and a server we just refused
        keeps a process alive for the lifetime of the host.

        Order matters. ``_handshake_failure`` reads ``_proc.returncode`` and the stderr
        tail, so it has to run *before* :meth:`close` nulls ``_proc`` and stops the
        reader. ``close`` then terminates the child, reaps the pipes and cancels the
        reader in one place instead of duplicating that logic here.
        """
        await self._settle_stderr()
        if isinstance(cause, McpError):
            failure = self._handshake_failure(cause)
        else:
            failure = McpError(
                f"server {self.server.name} failed the handshake: "
                f"{type(cause).__name__}: {cause}"
            )
        await self.close()
        self.protocol_version = ""
        self.implementation_name = ""
        self.implementation_version = ""
        self.last_error = str(failure)
        return failure

    def _accept_protocol(self, result: dict[str, Any]) -> None:
        """Negotiate the wire protocol and enforce the implementation pin.

        The spec has the server reply with a protocol version *it* supports; the client
        decides whether it can play along. It can — the three calls we make have not
        changed shape in any published version — so an unknown answer is accepted and
        logged rather than turned into a failed start.

        ``serverInfo.version`` is a different question. It identifies the third-party
        implementation that is about to execute, which is a supply-chain fact rather
        than a wire-compatibility guess. When the operator pinned a version, a mismatch
        raises :class:`McpError`; the caller's handshake try/except then cleans up the
        child. Without a pin the version is still recorded and audited, so the set of
        implementations that actually ran is knowable after the fact.
        """
        negotiated = str(result.get("protocolVersion") or "")
        self.protocol_version = negotiated or PROTOCOL_VERSION
        if negotiated and negotiated not in KNOWN_PROTOCOL_VERSIONS:
            logger.warning(
                "mcp server %s negotiated untested protocol %s (asked %s)",
                self.server.name,
                negotiated,
                PROTOCOL_VERSION,
            )
        elif negotiated and negotiated != PROTOCOL_VERSION:
            logger.info(
                "mcp server %s negotiated protocol %s (asked %s)",
                self.server.name,
                negotiated,
                PROTOCOL_VERSION,
            )

        info = result.get("serverInfo")
        if isinstance(info, dict):
            self.implementation_name = str(info.get("name") or "")
            self.implementation_version = str(info.get("version") or "")
        else:
            self.implementation_name = ""
            self.implementation_version = ""

        pinned = self.server.pinned_version.strip()
        issue = ""
        if pinned and not self.implementation_version:
            issue = "no serverInfo.version reported"
        elif pinned and self.implementation_version != pinned:
            issue = f"reports {self.implementation_version!r}, pinned {pinned!r}"

        # Recorded for both outcomes: a refused server is exactly the event a later
        # supply-chain review needs, and it cannot be reconstructed from status().
        get_audit_log().record(
            kind="mcp",
            action="implementation",
            outcome="deny" if issue else "allow",
            detail=(
                f"server={self.server.name} "
                f"name={self.implementation_name or '-'} "
                f"version={self.implementation_version or '-'} "
                f"pinned={pinned or '-'} protocol={self.protocol_version} "
                f"issue={issue or '-'}"
            ),
        )
        if issue:
            raise McpError(
                f"server {self.server.name} failed the implementation pin: {issue}"
            )

    async def _stop_stderr(self) -> None:
        """Stop the stderr reader. Safe to call when there is none."""
        task, self._stderr_task = self._stderr_task, None
        if task is None:
            return
        task.cancel()
        with contextlib.suppress(asyncio.CancelledError, Exception):
            await task

    async def close(self) -> None:
        proc, self._proc = self._proc, None
        await self._stop_stderr()
        if proc is None:
            return
        if proc.returncode is None:
            proc.terminate()
            with contextlib.suppress(asyncio.TimeoutError):
                await asyncio.wait_for(proc.wait(), timeout=3.0)
            if proc.returncode is None:  # pragma: no cover - stubborn child
                proc.kill()
                with contextlib.suppress(asyncio.TimeoutError):
                    await asyncio.wait_for(proc.wait(), timeout=3.0)
        # Reap the pipes as well. Leaving them open makes CPython print "Exception
        # ignored in BaseSubprocessTransport.__del__" once the transport is collected —
        # a traceback on a clean shutdown, which reads like a crash in a deployment log.
        with contextlib.suppress(Exception):
            await proc.communicate()

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
        raw_tools = result.get("tools") or []
        # Hash what the server actually sent, not the scrubbed copy. The pin is an
        # approval of the metadata we were shown; a description that changes into an
        # instruction-like payload may scrub to the same visible text.
        digest = _canonical_digest(raw_tools)
        expected = self.server.pinned_tools_digest
        if expected and digest != expected:
            get_audit_log().record(
                kind="injection",
                action="mcp_tool_metadata_drift",
                outcome="block",
                detail=(
                    f"server={self.server.name} expected={expected[:16]} "
                    f"actual={digest[:16]}"
                ),
            )
            raise McpError(
                f"server {self.server.name}: tool metadata changed since approval "
                f"(expected {expected[:16]}…, got {digest[:16]}…); re-approve the digest"
            )
        self.tools_digest = digest
        tools: list[McpTool] = []
        for raw in raw_tools:
            name = str(raw.get("name") or "")
            if not name:
                continue
            per_tool_digest = _canonical_digest(
                {
                    "name": raw.get("name"),
                    "description": raw.get("description"),
                    "inputSchema": raw.get("inputSchema"),
                }
            )

            # Tool metadata is written by the server, not by the host, and it lands in
            # the schema the model reads. Sanitised here — at the boundary, before the
            # text is ever stored — rather than in ``schemas()``: a value that is unsafe
            # is unsafe for every consumer, including the panel that renders it.
            description, description_suspicious = scrub_tool_text(
                str(raw.get("description") or "")
            )
            parameters, schema_hits = scrub_schema(
                raw.get("inputSchema") or {"type": "object", "properties": {}}
            )
            hits = (["description"] if description_suspicious else []) + list(schema_hits)
            suspicious = bool(hits)
            if suspicious:
                logger.warning(
                    "mcp server=%s tool=%s advertises instruction-like metadata (%s); "
                    "forwarding it as labelled data",
                    self.server.name,
                    name,
                    ",".join(hits)[:80],
                )
                get_audit_log().record(
                    kind="injection",
                    action="mcp_tool_metadata",
                    outcome="block",
                    detail=(
                        f"server={self.server.name} tool={name} "
                        f"fields={','.join(hits)[:80]}"
                    ),
                )

            tools.append(
                McpTool(
                    server=self.server.name,
                    name=name,
                    qualified_name=f"{NAME_PREFIX}__{self.server.name}__{name}",
                    description=description,
                    parameters=parameters if isinstance(parameters, dict) else {},
                    suspicious=suspicious,
                    metadata_digest=per_tool_digest,
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


def _spawn_signature(server: McpServer) -> tuple[Any, ...]:
    """The fields that decide what gets executed.

    ``description`` is deliberately absent: it is shown in the panel and nothing else,
    so editing it is not a reason to kill a working child process. ``pinned_version``
    is deliberately *present*: the pin is checked at handshake, so changing it on a
    live client without reconnecting would leave the old, unvalidated process running
    under a policy that was never applied to it.
    """
    return (
        server.command,
        tuple(sorted(server.env.items())),
        server.timeout,
        server.min_role,
        server.pinned_version,
        # The tool-metadata pin is checked when tools are listed, so changing it on a
        # live client without reconnecting would leave the previous tool set cached
        # under a policy that was never applied to it.
        server.pinned_tools_digest,
    )


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

    async def reload(self, servers: list[McpServer]) -> None:
        """Re-point at a new server list **without replacing this object**.

        The tool registry holds *this instance* as its source, so handing back a new
        manager would leave the registry talking to an object nobody updates. Unchanged
        servers keep their live client — closing and respawning every server on each
        save turns a one-line description edit into a reconnect storm — and only a
        change to the spawn signature gets a restart.
        """
        incoming = {s.name: s for s in servers}

        for name, client in list(self._clients.items()):
            fresh = incoming.get(name)
            if fresh is None:
                with contextlib.suppress(Exception):
                    await client.close()
                del self._clients[name]
                self._servers.pop(name, None)
                self._tools.pop(name, None)
                continue
            if _spawn_signature(fresh) != _spawn_signature(client.server):
                with contextlib.suppress(Exception):
                    await client.close()
                # In place: every later call reads `client.server` when it spawns, so
                # swapping the attribute is enough and keeps callers' references valid.
                client.server = fresh
            self._servers[name] = fresh

        for name, server in incoming.items():
            if name not in self._clients:
                self._clients[name] = McpClient(server)
                self._servers[name] = server

        # Enumerate after the swap, so the status the caller reports describes the new
        # list. Per-server failures stay contained (see ``ensure_tools``).
        await self.ensure_tools()

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
                    # Supply-chain view: the policy (pin), the identity the server
                    # claimed, and the wire protocol it negotiated. A version that was
                    # never checked shows up as an empty implementation_version.
                    "pinned_version": server.pinned_version,
                    # What was approved vs. what the server is currently advertising.
                    # Equal and non-empty means pinned; different means the list was
                    # refused and the operator must re-approve.
                    "pinned_tools_digest": server.pinned_tools_digest,
                    "tools_digest": self._clients[name].tools_digest,
                    "protocol_version": self._clients[name].protocol_version,
                    "implementation": self._clients[name].implementation_name,
                    "implementation_version": self._clients[name].implementation_version,
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

