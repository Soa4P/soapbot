"""Connectivity probes: what the panel's two "test" buttons actually promise.

Two distinct claims are under test, and conflating them is the bug these tests exist to
prevent:

* a provider probe answers "did something reply on this address", not "is my key valid" —
  so **401 is a pass**, and no credential is ever sent;
* an adapter probe answers "is this really OneBot on the other end" — so a handshake alone
  is not enough, ``get_login_info`` has to answer, and reverse mode can only report on the
  port it would bind.

Everything here is either a mock transport or a loopback server this test owns. Nothing
touches the internet: a test suite that needs api.deepseek.com is a suite that fails on a
train.
"""

from __future__ import annotations

import json
import socket
from pathlib import Path
from typing import Any

import httpx
import pytest
from fastapi.testclient import TestClient

import soapbot.api.config_probe as config_probe
from soapbot.security.posture import probe_endpoint
from soapbot.security.ratelimit import SlidingWindowLimiter


# ------------------------------------------------------------------ provider probe
def _factory(status: int):
    def build(**kwargs):
        transport = httpx.MockTransport(lambda request: httpx.Response(status))
        return httpx.AsyncClient(transport=transport, **kwargs)

    return build


@pytest.mark.parametrize(
    ("status", "reachable", "ok_expected"),
    [
        (200, True, True),
        (401, True, True),  # a rejection is proof of life — the core rule
        (403, True, True),
        (404, True, True),  # reachable, but the hint must name the /v1 mistake
        (500, False, False),
        (503, False, False),
    ],
)
async def test_probe_endpoint_classifies_status_codes(status, reachable, ok_expected) -> None:
    """401 must count as alive; 5xx must not. Both were previously guesswork in the UI."""
    result = await probe_endpoint("https://api.example.com/v1", timeout=3.0, client_factory=_factory(status))

    assert result["reachable"] is reachable
    assert result["ok"] is ok_expected
    assert result["status_code"] == status
    assert result["credential_sent"] is False
    assert result["target"] == "api.example.com"
    assert result["hint"]


async def test_a_transport_error_is_reported_not_raised() -> None:
    """A probe that raises turns a wrong hostname into a 500 and explains nothing."""

    def build(**kwargs):
        def boom(request):
            raise httpx.ConnectError("no route to host")

        return httpx.AsyncClient(transport=httpx.MockTransport(boom), **kwargs)

    result = await probe_endpoint("https://nope.invalid/v1", timeout=1.0, client_factory=build)

    assert result["ok"] is False
    assert result["reachable"] is False
    assert "ConnectError" in result["error"]
    assert result["elapsed_ms"] >= 0


async def test_a_404_hint_names_the_missing_prefix() -> None:
    """The single most common misconfiguration: base_url without ``/v1``."""
    result = await probe_endpoint("https://api.deepseek.com", timeout=3.0, client_factory=_factory(404))
    assert "/v1" in result["hint"]


async def test_an_empty_base_url_is_refused_before_any_socket() -> None:
    result = await probe_endpoint("   ", timeout=1.0)
    assert result["ok"] is False
    assert result["error"]


# ------------------------------------------------------------------- adapter probe
async def test_forward_probe_asks_for_login_info_on_a_real_socket() -> None:
    """A WebSocket that echoes the handshake but is not OneBot must not be called "ok"."""
    from websockets.asyncio.server import serve

    async def handler(ws) -> None:
        async for message in ws:
            body = json.loads(message)
            assert body["action"] == "get_login_info"
            await ws.send(
                json.dumps(
                    {
                        "status": "ok",
                        "retcode": 0,
                        "data": {"user_id": 10001, "nickname": "soapbot"},
                        "echo": "probe",
                    }
                )
            )

    async with serve(handler, "127.0.0.1", 0) as server:
        port = server.sockets[0].getsockname()[1]
        result = await config_probe.probe_forward(f"ws://127.0.0.1:{port}", token="s3cret")

    assert result["ok"] is True
    assert result["state"] == "handshake_ok"
    assert result["status_code"] == 101
    assert "10001" in result["detail"]
    # The token went out on the wire, but must never come back in the response.
    assert "s3cret" not in json.dumps(result)


