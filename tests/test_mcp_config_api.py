"""HTTP surface for editing ``config/mcp.yaml``.

Four things are worth testing at this level rather than at the patch engine:

* the read endpoint must not return an env **value**, in any field or at any depth;
* the diff endpoint must not write;
* apply must refuse a stale base and a diff that was never approved;
* apply must report per-server outcomes, because "written" and "works" are different
  claims and the second one is the one the operator asked about.

A stub manager stands in for the live one. Spawning real MCP servers here would make the
suite depend on a Node toolchain being installed, which is exactly the sort of implicit
requirement that turns a green build into a broken one on another machine.
"""

from __future__ import annotations

from pathlib import Path
from types import SimpleNamespace

import pytest
from fastapi.testclient import TestClient

TOKEN = "ghp_live_do_not_leak_9a3f"

MCP_YAML = (
    "servers:\n"
    "  - name: filesystem\n"
    "    description: read-only share\n"
    "    command: [npx, -y, server-filesystem, /srv/share]\n"
    "    env:\n"
    f"      GITHUB_TOKEN: {TOKEN}\n"
    "    timeout: 20\n"
    "    min_role: admin\n"
)


class _StubManager:
    """Records reloads; reports a fixed outcome per server."""

    def __init__(self) -> None:
        self.servers: list = []
        self.reloads = 0

    async def reload(self, servers: list) -> None:
        self.servers = servers
        self.reloads += 1

    def status(self) -> dict:
        return {
            "servers": [
                {"name": s.name, "min_role": s.min_role, "tools": 2, "error": ""}
                for s in self.servers
            ],
            "tools": 2 * len(self.servers),
        }


@pytest.fixture
def setup(tmp_path, monkeypatch):
    from soapbot.app import create_app
    from soapbot.config import settings

    config_dir = tmp_path / "cfg"
    config_dir.mkdir(parents=True, exist_ok=True)
    (config_dir / "providers.yaml").write_text("providers: []\n", encoding="utf-8")
    (config_dir / "adapters.yaml").write_text("adapters: []\n", encoding="utf-8")
    (config_dir / "mcp.yaml").write_text(MCP_YAML, encoding="utf-8")

    monkeypatch.setattr(settings, "config_dir", config_dir)

    manager = _StubManager()

    import soapbot.app as app_module

    monkeypatch.setattr(app_module, "_RUNTIME", SimpleNamespace(mcp=manager))
    return TestClient(create_app()), manager, config_dir


def _mcp_path(config_dir: Path) -> Path:
    return config_dir / "mcp.yaml"


# -------------------------------------------------------------------- reading


def test_read_never_returns_an_env_value(setup) -> None:
    client, _, _ = setup
    body = client.get("/api/config/mcp").json()

    assert TOKEN not in str(body)
    assert body["servers"][0]["env_keys"] == ["GITHUB_TOKEN"]
    assert body["base_hash"]


def test_read_returns_the_roles_and_the_path(setup) -> None:
    client, _, config_dir = setup
    body = client.get("/api/config/mcp").json()

    assert body["roles"] == ["admin", "anonymous", "member", "owner"]
    assert body["path"] == str(_mcp_path(config_dir))


def test_read_merges_live_status(setup) -> None:
    """One fetch gives the table both the file and what is actually running, so the
    panel cannot render a stale file next to a fresh status."""
    client, manager, _ = setup

    async def _seed() -> None:
        from soapbot.mcp.config import parse_servers

        await manager.reload(parse_servers([{"name": "filesystem", "command": ["npx"]}]))

    import asyncio

    asyncio.run(_seed())
    body = client.get("/api/config/mcp").json()
    assert body["status"]["filesystem"]["tools"] == 2


# ----------------------------------------------------------------------- diff


def test_diff_does_not_write(setup) -> None:
    client, _, config_dir = setup
    before = _mcp_path(config_dir).read_text(encoding="utf-8")
    body = client.get("/api/config/mcp").json()

    response = client.post(
        "/api/config/mcp/diff",
        json={"base_hash": body["base_hash"], "servers": [{"name": "filesystem", "timeout": 9}]},
    )

    assert response.status_code == 200
    assert "timeout" in response.json()["diff"]
    assert _mcp_path(config_dir).read_text(encoding="utf-8") == before


def test_diff_never_shows_the_token(setup) -> None:
    client, _, _ = setup
    body = client.get("/api/config/mcp").json()

    response = client.post(
        "/api/config/mcp/diff",
        json={
            "base_hash": body["base_hash"],
            "servers": [{"name": "filesystem", "env": {"GITHUB_TOKEN": "rotated"}}],
        },
    )

    assert TOKEN not in response.text
    assert "rotated" not in response.text


def test_a_command_string_is_rejected_before_the_engine_sees_it(setup) -> None:
    client, _, config_dir = setup
    body = client.get("/api/config/mcp").json()

    response = client.post(
        "/api/config/mcp/diff",
        json={
            "base_hash": body["base_hash"],
            "servers": [{"name": "shell", "command": "npx -y thing"}],
        },
    )

    # Refused by the request model: `command` is a list, so a string cannot even reach
    # the merge rules. Belt and braces — the engine rejects it too.
    assert response.status_code == 422
    assert _mcp_path(config_dir).read_text(encoding="utf-8") == MCP_YAML


