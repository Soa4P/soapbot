"""Wave 7: the management API has a real authentication boundary.

Before this existed, every management route was protected by a client-IP check against
a loopback set. That is not a boundary: a reverse proxy makes remote requests genuinely
arrive from loopback, and the bind address is one environment variable away from
``0.0.0.0``. The plugin routes load code into the process, so "unauthenticated remote
code execution" was a configuration accident away.

What is asserted here:

* a token can be issued from the one-time bootstrap secret and then used;
* the bootstrap secret cannot be used twice;
* token validation actually validates (expiry, signature, audience, required claims);
* the loopback shortcut still works but cannot be driven from another origin;
* a short or missing signing key does not silently produce a weak token.
"""

from __future__ import annotations

import time
from types import SimpleNamespace

import jwt
import pytest
from fastapi.testclient import TestClient

from soapbot.api.auth import BootstrapToken, configure_auth, reset_auth
from soapbot.config import settings
from soapbot.security.tokens import ALGORITHM, AUDIENCE, TokenError, TokenService


@pytest.fixture
def service(tmp_path) -> TokenService:
    return TokenService(secret="x" * 40, ttl_hours=1, secret_file=tmp_path / "jwt.key")


def _request(host: str, *, headers: dict[str, str] | None = None, method: str = "GET"):
    return SimpleNamespace(
        client=SimpleNamespace(host=host),
        headers=headers or {},
        method=method,
        url=SimpleNamespace(path="/api/runtime"),
        state=SimpleNamespace(),
    )


# ================================================================== TokenService


def test_issue_and_verify_roundtrip(service: TokenService) -> None:
    token, claims = service.issue("operator")
    decoded = service.verify(token)
    assert decoded.subject == "operator"
    assert decoded.role == "owner"
    assert decoded.token_id == claims.token_id
    assert decoded.expires_at == claims.expires_at


def test_wrong_secret_is_rejected(service: TokenService, tmp_path) -> None:
    token, _ = service.issue()
    other = TokenService(secret="y" * 40, ttl_hours=1, secret_file=tmp_path / "other.key")
    with pytest.raises(TokenError):
        other.verify(token)


def test_expired_token_is_rejected(service: TokenService) -> None:
    """A token minted with a past ``exp`` must not verify.

    Hand-built rather than slept-for: a test that waits for a real expiry either sleeps
    for an hour or has a TTL measured in milliseconds, and the second kind is flaky on
    a loaded CI box.
    """
    now = int(time.time())
    expired = jwt.encode(
        {
            "sub": "operator",
            "role": "owner",
            "iat": now - 7200,
            "exp": now - 3600,
            "nbf": now - 7200,
            "jti": "abc",
            "aud": AUDIENCE,
            "iss": "soapbot",
        },
        service._key,  # type: ignore[attr-defined]
        algorithm=ALGORITHM,
    )
    with pytest.raises(TokenError, match="expired"):
        service.verify(expired)


def test_token_without_exp_is_rejected(service: TokenService) -> None:
    """``require`` matters: a token with no ``exp`` would be valid forever."""
    now = int(time.time())
    immortal = jwt.encode(
        {
            "sub": "operator",
            "role": "owner",
            "iat": now,
            "jti": "abc",
            "aud": AUDIENCE,
            "iss": "soapbot",
        },
        service._key,  # type: ignore[attr-defined]
        algorithm=ALGORITHM,
    )
    with pytest.raises(TokenError):
        service.verify(immortal)


def test_foreign_audience_is_rejected(service: TokenService) -> None:
    """Another service sharing this HMAC key must not mint tokens we accept."""
    now = int(time.time())
    foreign = jwt.encode(
        {
            "sub": "operator",
            "role": "owner",
            "iat": now,
            "exp": now + 600,
            "jti": "abc",
            "aud": "some-other-service",
            "iss": "soapbot",
        },
        service._key,  # type: ignore[attr-defined]
        algorithm=ALGORITHM,
    )
    with pytest.raises(TokenError):
        service.verify(foreign)


def test_short_configured_secret_is_refused(tmp_path) -> None:
    """A short HMAC key is offline-brute-forced from one captured token."""
    with pytest.raises(TokenError, match="at least"):
        TokenService(secret="short", secret_file=tmp_path / "jwt.key")


