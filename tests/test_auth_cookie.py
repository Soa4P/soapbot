"""The cookie session boundary, pinned with strict loopback auth switched ON.

tests/conftest.py turns ``strict_loopback_auth`` off for the rest of the suite so
business assertions do not each have to log in first. Everything here turns it back
on explicitly: these are the tests that say what production actually does.

What is asserted:

* login sets an HttpOnly, SameSite session cookie and a separate readable CSRF cookie;
* no credential is stored where page scripts can read it;
* a cookie-backed write needs both the CSRF header and a same-origin Origin;
* loopback may read in strict mode but may not change state without a credential;
* a role floor is enforced on config routes, not just declared in a signature;
* bearer tokens still work for scripts, which cannot use a browser cookie jar.
"""

from __future__ import annotations

import pytest
from fastapi.testclient import TestClient
from pydantic import SecretStr

from soapbot.api.auth import (
    CSRF_COOKIE,
    CSRF_HEADER,
    SESSION_COOKIE,
    get_token_service,
    reset_auth,
)
from soapbot.config import settings

INIT_TOKEN = "bootstrap-strict-tests"


@pytest.fixture
def strict_client(tmp_path, monkeypatch):
    from soapbot.app import create_app

    reset_auth()
    monkeypatch.setattr(settings, "strict_loopback_auth", True)
    monkeypatch.setattr(settings, "cookie_secure", False)
    monkeypatch.setattr(settings, "init_token", SecretStr(INIT_TOKEN))
    with TestClient(create_app()) as client:
        yield client
    reset_auth()


def _login(client: TestClient):
    response = client.post("/api/auth/login", json={"init_token": INIT_TOKEN})
    assert response.status_code == 200, response.text
    return response


def _csrf(client: TestClient) -> str:
    return client.cookies.get(CSRF_COOKIE, "")


def test_login_sets_an_http_only_session_cookie(strict_client: TestClient) -> None:
    response = _login(strict_client)
    cookies = response.headers.get_list("set-cookie")
    session = [c for c in cookies if c.startswith(f"{SESSION_COOKIE}=")]
    csrf = [c for c in cookies if c.startswith(f"{CSRF_COOKIE}=")]
    assert session and csrf, cookies
    assert "httponly" in session[0].lower()
    assert "samesite=lax" in session[0].lower()
    assert "httponly" not in csrf[0].lower(), "the CSRF cookie must be readable by the page"
    assert SESSION_COOKIE in strict_client.cookies


def test_cookie_alone_authenticates_a_read(strict_client: TestClient) -> None:
    _login(strict_client)
    response = strict_client.get("/api/security/permissions")
    assert response.status_code == 200, response.text


def test_a_cookie_write_without_csrf_is_refused(strict_client: TestClient) -> None:
    _login(strict_client)
    response = strict_client.post("/api/auth/logout")
    assert response.status_code == 403


def test_a_cookie_write_with_a_wrong_csrf_is_refused(strict_client: TestClient) -> None:
    _login(strict_client)
    response = strict_client.post("/api/auth/logout", headers={CSRF_HEADER: "not-the-value"})
    assert response.status_code == 403


def test_a_cookie_write_with_the_csrf_header_succeeds(strict_client: TestClient) -> None:
    _login(strict_client)
    response = strict_client.post("/api/auth/logout", headers={CSRF_HEADER: _csrf(strict_client)})
    assert response.status_code == 200, response.text
    assert not strict_client.cookies.get(SESSION_COOKIE)


def test_cross_origin_cookie_write_is_refused(strict_client: TestClient) -> None:
    _login(strict_client)
    response = strict_client.post(
        "/api/auth/logout",
        headers={CSRF_HEADER: _csrf(strict_client), "Origin": "https://evil.example"},
    )
    assert response.status_code == 403


def test_opaque_origin_is_not_treated_as_loopback(strict_client: TestClient) -> None:
    """A sandboxed iframe sends `Origin: null`; "no host" is not a loopback host."""
    _login(strict_client)
    response = strict_client.post(
        "/api/auth/logout",
        headers={CSRF_HEADER: _csrf(strict_client), "Origin": "null"},
    )
    assert response.status_code == 403


def test_refresh_without_csrf_is_refused(strict_client: TestClient) -> None:
    """Refresh rotates cookies, so it is a state change like any other POST."""
    _login(strict_client)
    response = strict_client.post("/api/auth/refresh")
    assert response.status_code == 403


