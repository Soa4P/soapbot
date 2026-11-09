"""An MCP server's implementation version belongs to the supply chain.

The wire protocol is negotiated and an unknown answer is tolerated (see ``client.py``).
``serverInfo.version`` is different: it identifies the third-party code about to run.
An operator can pin it; a mismatch must be refused **and** leave no child process,
which is why the handshake cleanup and the pin check are tested together.
"""

from __future__ import annotations

import sys
from dataclasses import replace
from pathlib import Path

import pytest

from soapbot.mcp.client import McpClient, McpError, McpManager, McpServer, _spawn_signature
from soapbot.mcp.config import McpConfigError, parse_servers

#: The version comes from argv, not the environment: ``sanitize_env`` only forwards
#: variables the operator declared, and a test should not depend on that allowlist.
#: ``none`` makes the server omit ``serverInfo`` entirely.
_FAKE_SERVER = r'''
import json
import sys

version = sys.argv[1] if len(sys.argv) > 1 else "1"

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
        }
        if version != "none":
            result["serverInfo"] = {"name": "fake", "version": version}
    elif method == "tools/list":
        result = {"tools": []}
    else:
        result = {}
    if "id" in message:
        sys.stdout.write(
            json.dumps({"jsonrpc": "2.0", "id": message["id"], "result": result}) + "\n"
        )
        sys.stdout.flush()
'''


def _server(tmp_path: Path, *, version: str = "1", pinned: str = "") -> McpServer:
    script = tmp_path / "fake_server.py"
    script.write_text(_FAKE_SERVER, encoding="utf-8")
    return McpServer(
        name="fake",
        command=(sys.executable, str(script), version),
        timeout=10.0,
        pinned_version=pinned,
    )


def _entry(**overrides: object) -> dict[str, object]:
    entry: dict[str, object] = {"name": "x", "command": ["python"]}
    entry.update(overrides)
    return entry


def test_parse_servers_reads_and_trims_the_pin() -> None:
    servers = parse_servers([_entry(pinned_version=" 2.3.1 ")])
    assert servers[0].pinned_version == "2.3.1"


def test_an_absent_pin_means_record_only() -> None:
    assert parse_servers([_entry()])[0].pinned_version == ""


def test_an_oversized_pin_is_a_configuration_error() -> None:
    with pytest.raises(McpConfigError, match="too long"):
        parse_servers([_entry(pinned_version="v" * 129)])


def test_pin_validation_is_a_deterministic_rule() -> None:
    client = McpClient(McpServer(name="x", command=("python",), pinned_version="2"))
    with pytest.raises(McpError, match="reports '1'"):
        client._accept_protocol(
            {
                "protocolVersion": "2024-11-05",
                "serverInfo": {"name": "fake", "version": "1"},
            }
        )


async def test_a_matching_pin_is_accepted_and_the_identity_is_recorded(
    tmp_path: Path,
) -> None:
    client = McpClient(_server(tmp_path, version="1", pinned="1"))
    try:
        assert await client.list_tools() == []
        assert client.implementation_name == "fake"
        assert client.implementation_version == "1"
        assert client.protocol_version
        assert client.last_error == ""
    finally:
        await client.close()


async def test_a_mismatched_pin_is_refused_and_leaves_no_child(tmp_path: Path) -> None:
    """The reason this round also had to fix handshake cleanup.

    ``_accept_protocol`` used to sit outside the try: raising here would have left the
    spawned child and its stderr reader alive forever.
    """
    client = McpClient(_server(tmp_path, version="1", pinned="2"))
    with pytest.raises(McpError, match="implementation pin"):
        await client.list_tools()

    assert client._proc is None, "a refused server must not keep a live process"
    assert client._stderr_task is None, "the stderr reader must be stopped too"
    assert client.protocol_version == ""
    assert client.implementation_version == ""
    assert "pinned '2'" in client.last_error
    await client.close()  # idempotent after an aborted handshake


async def test_a_pinned_server_must_report_its_version(tmp_path: Path) -> None:
    client = McpClient(_server(tmp_path, version="none", pinned="1"))
    with pytest.raises(McpError, match=r"no serverInfo\.version"):
        await client.list_tools()
    assert client._proc is None
    assert client._stderr_task is None


async def test_an_unpinned_server_still_records_what_ran(tmp_path: Path) -> None:
    client = McpClient(_server(tmp_path, version="1", pinned=""))
    try:
        assert await client.list_tools() == []
        assert client.implementation_version == "1"
    finally:
        await client.close()


async def test_status_exposes_the_supply_chain_view(tmp_path: Path) -> None:
    manager = McpManager([_server(tmp_path, version="1", pinned="1")])
    try:
        await manager.ensure_tools()
        entry = manager.status()["servers"][0]
        assert entry["pinned_version"] == "1"
        assert entry["implementation"] == "fake"
        assert entry["implementation_version"] == "1"
        assert entry["protocol_version"]
        assert entry["error"] == ""
    finally:
        await manager.close()


def test_changing_the_pin_forces_a_reconnect() -> None:
    """A live client must re-handshake when the policy it was validated under changes."""
    base = McpServer(name="x", command=("python",))
    assert _spawn_signature(base) != _spawn_signature(
        replace(base, pinned_version="1")
    )
    assert _spawn_signature(base) == _spawn_signature(
        replace(base, description="only shown in the panel")
    )