def test_secret_file_is_created_restrictive_and_reused(tmp_path) -> None:
    """

    The permission assertion goes through ``is_owner_only`` rather than reading
    ``st_mode`` directly: on Windows the bits do not exist and ``chmod`` only toggles
    read-only, so a raw check would either fail or (worse) silently assert nothing. The
    helper is the same one ``soapbot doctor`` uses, and it reports the platform
    limitation instead of pretending the control is in force.
    """
    from soapbot.security.files import POSIX, is_owner_only

    path = tmp_path / "jwt.key"
    first = TokenService(secret_file=path)
    assert path.exists()
    assert is_owner_only(path)
    if POSIX:
        assert path.stat().st_mode & 0o077 == 0

    # A second instance reads the same file, so tokens survive a restart.
    second = TokenService(secret_file=path)
    token, _ = first.issue()
    assert second.verify(token).subject == "operator"


# ================================================================ BootstrapToken


def test_bootstrap_token_is_single_use() -> None:
    """Reusable forever would make the file it is written to a permanent credential."""
    bootstrap = BootstrapToken("boot-secret")
    assert bootstrap.redeem("boot-secret") is True
    assert bootstrap.redeem("boot-secret") is False
    assert bootstrap.consumed is True


def test_bootstrap_token_rejects_wrong_value() -> None:
    bootstrap = BootstrapToken("boot-secret")
    assert bootstrap.redeem("boot-secreu") is False
    assert bootstrap.redeem("") is False
    assert bootstrap.consumed is False  # a failed attempt must not burn the token


def test_bootstrap_token_is_generated_when_unset() -> None:
    bootstrap = BootstrapToken("")
    assert bootstrap.generated is True
    assert len(bootstrap.reveal()) >= 20


# ============================================================== request handling


def test_anonymous_remote_client_is_refused(service: TokenService) -> None:
    from fastapi import HTTPException

    from soapbot.api.auth import authenticate

    configure_auth(service=service, bootstrap=BootstrapToken("b"))
    with pytest.raises(HTTPException) as exc:
        authenticate(_request("203.0.113.7"))
    assert exc.value.status_code == 401


def test_remote_client_with_valid_token_is_allowed(service: TokenService) -> None:
    """The token is the boundary; the source address is not."""
    from soapbot.api.auth import authenticate

    configure_auth(service=service, bootstrap=BootstrapToken("b"))
    token, _ = service.issue()
    result = authenticate(_request("203.0.113.7", headers={"Authorization": f"Bearer {token}"}))
    assert result["mode"] == "token"
    assert result["subject"] == "operator"


def test_garbage_token_is_refused(service: TokenService) -> None:
    from fastapi import HTTPException

    from soapbot.api.auth import authenticate

    configure_auth(service=service, bootstrap=BootstrapToken("b"))
    with pytest.raises(HTTPException) as exc:
        authenticate(_request("127.0.0.1", headers={"Authorization": "Bearer not-a-jwt"}))
    assert exc.value.status_code == 401


def test_loopback_without_token_is_allowed(service: TokenService) -> None:
    from soapbot.api.auth import authenticate

    configure_auth(service=service, bootstrap=BootstrapToken("b"))
    assert authenticate(_request("127.0.0.1"))["mode"] == "loopback"


def test_cross_site_post_from_loopback_is_refused(service: TokenService) -> None:
    """A form post is not subject to a CORS preflight, so Origin must be checked."""
    from fastapi import HTTPException

    from soapbot.api.auth import authenticate

    configure_auth(service=service, bootstrap=BootstrapToken("b"))
    with pytest.raises(HTTPException) as exc:
        authenticate(
            _request(
                "127.0.0.1",
                headers={"Origin": "https://evil.example"},
                method="POST",
            )
        )
    assert exc.value.status_code == 403


def test_cross_site_post_with_token_is_allowed(service: TokenService) -> None:
    """A token cannot be attached by a browser automatically, so Origin is irrelevant."""
    from soapbot.api.auth import authenticate

    configure_auth(service=service, bootstrap=BootstrapToken("b"))
    token, _ = service.issue()
    result = authenticate(
        _request(
            "203.0.113.7",
            headers={"Authorization": f"Bearer {token}", "Origin": "https://evil.example"},
            method="POST",
        )
    )
    assert result["mode"] == "token"


