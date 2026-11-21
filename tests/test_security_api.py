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
    # 进入 lifespan：token_service 只在 _init_auth 里挂上 app.state（S-AIM-01 的
    # owner-bearer 需要它）。
    with TestClient(create_app()) as c:
        yield c


def test_permission_matrix_lists_every_permission(client: TestClient) -> None:
    data = client.get("/api/security/permissions").json()
    names = {p["name"] for p in data["permissions"]}
    assert "approve_payment" in names
    assert "manage_memory_any" in names
    # Payment must sit at the top of the ladder, or the approval gate is meaningless.
    payment = next(p for p in data["permissions"] if p["name"] == "approve_payment")
    assert payment["min_role"] == "owner"


def _owner_headers(client: TestClient) -> dict:
    """Mint an owner bearer from the app's own token service (S-AIM-01: the
    audit/denials reads now require ADMIN + credential). The auth objects live
    on the nested AuthState under _STATE_KEY, not on app.state directly."""
    auth_state = client.app.state.soapbot_auth_state
    token, _ = auth_state.token_service.issue(role="owner")
    return {"Authorization": f"Bearer {token}"}


def test_audit_endpoint_reports_denials(client: TestClient) -> None:
    audit = get_audit_log()
    principal = Principal(user_id="20001", role=Role.MEMBER, authenticated=True)
    audit.record(kind="authz", action="cmd:kb", outcome="deny", principal=principal)

    # MEMBER / credentialless loopback is refused now (S-AIM-01)…
    assert client.get("/api/security/audit").status_code in (401, 403)
    assert client.get("/api/security/denials").status_code in (401, 403)
    # …while the operator (owner credential) still sees everything.
    data = client.get("/api/security/audit", headers=_owner_headers(client)).json()
    assert data["total_denials"] >= 1
    assert any(e["action"] == "cmd:kb" for e in data["events"])

    denials = client.get("/api/security/denials", headers=_owner_headers(client)).json()
    assert denials["count"] >= 1
    assert all(e["outcome"] == "deny" for e in denials["events"])


def test_audit_never_returns_raw_secrets(client: TestClient) -> None:
    get_audit_log().record(
        kind="authz", action="t", outcome="deny", api_key="sk-supersecret1234567"
    )
    body = client.get("/api/security/audit", headers=_owner_headers(client)).text
    assert "sk-supersecret1234567" not in body


def test_whoami_resolves_an_unlisted_user_to_member(client: TestClient) -> None:
    data = client.get("/api/security/whoami", params={"user_id": "20001"}).json()
    assert data["role"] == "member"
    assert "chat" in data["permissions"]
    # The dangerous ones must not be present for an unlisted user.
    assert "read_knowledge" not in data["permissions"]
    assert "approve_payment" not in data["permissions"]