def test_refresh_with_csrf_rotates_the_session(strict_client: TestClient) -> None:
    _login(strict_client)
    before_csrf = strict_client.cookies.get(CSRF_COOKIE)
    response = strict_client.post(
        "/api/auth/refresh", headers={CSRF_HEADER: _csrf(strict_client)}
    )
    assert response.status_code == 200, response.text
    assert strict_client.cookies.get(SESSION_COOKIE)
    # The CSRF value is rotated on every set_session call; that is the observable
    # proof the session was actually reissued rather than merely accepted.
    assert strict_client.cookies.get(CSRF_COOKIE) != before_csrf


def test_member_cannot_install_a_plugin(strict_client: TestClient) -> None:
    """A MEMBER who could load worker code but not edit config is an inversion."""
    service = get_token_service()
    assert service is not None
    token, _ = service.issue("member-user", role="member")
    strict_client.cookies.set(SESSION_COOKIE, token)
    strict_client.cookies.set(CSRF_COOKIE, "csrf-for-member")
    response = strict_client.post(
        "/api/plugins/install",
        headers={CSRF_HEADER: "csrf-for-member"},
        content=b"PK\x03\x04not-a-real-zip",
    )
    assert response.status_code == 403, response.text


def test_bearer_token_still_works_for_scripts(strict_client: TestClient) -> None:
    body = _login(strict_client).json()
    response = strict_client.get(
        "/api/security/permissions", headers={"Authorization": f"Bearer {body['access_token']}"}
    )
    assert response.status_code == 200, response.text
    # A bearer-authenticated write has no CSRF exposure: a cross-site page cannot
    # attach the header in the first place.
    logout = strict_client.post(
        "/api/auth/logout", headers={"Authorization": f"Bearer {body['access_token']}"}
    )
    assert logout.status_code == 200, logout.text


def test_strict_loopback_reads_but_refuses_writes(strict_client: TestClient) -> None:
    # No login at all: a loopback viewer may look, but may not change anything.
    assert strict_client.get("/api/security/permissions").status_code == 200
    refused = strict_client.post("/api/auth/logout")
    assert refused.status_code == 401


def test_strict_loopback_is_not_an_owner(strict_client: TestClient) -> None:
    from types import SimpleNamespace

    from soapbot.api.auth import authenticate

    request = SimpleNamespace(
        client=SimpleNamespace(host="127.0.0.1"),
        headers={},
        cookies={},
        method="GET",
        url=SimpleNamespace(path="/api/security/permissions", hostname="127.0.0.1"),
        state=SimpleNamespace(),
    )
    assert authenticate(request)["role"] == "member"


def test_role_floor_blocks_a_member_from_config_routes(strict_client: TestClient) -> None:
    # Build a member-role session directly with the app's own signer. A second
    # TokenService would produce a signature the app rejects with 401, which would
    # prove nothing about the role floor.
    service = get_token_service()
    assert service is not None
    token, _ = service.issue("member-user", role="member")
    strict_client.cookies.set(SESSION_COOKIE, token)
    strict_client.cookies.set(CSRF_COOKIE, "csrf-for-member")

    response = strict_client.get("/api/config/providers")
    assert response.status_code == 403, response.text


def test_role_gate_gets_its_identity_from_authentication(monkeypatch) -> None:
    """The role dependency must never compare an unauthenticated request's role.

    ``require_role`` receives its caller through ``Depends(require_api_auth)``. An
    anonymous remote request is therefore refused by that dependency before any
    role comparison happens, so the response cannot reveal which routes have a
    higher floor.
    """
    import asyncio
    from types import SimpleNamespace

    from fastapi import HTTPException

    from soapbot.api.auth import require_api_auth

    monkeypatch.setattr(settings, "strict_loopback_auth", True)
    request = SimpleNamespace(
        client=SimpleNamespace(host="203.0.113.9"),
        headers={},
        cookies={},
        method="GET",
        url=SimpleNamespace(path="/api/security/permissions", hostname="127.0.0.1"),
        state=SimpleNamespace(),
    )
    with pytest.raises(HTTPException) as excinfo:
        asyncio.run(require_api_auth(request))  # type: ignore[arg-type]
    assert excinfo.value.status_code == 401
