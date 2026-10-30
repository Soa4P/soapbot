"""MCP: external tools must join the *same* filtered table as plugin tools.

The security-relevant assertion is not "the client speaks the protocol" but "a caller
who may not use an MCP tool does not see it at all". A second tool path would be a
second place to remember the role check, and the forgotten one is what gets used.

The server is a real child process speaking newline-delimited JSON-RPC, so the tests
exercise the transport rather than a mock of it.
"""

from __future__ import annotations

import sys
from pathlib import Path
from types import SimpleNamespace

import pytest

from soapbot.mcp.client import McpClient, McpManager, McpServer
from soapbot.mcp.config import McpConfigError, load_config
from soapbot.plugins.dispatch import PluginToolRegistry
from soapbot.plugins.loader import PluginLoader
from soapbot.security.principal import Role

SERVER = r'''
import json
import sys

TOOLS = [
    {
        "name": "echo",
        "description": "echo the arguments back",
        "inputSchema": {"type": "object", "properties": {"text": {"type": "string"}}},
    }
]

for line in sys.stdin:
    line = line.strip()
    if not line:
        continue
    try:
        message = json.loads(line)
    except json.JSONDecodeError:
        continue
    method = message.get("method")
    if method == "initialize":
        result = {
            "protocolVersion": "2024-11-05",
            "capabilities": {"tools": {}},
            "serverInfo": {"name": "fake", "version": "1"},
        }
    elif method == "tools/list":
        result = {"tools": TOOLS}
    elif method == "tools/call":
        result = {
            "content": [
                {"type": "text", "text": "got:" + json.dumps(message["params"]["arguments"])}
            ]
        }
    else:
        result = {}
    if "id" in message:
        sys.stdout.write(json.dumps({"jsonrpc": "2.0", "id": message["id"], "result": result}) + "\n")
        sys.stdout.flush()
'''


#: Dies during the handshake, the way a package that failed to download does: reads the
#: one request, puts a line on stderr, exits.
CRASHER = r'''
import sys

sys.stdin.readline()
sys.stderr.write("npm error 404 Not Found - GET https://registry.npmjs.org/nope\n")
sys.stderr.flush()
sys.exit(9)
'''


def _crasher(tmp_path: Path, marker: str) -> Path:
    """A child that reads one request, says ``marker`` on stderr, and exits."""
    path = tmp_path / f"crash_{marker}.py"
    path.write_text(
        "import sys\n"
        "sys.stdin.readline()\n"
        f"sys.stderr.write({marker!r})\n"
        "sys.stderr.flush()\n"
        "sys.exit(9)\n",
        encoding="utf-8",
    )
    return path


def _script(tmp_path: Path) -> Path:
    path = tmp_path / "fake_server.py"
    path.write_text(SERVER, encoding="utf-8")
    return path


def _server(tmp_path: Path, *, min_role: str = "member") -> McpServer:
    return McpServer(
        name="fake",
        command=(sys.executable, str(_script(tmp_path))),
        timeout=15.0,
        min_role=min_role,
    )


def _principal(role: Role) -> SimpleNamespace:
    return SimpleNamespace(role=role)


def _rank(value: str) -> int:
    try:
        return Role(value).rank
    except ValueError:
        return Role.ANONYMOUS.rank


# ------------------------------------------------------------------------ client


async def test_client_handshakes_lists_and_calls(tmp_path: Path) -> None:
    client = McpClient(_server(tmp_path))
    try:
        tools = await client.list_tools()
        # The fake answers with an older version than we ask for, on purpose: taking the
        # server's answer is the negotiation, and pinning our own would have made this
        # line read "2025-06-18" while the server actually runs on something else.
        assert client.protocol_version == "2024-11-05"
        assert [t.name for t in tools] == ["echo"]
        # Namespaced so one server cannot shadow another's tool.
        assert tools[0].qualified_name == "mcp__fake__echo"

        text = await client.call_tool("echo", {"text": "hi"})
        assert text == 'got:{"text": "hi"}'
    finally:
        await client.close()


