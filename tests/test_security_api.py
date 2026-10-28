"""Security API surface: audit visibility and permission matrix."""

from __future__ import annotations

import pytest
from fastapi.testclient import TestClient

from soapbot.app import create_app
from soapbot.security.audit import get_audit_log
from soapbot.security.principal import Principal, Role


@pytest.fixture
def client() -> TestClient:
    get_audit_log().clear()
    return TestClient(create_app())


def test_permission_matrix_lists_every_permission(client: TestClient) -> None:
    data = client.get("/api/security/permissions").json()
    names = {p["name"] for p in data["permissions"]}
    assert "approve_payment" in names
    assert "manage_memory_any" in names
    # Payment must sit at the top of the ladder, or the approval gate is meaningless.
    payment = next(p for p in data["permissions"] if p["name"] == "approve_payment")
    assert payment["min_role"] == "owner"


def test_audit_endpoint_reports_denials(client: TestClient) -> None:
    audit = get_audit_log()
    principal = Principal(user_id="20001", role=Role.MEMBER, authenticated=True)
    audit.record(kind="authz", action="cmd:kb", outcome="deny", principal=principal)

    data = client.get("/api/security/audit").json()
    assert data["total_denials"] >= 1
    assert any(e["action"] == "cmd:kb" for e in data["events"])

    denials = client.get("/api/security/denials").json()
    assert denials["count"] >= 1
    assert all(e["outcome"] == "deny" for e in denials["events"])


def test_audit_never_returns_raw_secrets(client: TestClient) -> None:
    get_audit_log().record(
        kind="authz", action="t", outcome="deny", api_key="sk-supersecret1234567"
    )
    body = client.get("/api/security/audit").text
    assert "sk-supersecret1234567" not in body


def test_whoami_resolves_an_unlisted_user_to_member(client: TestClient) -> None:
    data = client.get("/api/security/whoami", params={"user_id": "20001"}).json()
    assert data["role"] == "member"
    assert "chat" in data["permissions"]
    # The dangerous ones must not be present for an unlisted user.
    assert "read_knowledge" not in data["permissions"]
    assert "approve_payment" not in data["permissions"]