# ---------------------------------------------------------------------- apply


def test_apply_writes_and_hot_reloads(setup) -> None:
    client, manager, config_dir = setup
    body = client.get("/api/config/mcp").json()
    payload = {"base_hash": body["base_hash"], "servers": [{"name": "filesystem", "timeout": 9}]}

    approved = client.post("/api/config/mcp/diff", json=payload).json()["new_hash"]
    response = client.post("/api/config/mcp/apply", json={**payload, "approved_hash": approved})

    assert response.status_code == 200
    data = response.json()
    assert data["written"] is True
    assert data["restart_required"] is False
    assert data["servers"]["filesystem"] == {"tools": 2, "error": ""}
    assert manager.reloads == 1
    assert manager.servers[0].timeout == 9
    assert "timeout: 9.0" in _mcp_path(config_dir).read_text(encoding="utf-8")


def test_apply_refuses_a_stale_base_hash(setup) -> None:
    client, manager, config_dir = setup
    body = client.get("/api/config/mcp").json()
    _mcp_path(config_dir).write_text(
        MCP_YAML + "  - name: other\n    command: [npx, x]\n", encoding="utf-8"
    )

    response = client.post(
        "/api/config/mcp/apply",
        json={"base_hash": body["base_hash"], "servers": [{"name": "filesystem", "timeout": 9}]},
    )

    assert response.status_code == 409
    assert manager.reloads == 0


def test_apply_refuses_a_diff_that_was_never_approved(setup) -> None:
    client, manager, _ = setup
    body = client.get("/api/config/mcp").json()

    response = client.post(
        "/api/config/mcp/apply",
        json={
            "base_hash": body["base_hash"],
            "servers": [{"name": "filesystem", "timeout": 9}],
            "approved_hash": "deadbeefdeadbeef",
        },
    )

    assert response.status_code == 409
    assert response.json()["detail"]["expected_hash"]
    assert manager.reloads == 0


def test_a_noop_apply_does_not_touch_the_file(setup) -> None:
    client, manager, config_dir = setup
    body = client.get("/api/config/mcp").json()

    response = client.post(
        "/api/config/mcp/apply",
        json={"base_hash": body["base_hash"], "servers": [{"name": "filesystem", "timeout": 20}]},
    )

    assert response.status_code == 200
    assert response.json()["written"] is False
    # No mtime/hash churn: another admin's open editor must not be invalidated by a
    # button press that changed nothing.
    assert _mcp_path(config_dir).read_text(encoding="utf-8") == MCP_YAML
    assert manager.reloads == 0


# ----------------------------------------------------------------- permission


def _caller(role: str) -> dict:
    return {"mode": "token", "subject": "someone", "role": role}


def test_admin_role_cannot_manage_mcp() -> None:
    """One rank above MANAGE_CONFIG: an entry is an argv the host will execute."""
    from fastapi import HTTPException

    from soapbot.api.config_write import _require_permission
    from soapbot.security.principal import Permission

    request = SimpleNamespace(client=SimpleNamespace(host="203.0.113.9"))
    with pytest.raises(HTTPException) as excinfo:
        _require_permission(_caller("admin"), request, Permission.MANAGE_MCP)
    assert excinfo.value.status_code == 403


def test_owner_role_passes_the_mcp_gate() -> None:
    from soapbot.api.config_write import _require_permission
    from soapbot.security.principal import Permission

    request = SimpleNamespace(client=SimpleNamespace(host="127.0.0.1"))
    _require_permission(_caller("owner"), request, Permission.MANAGE_MCP)


# ---------------------------------------------------------------------- audit


def test_apply_is_audited_without_the_env_value(setup) -> None:
    """The audit log is exported and read by people who may not see the credential.

    So the assertion is two-sided: the change is attributable (server + field names),
    and the value that was typed is nowhere in the log.
    """
    from soapbot.security.audit import get_audit_log

    client, _, _ = setup
    get_audit_log().clear()
    body = client.get("/api/config/mcp").json()
    payload = {
        "base_hash": body["base_hash"],
        "servers": [{"name": "filesystem", "env": {"GITHUB_TOKEN": "rotated-secret-value"}}],
    }

    approved = client.post("/api/config/mcp/diff", json=payload).json()["new_hash"]
    assert client.post("/api/config/mcp/apply", json={**payload, "approved_hash": approved}).status_code == 200

    events = [e.to_dict() for e in get_audit_log()._events if e.action == "mcp_servers_updated"]
    assert len(events) == 1
    detail = str(events[0])
    assert "servers[filesystem].env" in detail
    assert "rotated-secret-value" not in detail
    assert TOKEN not in detail


def test_a_refused_apply_is_audited_as_a_denial(setup) -> None:
    from soapbot.security.audit import get_audit_log

    client, _, _ = setup
    get_audit_log().clear()
    body = client.get("/api/config/mcp").json()

    client.post(
        "/api/config/mcp/apply",
        json={
            "base_hash": body["base_hash"],
            "servers": [{"name": "filesystem", "timeout": 9}],
            "approved_hash": "deadbeefdeadbeef",
        },
    )

    events = [e.to_dict() for e in get_audit_log()._events if e.action == "mcp_unapproved_diff"]
    assert len(events) == 1
    assert events[0]["outcome"] == "deny"