async def test_a_restart_does_not_inherit_the_previous_stderr(tmp_path: Path) -> None:
    """One client, two children: the second failure must not quote the first one.

    ``reload()`` reuses a client when only the command changed, so the same object can
    spawn twice. The stderr tail is a record of one process; if it survives the restart,
    the operator fixing a command reads a mix of both attempts and cannot tell which
    line came from the run they just caused.
    """
    client = McpClient(
        McpServer(name="crasher", command=(sys.executable, str(_crasher(tmp_path, "FIRST"))))
    )
    with pytest.raises(Exception, match="FIRST"):
        await client.list_tools()

    client.server = McpServer(
        name="crasher", command=(sys.executable, str(_crasher(tmp_path, "SECOND")))
    )
    with pytest.raises(Exception) as caught:
        await client.list_tools()

    message = str(caught.value)
    assert "SECOND" in message
    assert "FIRST" not in message
    await client.close()


async def test_missing_executable_is_a_clear_error(tmp_path: Path) -> None:
    client = McpClient(McpServer(name="x", command=("definitely-not-a-binary",), timeout=5))
    with pytest.raises(Exception, match="not found on PATH"):
        await client.list_tools()


async def test_a_server_that_dies_in_the_handshake_says_so(tmp_path: Path) -> None:
    """The two ways a real server fails must not read the same.

    A package that never downloaded and a protocol we do not speak both surface as "the
    pipe closed", and they need opposite fixes. So the message has to name which one
    happened, and carry whatever the child managed to say — with ``stderr`` discarded
    this used to be the only unfixable-looking error in the codebase.
    """
    script = tmp_path / "crasher.py"
    script.write_text(CRASHER, encoding="utf-8")
    client = McpClient(
        McpServer(name="crasher", command=(sys.executable, str(script)), timeout=10)
    )
    with pytest.raises(Exception, match="exited during the handshake") as caught:
        await client.list_tools()
    message = str(caught.value)
    assert "404 Not Found" in message
    await client.close()


# ------------------------------------------------------------- role filtering


async def test_tools_are_hidden_below_min_role(tmp_path: Path) -> None:
    manager = McpManager([_server(tmp_path, min_role="admin")], role_rank=_rank)
    try:
        await manager.ensure_tools()
        assert manager.schemas(_principal(Role.ADMIN))
        assert manager.schemas(_principal(Role.MEMBER)) == []
        assert manager.schemas(None) == []
        with pytest.raises(Exception, match="not permitted"):
            await manager.call("mcp__fake__echo", {}, principal=_principal(Role.MEMBER))
    finally:
        await manager.close()


# ---------------------------------------------------------------- tool registry


async def test_registry_lists_mcp_tools_for_allowed_callers(tmp_path: Path) -> None:
    manager = McpManager([_server(tmp_path)], role_rank=_rank)
    registry = PluginToolRegistry(PluginLoader(plugins_dir=tmp_path / "plugins"))
    registry.register_source(manager)
    try:
        await manager.ensure_tools()
        names = [t["name"] for t in registry.available_for(_principal(Role.MEMBER))]
        assert names == ["mcp__fake__echo"]
    finally:
        await manager.close()


async def test_the_first_server_added_shows_up_without_a_restart(tmp_path: Path) -> None:
    """Empty -> one is the path every new install takes, and it used to need a restart.

    The manager was created only when ``mcp.yaml`` already named a server, so the panel
    had no object to reload into and could only answer "written, takes effect after
    restart" — for the one edit the editor exists to make unnecessary.
    """
    manager = McpManager([], role_rank=_rank)
    registry = PluginToolRegistry(PluginLoader(plugins_dir=tmp_path / "plugins"))
    registry.register_source(manager)
    try:
        assert registry.available_for(_principal(Role.MEMBER)) == []

        await manager.reload([_server(tmp_path)])

        names = [tool["name"] for tool in registry.available_for(_principal(Role.MEMBER))]
        assert names == ["mcp__fake__echo"]
    finally:
        await manager.close()


async def test_registry_routes_an_mcp_call(tmp_path: Path) -> None:
    manager = McpManager([_server(tmp_path)], role_rank=_rank)
    registry = PluginToolRegistry(PluginLoader(plugins_dir=tmp_path / "plugins"))
    registry.register_source(manager)
    try:
        await manager.ensure_tools()
        result = await registry.invoke(
            "mcp__fake__echo", {"text": "hey"}, principal=_principal(Role.MEMBER)
        )
        assert result == 'got:{"text": "hey"}'
    finally:
        await manager.close()


async def test_registry_hides_mcp_tools_below_min_role(tmp_path: Path) -> None:
    manager = McpManager([_server(tmp_path, min_role="owner")], role_rank=_rank)
    registry = PluginToolRegistry(PluginLoader(plugins_dir=tmp_path / "plugins"))
    registry.register_source(manager)
    try:
        await manager.ensure_tools()
        assert registry.available_for(_principal(Role.ADMIN)) == []
        # And calling by name anyway is refused, not merely unlisted.
        result = await registry.invoke(
            "mcp__fake__echo", {}, principal=_principal(Role.ADMIN)
        )
        assert result.startswith("错误")
    finally:
        await manager.close()


