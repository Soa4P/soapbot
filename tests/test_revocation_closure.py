"""Revoking everything must leave no live session behind.

What was wrong
--------------
``/api/auth/revoke-all`` used to revoke every token and then, in the same response,
issue the caller a fresh full-privilege token plus a cookie. "Revoked" was a log line
rather than a state: the one session that definitely mattered was still open, and it
was opened *after* the cut-off with no new login.

Now the endpoint clears the session cookie, rotates a single-use bootstrap credential
in the running process, and verifies both terminal conditions before reporting
success. Getting back in is an explicit ``/api/auth/login``, not an automatic renewal.

Why the rotation is in the endpoint
-----------------------------------
``reset_bootstrap`` already existed but only writes files: the live process keeps its
old consumed object and refuses the new value until a restart. That is fine for a CLI
recovery and useless here — the operator needs a way back in *now*, without shell access
to the host.
"""

from __future__ import annotations

import pytest
from fastapi.testclient import TestClient
from pydantic import SecretStr

from soapbot.api.auth import SESSION_COOKIE, reset_auth
from soapbot.config import settings

BOOTSTRAP = "bootstrap-abc"


@pytest.fixture
def client(tmp_path, monkeypatch):
    from soapbot.app import create_app

    reset_auth()
    monkeypatch.setattr(settings, "init_token", SecretStr(BOOTSTRAP))
    monkeypatch.setattr(settings, "data_dir", tmp_path)
    monkeypatch.setattr(settings, "config_dir", tmp_path / "config")
    with TestClient(create_app()) as app_client:
        yield app_client
    reset_auth()


def _login(client: TestClient, token: str) -> str:
    response = client.post("/api/auth/login", json={"init_token": token})
    assert response.status_code == 200, response.text
    return response.json()["access_token"]


def _revoke_all(client: TestClient, token: str):
    return client.post(
        "/api/auth/revoke-all", headers={"Authorization": f"Bearer {token}"}
    )


def test_revoke_all_issues_no_replacement_session(client: TestClient) -> None:
    token = _login(client, BOOTSTRAP)
    response = _revoke_all(client, token)
    assert response.status_code == 200, response.text
    body = response.json()

    assert body["ok"] is True
    assert body["requires_login"] is True
    assert "access_token" not in body, "撤销后不得再签发会话令牌"
    assert body["bootstrap_token"]
    assert body["bootstrap_token"] != BOOTSTRAP


def test_the_callers_own_token_stops_working_immediately(client: TestClient) -> None:
    token = _login(client, BOOTSTRAP)
    _revoke_all(client, token)

    after = client.get(
        "/api/security/permissions", headers={"Authorization": f"Bearer {token}"}
    )
    assert after.status_code == 401


def test_the_rotated_bootstrap_is_the_only_way_back_in(client: TestClient) -> None:
    token = _login(client, BOOTSTRAP)
    rotated = _revoke_all(client, token).json()["bootstrap_token"]

    # The consumed secret stays dead — rotation replaces it, it does not resurrect it.
    assert (
        client.post("/api/auth/login", json={"init_token": BOOTSTRAP}).status_code
        == 401
    )
    # The new one works exactly once.
    assert (
        client.post("/api/auth/login", json={"init_token": rotated}).status_code == 200
    )
    assert (
        client.post("/api/auth/login", json={"init_token": rotated}).status_code == 401
    )


def test_the_session_cookie_is_cleared(client: TestClient) -> None:
    token = _login(client, BOOTSTRAP)
    response = _revoke_all(client, token)

    cookies = response.headers.get_list("set-cookie")
    assert any(SESSION_COOKIE in value for value in cookies), cookies


def test_a_closed_state_is_verified_not_assumed(
    client: TestClient, monkeypatch: pytest.MonkeyPatch
) -> None:
    """A store that silently failed to revoke must produce an error, not ``ok``."""
    from soapbot.security.revocation import RevocationStore

    token = _login(client, BOOTSTRAP)
    monkeypatch.setattr(RevocationStore, "is_revoked", lambda *a, **k: False)

    response = _revoke_all(client, token)
    assert response.status_code == 500
    assert "closed terminal state" in response.text


def test_a_fileless_bootstrap_rotates_only_in_memory() -> None:
    """An explicitly configured ``SOAPBOT_INIT_TOKEN`` has no file to rewrite.

    ``reset_bootstrap`` would fail here (nothing to write), and pretending otherwise
    would make "revoke everything" raise on deployments that configure the secret by
    environment. Rotating the in-memory value is the honest subset: a restart returns to
    the configured one, which is the operator's own lifecycle decision.
    """
    from soapbot.security.tokens import BootstrapToken

    bootstrap = BootstrapToken("configured-token", generated=False)
    assert bootstrap.redeem("configured-token") is True

    fresh = bootstrap.regenerate()

    assert fresh != "configured-token"
    assert bootstrap.available
    assert bootstrap.redeem("configured-token") is False
    assert bootstrap.redeem(fresh) is True
