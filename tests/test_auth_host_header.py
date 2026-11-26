"""A local connection is not the same claim as a local *address* (audit S-AUTH-10).

The panel treats a request from 127.0.0.1 without a credential as an operator read. That
rule predates the observation that DNS rebinding makes "from 127.0.0.1" something a
remote page can arrange: ``evil.example`` resolves to the attacker's server first, then
to 127.0.0.1, and the browser — still believing it talks to evil.example — sends
``Host: evil.example`` over a genuinely local socket.

So the credential-less loopback branch also checks the ``Host`` header. The cost is
stated rather than hidden: a reverse proxy on the same host serving the panel under a
domain has to list that domain in ``SOAPBOT_TRUSTED_HOSTS``. Requests carrying a
credential never take this branch, so a logged-in panel is unaffected.

Assertions are about 403 (the Host rule) rather than 200: these fixtures build an app
with no runtime, so a request that passes authentication may still answer 503 for
reasons that have nothing to do with this test.
"""

from __future__ import annotations

import pytest
from fastapi.testclient import TestClient

from soapbot.app import create_app
from soapbot.config import settings

PROBE = "/api/memory/items"


@pytest.fixture
def client(tmp_path, monkeypatch) -> TestClient:
    monkeypatch.setattr(settings, "data_dir", tmp_path)
    # These tests are about the Host rule, so they must not inherit the suite-wide
    # allowlist entry for ``testserver``.
    monkeypatch.setattr(settings, "trusted_hosts", [])
    app = create_app()
    with TestClient(app) as c:
        yield c


def _status(client: TestClient, host: str, **headers: str) -> int:
    response = client.get(PROBE, headers={"host": host, **headers})
    return response.status_code


def test_a_rebound_name_is_refused_on_the_credential_less_path(client: TestClient) -> None:
    response = client.get(PROBE, headers={"host": "evil.example"})

    assert response.status_code == 403
    assert "Host" in response.json()["detail"]


def test_a_loopback_host_is_still_accepted(client: TestClient) -> None:
    """127.0.0.1, localhost and the bracketed IPv6 form all mean this machine."""
    for host in ("127.0.0.1:6185", "localhost:6185", "[::1]:6185"):
        assert _status(client, host) != 403, host


def test_a_configured_host_is_accepted(client: TestClient, monkeypatch) -> None:
    """A same-host reverse proxy serving the panel under a domain is the intended use."""
    monkeypatch.setattr(settings, "trusted_hosts", ["Panel.Example.COM"])

    assert _status(client, "panel.example.com") != 403


def test_a_missing_host_header_is_refused(client: TestClient) -> None:
    """No Host means nothing to check, and "cannot tell" is a refusal, not a pass."""
    assert _status(client, "") == 403


def test_case_and_a_trailing_dot_are_normalised(client: TestClient, monkeypatch) -> None:
    monkeypatch.setattr(settings, "trusted_hosts", ["panel.example.com"])

    assert _status(client, "LOCALHOST") != 403
    assert _status(client, "panel.example.com.") != 403
    assert _status(client, "evil.example") == 403


def test_a_credentialed_request_is_not_subject_to_the_host_rule(
    client: TestClient,
) -> None:
    """A reverse proxy terminates TLS under its own name; a token settles identity.

    Pinning this keeps the fix from turning into "every proxied deployment must
    reconfigure before it can use the panel".
    """
    init_token = (settings.data_dir / "init_token.txt").read_text(encoding="utf-8").strip()
    login = client.post(
        "/api/auth/login", json={"init_token": init_token}, headers={"host": "evil.example"}
    )
    assert login.status_code == 200, login.text

    token = login.json()["access_token"]
    status = _status(client, "evil.example", Authorization=f"Bearer {token}")
    assert status not in (401, 403), status