# ---------------------------------------------------------------------- config


def test_config_rejects_a_string_command(tmp_path: Path) -> None:
    """A string command would have to be split, and splitting is where shells appear."""
    path = tmp_path / "mcp.yaml"
    path.write_text("servers:\n  - name: x\n    command: 'npx server'\n", encoding="utf-8")
    with pytest.raises(McpConfigError, match="list of arguments"):
        load_config(path)


def test_config_rejects_duplicate_names(tmp_path: Path) -> None:
    path = tmp_path / "mcp.yaml"
    path.write_text(
        "servers:\n"
        "  - name: x\n    command: ['a']\n"
        "  - name: x\n    command: ['b']\n",
        encoding="utf-8",
    )
    with pytest.raises(McpConfigError, match="duplicate"):
        load_config(path)


def test_config_rejects_unknown_role(tmp_path: Path) -> None:
    path = tmp_path / "mcp.yaml"
    path.write_text(
        "servers:\n  - name: x\n    command: ['a']\n    min_role: superuser\n",
        encoding="utf-8",
    )
    with pytest.raises(McpConfigError, match="min_role"):
        load_config(path)


def test_missing_config_means_no_mcp(tmp_path: Path) -> None:
    assert load_config(tmp_path / "absent.yaml") == []


# ------------------------------------------------------------------- recovery

def _flaky_server(tmp_path: Path, marker: Path) -> McpServer:
    """A server that fails until ``marker`` exists, then behaves.

    Stands in for "the MCP server was down when the bot booted": the state the refresh
    endpoint exists to fix.
    """
    script = tmp_path / "flaky_server.py"
    script.write_text(
        "import json, sys, pathlib\n"
        f"MARKER = pathlib.Path({str(marker)!r})\n"
        "if not MARKER.exists():\n"
        "    sys.stderr.write('not ready\\n')\n"
        "    sys.exit(3)\n" + SERVER,
        encoding="utf-8",
    )
    return McpServer(
        name="fake",
        command=(sys.executable, str(script)),
        timeout=15.0,
        min_role="member",
    )


async def test_refresh_recovers_a_server_that_was_down_at_boot(tmp_path: Path) -> None:
    """The manager claims a dead server is "retried on the next refresh".

    Nothing could trigger a refresh before: ``ensure_tools`` ran once inside
    ``runtime.start()``, so a server that was down at boot stayed tool-less until the
    process restarted. This asserts the documented recovery path now exists.
    """
    marker = tmp_path / "ready"
    manager = McpManager([_flaky_server(tmp_path, marker)], role_rank=_rank)
    try:
        await manager.ensure_tools()
        assert manager.status()["tools"] == 0
        assert manager.status()["servers"][0]["error"], "a dead server must report why"

        marker.touch()
        await manager.ensure_tools()          # <- the refresh the endpoint calls

        assert manager.status()["tools"] == 1
        assert manager.schemas(_principal(Role.MEMBER)), "the tool must be visible again"
    finally:
        await manager.close()


async def test_a_successful_call_clears_the_stale_error(tmp_path: Path) -> None:
    """Otherwise "reconnect" looks like it did nothing.

    ``last_error`` was only ever assigned on failure, so a server that recovered kept
    reporting the old message and the operator would restart the process for nothing.
    """
    marker = tmp_path / "ready"
    server = _flaky_server(tmp_path, marker)
    manager = McpManager([server], role_rank=_rank)
    try:
        await manager.ensure_tools()
        client = manager._clients["fake"]
        assert client.last_error

        marker.touch()
        await manager.ensure_tools()

        assert client.last_error == ""
    finally:
        await manager.close()


async def test_a_later_success_clears_a_recorded_timeout(tmp_path: Path) -> None:
    """A timeout is sticky otherwise: the next working call leaves the error in place.

    Distinct from the restart case — here the process never died, so ``_ensure_started``
    returns early and only the request path can clear the message.
    """
    client = McpClient(_server(tmp_path))
    try:
        await client.list_tools()
        client.last_error = "timeout after 15s"      # simulate an earlier failure
        await client.list_tools()                    # same process, still healthy
        assert client.last_error == ""
    finally:
        await client.close()
