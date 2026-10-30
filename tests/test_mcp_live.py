"""The real thing: a third-party MCP server, configured the way the panel writes it.

Why opt-in
----------
This test downloads a package from the public npm registry. CI must not depend on that:
a suite that goes red when npm has a bad afternoon gets marked flaky, and a flaky gate
is worse than a narrow one. The fake server in ``test_mcp_wiring`` covers the protocol;
this file covers the part a fake cannot — somebody else's SDK, a version we did not
choose, and an argv that came out of a user-editable YAML file.

    SOAPBOT_LIVE_MCP=1 python -m pytest tests/test_mcp_live.py -q

What it rules out: the client only ever shakes hands with a script written to agree
with it.
"""

from __future__ import annotations

import os
import shutil
from pathlib import Path

import pytest

from soapbot.mcp.client import McpClient, McpServer

LIVE = os.environ.get("SOAPBOT_LIVE_MCP") == "1"
NPX = shutil.which("npx")

pytestmark = [
    pytest.mark.skipif(
        not LIVE, reason="set SOAPBOT_LIVE_MCP=1 to download and start a real server"
    ),
    pytest.mark.skipif(NPX is None, reason="npx is not on PATH"),
]

#: Generous on purpose. The first run downloads the package, and a tight timeout here
#: would report "handshake failed" for what is really "still downloading" — the exact
#: confusion the client's error messages were fixed to avoid.
TIMEOUT = 240.0


def _server(share: Path) -> McpServer:
    return McpServer(
        name="filesystem",
        command=(NPX or "npx", "-y", "@modelcontextprotocol/server-filesystem", str(share)),
        timeout=TIMEOUT,
        min_role="member",
    )


async def test_a_real_server_lists_tools_and_reads_a_file(tmp_path: Path) -> None:
    share = tmp_path / "share"
    share.mkdir()
    (share / "hello.txt").write_text("the real thing", encoding="utf-8")

    client = McpClient(_server(share))
    try:
        tools = await client.list_tools()
        names = [tool.name for tool in tools]
        assert "read_text_file" in names
        # Namespaced per server, so two servers cannot shadow each other's tools.
        assert all(tool.qualified_name.startswith("mcp__filesystem__") for tool in tools)
        # Whatever version the server speaks, we took its answer rather than assuming
        # ours was accepted.
        assert client.protocol_version

        text = await client.call_tool("read_text_file", {"path": str(share / "hello.txt")})
        assert "the real thing" in text
    finally:
        await client.close()