async def test_a_websocket_that_does_not_speak_onebot_is_not_ok() -> None:
    from websockets.asyncio.server import serve

    async def handler(ws) -> None:
        async for _ in ws:
            await ws.send("hello, I am not OneBot")
            break

    async with serve(handler, "127.0.0.1", 0) as server:
        port = server.sockets[0].getsockname()[1]
        result = await config_probe.probe_forward(f"ws://127.0.0.1:{port}")

    assert result["ok"] is False
    assert result["state"] == "not_onebot"
    assert result["hint"]


async def test_a_closed_port_reports_unreachable() -> None:
    """Get a port by binding, then release it: nothing is listening there."""
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as probe:
        probe.bind(("127.0.0.1", 0))
        port = probe.getsockname()[1]

    result = await config_probe.probe_forward(f"ws://127.0.0.1:{port}", open_timeout=2.0)
    assert result["ok"] is False
    assert result["state"] == "unreachable"


def test_an_occupied_port_is_reported_as_probably_listening() -> None:
    """Reverse mode's only knowable fact — and EADDRINUSE is the *good* outcome."""
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as listener:
        listener.bind(("127.0.0.1", 0))
        listener.listen(1)
        port = listener.getsockname()[1]

        result = config_probe.probe_bind("127.0.0.1", port)

    assert result["ok"] is True, "a port in use is the healthy state for a reverse adapter"
    assert result["state"] == "in_use"
    assert "监听" in result["hint"]


def test_a_free_port_is_reported_as_not_listening_yet() -> None:
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as probe:
        probe.bind(("127.0.0.1", 0))
        port = probe.getsockname()[1]

    result = config_probe.probe_bind("127.0.0.1", port)

    assert result["ok"] is True
    assert result["state"] == "free"
    # The sentence that stops someone waiting for a connection this check cannot see.
    assert "测不到" in result["hint"]


# ------------------------------------------------------------------------- routes
@pytest.fixture
def client(tmp_path: Path, monkeypatch):
    from soapbot.app import create_app
    from soapbot.config import settings

    monkeypatch.setattr(settings, "config_dir", tmp_path)
    monkeypatch.setattr(settings, "enable_runtime", False)
    monkeypatch.setattr(config_probe, "_limiter", SlidingWindowLimiter(limit=30, window_seconds=60.0))
    with TestClient(create_app()) as instance:
        yield instance


def test_the_routes_live_under_the_config_prefix() -> None:
    paths = {route.path for route in config_probe.router.routes}
    assert config_probe.router.prefix == "/api/config"
    assert "/api/config/providers/test" in paths
    assert "/api/config/adapters/test" in paths


def test_provider_test_endpoint_returns_the_probe_contract(client: TestClient, monkeypatch) -> None:
    """The payload the page reads. Field names are the contract; renaming one is a bug."""
    canned: dict[str, Any] = {
        "ok": True,
        "target": "api.deepseek.com",
        "status_code": 401,
        "reachable": True,
        "elapsed_ms": 412,
        "error": "",
        "hint": "401/403 表示端点活着（本次未发送密钥）",
        "credential_sent": False,
    }

    async def fake(base_url: str, *, timeout: float = 15.0) -> dict[str, Any]:
        assert base_url == "https://api.deepseek.com/v1"
        return canned

    monkeypatch.setattr(config_probe, "probe_provider", fake)

    response = client.post(
        "/api/config/providers/test",
        json={"id": "deepseek", "base_url": "https://api.deepseek.com/v1"},
    )

    assert response.status_code == 200, response.text
    assert response.json() == canned


@pytest.mark.parametrize("url", ["file:///etc/passwd", "gopher://x:70", "api.deepseek.com/v1", ""])
def test_provider_test_refuses_a_non_http_target(client: TestClient, url: str) -> None:
    response = client.post("/api/config/providers/test", json={"base_url": url})
    assert response.status_code in (400, 422)