# ===================================================================== endpoints


@pytest.fixture
def app_client(tmp_path, monkeypatch):
    from soapbot.app import create_app

    reset_auth()
    monkeypatch.setattr(settings, "init_token", "bootstrap-abc")
    with TestClient(create_app()) as client:
        yield client
    reset_auth()


def test_login_exchanges_bootstrap_token(app_client: TestClient) -> None:
    response = app_client.post("/api/auth/login", json={"init_token": "bootstrap-abc"})
    assert response.status_code == 200
    body = response.json()
    assert body["token_type"] == "bearer"
    assert body["access_token"]
    assert body["expires_in"] > 0

    # The token works on a protected route.
    protected = app_client.get(
        "/api/security/permissions",
        headers={"Authorization": f"Bearer {body['access_token']}"},
    )
    assert protected.status_code == 200


def test_bootstrap_token_cannot_be_reused(app_client: TestClient) -> None:
    assert app_client.post("/api/auth/login", json={"init_token": "bootstrap-abc"}).status_code == 200
    again = app_client.post("/api/auth/login", json={"init_token": "bootstrap-abc"})
    assert again.status_code == 401


def test_wrong_bootstrap_token_is_refused(app_client: TestClient) -> None:
    response = app_client.post("/api/auth/login", json={"init_token": "guess"})
    assert response.status_code == 401


def test_login_is_rate_limited(app_client: TestClient) -> None:
    """The endpoint needs no credential, so it needs a budget."""
    codes = [
        app_client.post("/api/auth/login", json={"init_token": f"nope-{i}"}).status_code
        for i in range(6)
    ]
    assert codes[:5] == [401] * 5
    assert codes[5] == 429


def test_auth_status_reports_loopback_and_login_availability(app_client: TestClient) -> None:
    body = app_client.get("/api/auth/status").json()
    assert body["loopback"] is True
    assert body["mode"] == "loopback"
    assert body["login_available"] is True
    # Never the token itself.
    assert "init_token" not in body
    assert "bootstrap-abc" not in str(body)


def test_status_hides_login_after_use(app_client: TestClient) -> None:
    app_client.post("/api/auth/login", json={"init_token": "bootstrap-abc"})
    body = app_client.get("/api/auth/status").json()
    assert body["login_available"] is False


def test_generated_bootstrap_token_is_written_to_a_private_file(
    tmp_path, monkeypatch
) -> None:
    """Written to disk, not only logged.

    A credential in the log stream reaches whatever collects logs — frequently a shared
    system — and stays valid for the life of the process.
    """
    from soapbot.app import create_app
    from soapbot.security.files import is_owner_only

    reset_auth()
    monkeypatch.setattr(settings, "init_token", "")
    with TestClient(create_app()):
        path = settings.data_dir / "init_token.txt"
        assert path.exists()
        assert is_owner_only(path)
        token = path.read_text(encoding="utf-8")
        assert len(token) >= 20
    reset_auth()


def test_refresh_requires_a_token(app_client: TestClient) -> None:
    """Refreshing on the loopback fallback would let any local process mint a token."""
    assert app_client.post("/api/auth/refresh").status_code == 401


def test_refresh_reissues_for_a_valid_token(app_client: TestClient) -> None:
    login = app_client.post("/api/auth/login", json={"init_token": "bootstrap-abc"}).json()
    refreshed = app_client.post(
        "/api/auth/refresh",
        headers={"Authorization": f"Bearer {login['access_token']}"},
    )
    assert refreshed.status_code == 200
    assert refreshed.json()["access_token"]


def test_protected_routes_reject_bad_tokens(app_client: TestClient) -> None:
    for route in ("/api/security/permissions", "/api/security/audit", "/api/plugins"):
        response = app_client.get(route, headers={"Authorization": "Bearer bogus"})
        assert response.status_code == 401, route


def test_health_is_public(app_client: TestClient) -> None:
    """Liveness must not require a credential: probes do not carry one."""
    assert app_client.get("/api/health").status_code == 200
