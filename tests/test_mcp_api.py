"""The MCP refresh endpoint, exercised through HTTP with a real child process.

The manager-level tests in ``test_mcp_wiring.py`` prove the refresh *works*; this one
proves the operator can *reach* it. Both matter here, because the defect being fixed
was precisely a capability with no caller: the code to recover a dead server existed
in ``ensure_tools``'s docstring and nowhere in the request path.

The server is a real subprocess speaking newline-delimited JSON-RPC, started through
``config/mcp.yaml`` exactly as a deployment would.
"""

from __future__ import annotations

import shutil
import sys
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from soapbot.config import settings

SERVER = r"""
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
        result = {"protocolVersion": "2024-11-05", "capabilities": {"tools": {}}}
    elif method == "tools/list":
        result = {"tools": TOOLS}
    elif method == "tools/call":
        result = {"content": [{"type": "text", "text": "ok"}]}
    else:
        result = {}
    if "id" in message:
        sys.stdout.write(json.dumps({"jsonrpc": "2.0", "id": message["id"], "result": result}) + "\n")
        sys.stdout.flush()
"""


def _config_with_mcp(tmp_path: Path, *, command: list[str]) -> Path:
    import yaml

    config_dir = tmp_path / "cfg"
    config_dir.mkdir(parents=True, exist_ok=True)
    (config_dir / "providers.yaml").write_text("providers: []\n", encoding="utf-8")
    (config_dir / "adapters.yaml").write_text("adapters: []\n", encoding="utf-8")
    source = Path(__file__).resolve().parents[1] / "config" / "personas"
    if source.is_dir():
        shutil.copytree(source, config_dir / "personas")
    (config_dir / "mcp.yaml").write_text(
        yaml.safe_dump(
            {"servers": [{"name": "fake", "command": command, "min_role": "member"}]},
            allow_unicode=True,
        ),
        encoding="utf-8",
    )
    return config_dir


@pytest.fixture
def client_with_mcp(tmp_path, monkeypatch):
    script = tmp_path / "server.py"
    script.write_text(SERVER, encoding="utf-8")
    config_dir = _config_with_mcp(tmp_path, command=[sys.executable, str(script)])

    monkeypatch.setattr(settings, "enable_runtime", True)
    monkeypatch.setattr(settings, "config_dir", config_dir)

    from soapbot.app import create_app

    with TestClient(create_app()) as client:
        yield client


def test_status_lists_the_configured_server(client_with_mcp: TestClient) -> None:
    body = client_with_mcp.get("/api/mcp").json()
    assert body["configured"] is True
    assert [s["name"] for s in body["servers"]] == ["fake"]
    # Tools were discovered at startup, so the count is non-zero here. A zero would
    # mean the wiring changed and the panel would silently show nothing.
    assert body["tools"] >= 1


def test_refresh_returns_the_same_shape_as_status(client_with_mcp: TestClient) -> None:
    before = client_with_mcp.get("/api/mcp").json()
    after = client_with_mcp.post("/api/mcp/refresh")
    assert after.status_code == 200
    body = after.json()
    assert body["ok"] is True
    assert body["tools"] == before["tools"]
    assert {s["name"] for s in body["servers"]} == {s["name"] for s in before["servers"]}
    # The panel renders ``error`` per row; the key must exist even when empty, or the
    # table shows "undefined" instead of the healthy state.
    assert all("error" in s for s in body["servers"])


def test_refresh_refuses_a_member_with_403(client_with_mcp: TestClient) -> None:
    """Refreshing starts subprocesses and reshapes the tool table, so it is a config
    write. A member must be refused *by the endpoint*, not merely by the UI hiding the
    button — the button is a hint, the 403 is the control.
    """
    from soapbot.api.auth import require_api_auth

    client_with_mcp.app.dependency_overrides[require_api_auth] = lambda: {"role": "member"}
    try:
        response = client_with_mcp.post("/api/mcp/refresh")
    finally:
        client_with_mcp.app.dependency_overrides.pop(require_api_auth, None)

    assert response.status_code == 403, response.text
    # The refusal names the role required, so an operator knows what to grant.
    assert "admin" in response.json()["detail"].lower()


def test_refresh_allows_an_admin(client_with_mcp: TestClient) -> None:
    """The paired positive case: 403 above must not be 403 for everyone."""
    from soapbot.api.auth import require_api_auth

    client_with_mcp.app.dependency_overrides[require_api_auth] = lambda: {"role": "admin"}
    try:
        response = client_with_mcp.post("/api/mcp/refresh")
    finally:
        client_with_mcp.app.dependency_overrides.pop(require_api_auth, None)

    assert response.status_code == 200, response.text


def test_an_unknown_role_is_not_treated_as_privileged() -> None:
    """A token carrying a role this build does not know must not pass the rank check.

    ``Role("nonsense")`` raises; swallowing that as "probably fine" would be a
    privilege escalation for any typo in an operator's config.
    """
    from soapbot.api.admin import _role_of
    from soapbot.security.principal import Role

    assert _role_of({"role": "nonsense"}) is Role.ANONYMOUS
    assert _role_of({}) is Role.ANONYMOUS
