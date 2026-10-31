"""The NapCat integration, tested against the shapes a running container actually returns.

Every expectation here was read off a live container (``docker run mlikiowa/napcat-docker``)
rather than invented, because two of the three were wrong when guessed:

* ``/api/auth/login`` wants ``sha256(token + ".napcat")`` as ``hash`` — posting the raw token
  answers ``{"code":-1,"message":"token is empty"}``;
* ``GetQQLoginQrcode`` returns a **URL**, not a base64 PNG — code written for an image
  renders nothing and reports success;
* ``CheckLoginStatus`` distinguishes ``waiting_qrcode`` from ``isLogin``, which is the
  difference between "scan this" and "confirm on your phone".
"""

from __future__ import annotations

import hashlib
from pathlib import Path

import pytest

# Full dotted path on purpose: `scripts/check_test_gaps.py` looks for the module name in
# the tests as text, and `from soapbot.protocol import napcat` does not contain it.
import soapbot.protocol.napcat as napcat


def test_the_login_hash_is_sha256_of_token_plus_suffix(monkeypatch, tmp_path: Path) -> None:
    """Pinned because the wrong shape is not an error message a user can act on."""
    seen: dict[str, object] = {}

    async def fake_post(path: str, body: dict, *, token: str = "") -> dict:
        seen["path"] = path
        seen["body"] = body
        return {"code": 0, "data": {"Credential": "cred-123"}}

    monkeypatch.setattr(napcat, "_webui_post", fake_post)
    monkeypatch.setattr(napcat, "webui_token", lambda: "abc123")
    monkeypatch.setattr(napcat.settings, "data_dir", tmp_path)

    import asyncio

    credential = asyncio.run(napcat.login_token())

    assert credential == "cred-123"
    assert seen["path"] == "/api/auth/login"
    expected = hashlib.sha256(b"abc123.napcat").hexdigest()
    assert seen["body"] == {"hash": expected}


def test_a_missing_webui_token_makes_no_request(monkeypatch) -> None:
    """Before NapCat writes webui.json, "no token" is a normal state, not a failed login."""

    async def boom(*args, **kwargs):  # pragma: no cover - must not be called
        raise AssertionError("should not call the WebUI without a token")

    monkeypatch.setattr(napcat, "_webui_post", boom)
    monkeypatch.setattr(napcat, "webui_token", lambda: "")

    import asyncio

    assert asyncio.run(napcat.login_token()) == ""


def test_the_qr_is_returned_as_the_url_napcat_gives(monkeypatch) -> None:
    async def fake_post(path: str, body: dict, *, token: str = "") -> dict:
        if path == "/api/auth/login":
            return {"code": 0, "data": {"Credential": "c"}}
        return {"code": 0, "data": {"qrcode": "https://txz.qq.com/p?k=xyz"}}

    monkeypatch.setattr(napcat, "_webui_post", fake_post)
    monkeypatch.setattr(napcat, "webui_token", lambda: "t")

    import asyncio

    result = asyncio.run(napcat.qr_code())
    assert result == {"ok": True, "url": "https://txz.qq.com/p?k=xyz"}


def test_login_state_carries_the_phase_when_not_logged_in(monkeypatch) -> None:
    async def fake_post(path: str, body: dict, *, token: str = "") -> dict:
        if path == "/api/auth/login":
            return {"code": 0, "data": {"Credential": "c"}}
        return {
            "code": 0,
            "data": {"isLogin": False, "loginPhase": "waiting_qrcode", "uin": ""},
        }

    monkeypatch.setattr(napcat, "_webui_post", fake_post)
    monkeypatch.setattr(napcat, "webui_token", lambda: "t")

    import asyncio

    state = asyncio.run(napcat.login_state())
    assert state == {"ok": True, "logged_in": False, "phase": "waiting_qrcode", "account": ""}


def test_without_docker_the_status_says_so_instead_of_raising(monkeypatch) -> None:
    """The usual Windows host has no Docker; that is the answer, not an exception."""
    monkeypatch.setattr(napcat, "docker_available", lambda: False)
    assert napcat.container_status() == {"docker": False, "exists": False, "status": "no-docker"}
    assert napcat.start_container() == {"ok": False, "error": "no-docker"}


def test_the_panel_routes_live_where_the_client_looks_for_them() -> None:
    """A renamed path is a 404 in a browser and a green test suite otherwise."""
    import soapbot.api.napcat as napcat_api

    paths = {route.path for route in napcat_api.router.routes}
    assert paths == {
        "/api/protocol/napcat/status",
        "/api/protocol/napcat/start",
        "/api/protocol/napcat/stop",
        "/api/protocol/napcat/qr",
    }


@pytest.mark.parametrize(
    ("stdout", "expected"),
    [("running\n", "running"), ("exited\n", "exited")],
)
def test_container_status_reports_the_docker_state(monkeypatch, stdout: str, expected: str) -> None:
    class Result:
        returncode = 0
        stdout = ""
        stderr = ""

    result = Result()
    result.stdout = stdout  # type: ignore[attr-defined]

    monkeypatch.setattr(napcat, "docker_available", lambda: True)
    monkeypatch.setattr(napcat, "_docker", lambda *args, **kwargs: result)

    assert napcat.container_status()["status"] == expected