def test_adapter_test_refuses_a_non_websocket_url(client: TestClient) -> None:
    response = client.post(
        "/api/config/adapters/test",
        json={"kind": "onebot11", "mode": "forward", "ws_url": "http://127.0.0.1:3001"},
    )
    assert response.status_code == 400


def test_adapter_test_rejects_an_unknown_mode(client: TestClient) -> None:
    response = client.post("/api/config/adapters/test", json={"kind": "onebot11", "mode": "sideways"})
    assert response.status_code == 400


def test_adapter_test_passes_the_draft_values_through(client: TestClient, monkeypatch) -> None:
    seen: dict[str, Any] = {}

    async def fake(payload) -> dict[str, Any]:
        seen.update(payload.model_dump())
        return {
            "ok": True,
            "mode": "reverse",
            "target": "127.0.0.1:6700",
            "state": "in_use",
            "status_code": None,
            "elapsed_ms": 3,
            "error": "",
            "hint": "端口已被占用：可能适配器已在监听",
            "detail": "",
            "credential_sent": False,
        }

    monkeypatch.setattr(config_probe, "probe_adapter", fake)

    response = client.post(
        "/api/config/adapters/test",
        json={"kind": "onebot11", "mode": "reverse", "host": "127.0.0.1", "port": 6700},
    )

    assert response.status_code == 200, response.text
    assert response.json()["state"] == "in_use"
    assert seen["mode"] == "reverse"
    assert seen["port"] == 6700


def test_the_probe_is_rate_limited_per_caller(client: TestClient, monkeypatch) -> None:
    """Otherwise the panel is an SSRF tool with a nice UI: a slow port scanner."""
    monkeypatch.setattr(config_probe, "_limiter", SlidingWindowLimiter(limit=2, window_seconds=60.0))

    async def fake(base_url: str, *, timeout: float = 15.0) -> dict[str, Any]:
        return {"ok": True, "reachable": True, "status_code": 200, "target": "x", "elapsed_ms": 1}

    monkeypatch.setattr(config_probe, "probe_provider", fake)

    body = {"base_url": "https://api.example.com/v1"}
    assert client.post("/api/config/providers/test", json=body).status_code == 200
    assert client.post("/api/config/providers/test", json=body).status_code == 200
    third = client.post("/api/config/providers/test", json=body)
    assert third.status_code == 429
    assert "30" in third.json()["detail"] or "分钟" in third.json()["detail"]


def test_a_token_below_admin_cannot_probe(client: TestClient) -> None:
    """The probe dials an address the caller chose; that is not a read-only privilege."""
    from soapbot.api.auth import get_token_service

    service = get_token_service()
    assert service is not None, "the app lifespan installs the token service"
    token, _ = service.issue("member", role="member")

    response = client.post(
        "/api/config/providers/test",
        json={"base_url": "https://api.example.com/v1"},
        headers={"Authorization": f"Bearer {token}"},
    )

    assert response.status_code == 403


def test_a_masked_token_falls_back_to_the_saved_value(client: TestClient, tmp_path: Path) -> None:
    """Testing a saved row must not send ``********`` as a bearer token.

    The read endpoint masks a literal token, so the form posts the mask back. Treating it
    as a credential produces a 401 that blames a token which is actually correct.
    """
    from soapbot.core.config_write import MASK

    (tmp_path / "adapters.yaml").write_text(
        "adapters:\n  - kind: onebot11\n    ws_url: ws://saved:3001\n    access_token: env:OB_TOKEN\n",
        encoding="utf-8",
    )

    stored = config_probe._stored_adapter("onebot11")
    token, problem = config_probe._effective_token(MASK, stored)
    # The variable is not set in this test: reported as a problem, not sent as the mask.
    assert token == ""
    assert problem
    assert "OB_TOKEN" in problem
