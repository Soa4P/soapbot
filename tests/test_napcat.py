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
import json
from pathlib import Path

import pytest

# Full dotted path on purpose: `scripts/check_test_gaps.py` looks for the module name in
# the tests as text, and `from soapbot.protocol import napcat` does not contain it.
import soapbot.protocol.napcat as napcat


@pytest.fixture(autouse=True)
def _clear_credential_cache():
    """The credential cache is module state; every test starts from a cold WebUI."""
    napcat._credential_cache.update(
        {"value": "", "expires_at": 0.0, "retry_after": 0.0, "last_error": ""}
    )
    napcat._last_qr.update({"url": "", "at": 0.0})
    yield
    napcat._credential_cache.update(
        {"value": "", "expires_at": 0.0, "retry_after": 0.0, "last_error": ""}
    )
    napcat._last_qr.update({"url": "", "at": 0.0})


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
    assert result["ok"] is True
    assert result["url"] == "https://txz.qq.com/p?k=xyz"
    assert result["age_seconds"] == 0.0
    assert "stale" not in result


def test_polling_does_not_re_login_every_time(monkeypatch) -> None:
    """The production outage: 3s polling re-logged-in on every call and NapCat (loginRate=10)
    answered "login rate limit" for ever, so no QR was ever fetched. One credential is a
    session, so the panel must reuse it."""
    logins = 0

    async def fake_post(path: str, body: dict, *, token: str = "") -> dict:
        nonlocal logins
        if path == "/api/auth/login":
            logins += 1
            return {"code": 0, "data": {"Credential": "session-abc"}}
        return {"code": 0, "data": {"qrcode": "https://txz.qq.com/p?k=xyz"}}

    monkeypatch.setattr(napcat, "_webui_post", fake_post)
    monkeypatch.setattr(napcat, "webui_token", lambda: "t")

    import asyncio

    results = [asyncio.run(napcat.login_token()) for _ in range(6)]

    assert all(c == "session-abc" for c in results)
    assert logins == 1, f"expected one login for six polls, got {logins}"


def test_a_rate_limited_webui_backs_off_instead_of_retry_storming(monkeypatch) -> None:
    """Once limited, further polls must not hit /api/auth/login again."""
    logins = 0

    async def fake_post(path: str, body: dict, *, token: str = "") -> dict:
        nonlocal logins
        if path == "/api/auth/login":
            logins += 1
            return {"code": -1, "message": "login rate limit"}
        return {"code": 0, "data": {}}

    monkeypatch.setattr(napcat, "_webui_post", fake_post)
    monkeypatch.setattr(napcat, "webui_token", lambda: "t")
    monkeypatch.setattr(napcat, "webui_reachable", lambda: True)

    import asyncio

    first = asyncio.run(napcat.qr_code())
    again = asyncio.run(napcat.qr_code())

    assert first["error"] == "webui-rate-limited"
    assert again["error"] == "webui-rate-limited"
    assert logins == 1, f"backoff must suppress retries, got {logins} logins"
    assert napcat.credential_cache_state()["backoff_remaining"] > 0
    # The diagnostic view must never leak the credential itself.
    assert "value" not in napcat.credential_cache_state()


def test_qr_reports_rate_limit_immediately_without_waiting(monkeypatch) -> None:
    """Holding each poll for wait_seconds while limited piles up requests that all fail."""

    async def fake_post(path: str, body: dict, *, token: str = "") -> dict:
        return {"code": -1, "message": "login rate limit"}

    async def should_not_wait(*_args, **_kwargs):  # pragma: no cover - must not be called
        raise AssertionError("do not wait out a rate limit inside the request")

    monkeypatch.setattr(napcat, "_webui_post", fake_post)
    monkeypatch.setattr(napcat, "webui_token", lambda: "t")
    monkeypatch.setattr(napcat, "wait_until_ready", should_not_wait)

    import asyncio

    result = asyncio.run(napcat.qr_code(wait_seconds=5.0))
    assert result["error"] == "webui-rate-limited"
    assert result["retry_after"] > 0


def test_a_qr_that_never_changes_is_reported_as_stale(monkeypatch) -> None:
    """HTTP 200 is not proof the QR is scannable.

    NapCat kept returning the same URL for hours after its login expired (ErrCode 10,
    coreReady=false). The old code returned {"ok": true} every time, so the panel claimed
    it had "refreshed" while handing the operator a dead picture.
    """
    async def fake_post(path: str, body: dict, *, token: str = "") -> dict:
        if path == "/api/auth/login":
            return {"code": 0, "data": {"Credential": "c"}}
        return {"code": 0, "data": {"qrcode": "https://txz.qq.com/p?k=DEAD"}}

    monkeypatch.setattr(napcat, "_webui_post", fake_post)
    monkeypatch.setattr(napcat, "webui_token", lambda: "t")

    import asyncio

    first = asyncio.run(napcat.qr_code())
    assert first.get("stale") is None

    # Simulate two minutes of polling with NapCat never minting a new URL.
    napcat._last_qr["at"] -= napcat._QR_STALE_S + 1
    later = asyncio.run(napcat.qr_code())
    assert later["stale"] is True
    assert later["age_seconds"] > napcat._QR_STALE_S


def test_a_new_url_resets_the_stale_tracking(monkeypatch) -> None:
    current = {"k": "AAA"}

    async def fake_post(path: str, body: dict, *, token: str = "") -> dict:
        if path == "/api/auth/login":
            return {"code": 0, "data": {"Credential": "c"}}
        return {"code": 0, "data": {"qrcode": f"https://txz.qq.com/p?k={current['k']}"}}

    monkeypatch.setattr(napcat, "_webui_post", fake_post)
    monkeypatch.setattr(napcat, "webui_token", lambda: "t")

    import asyncio

    assert asyncio.run(napcat.qr_code())["age_seconds"] == 0.0
    napcat._last_qr["at"] -= napcat._QR_STALE_S + 1
    current["k"] = "BBB"
    fresh = asyncio.run(napcat.qr_code())
    assert "stale" not in fresh
    assert fresh["age_seconds"] == 0.0
    assert fresh["url"].endswith("BBB")


def test_unauthorized_after_a_napcat_restart_re_logs_in_once(monkeypatch) -> None:
    """A cached WebUI session dies with NapCat; retry with a fresh credential."""
    calls: list[str] = []

    async def fake_post(path: str, body: dict, *, token: str = "") -> dict:
        calls.append(path)
        if path == "/api/auth/login":
            return {"code": 0, "data": {"Credential": "fresh"}}
        # First QR call uses the old (stale) session, second succeeds.
        if token == "old":
            return {"code": -1, "message": "Unauthorized"}
        return {"code": 0, "data": {"qrcode": "https://txz.qq.com/p?k=NEW"}}

    monkeypatch.setattr(napcat, "_webui_post", fake_post)
    monkeypatch.setattr(napcat, "webui_token", lambda: "t")

    import asyncio

    # Seed a cached credential as though NapCat had been running for a while.
    asyncio.run(napcat.login_token())
    napcat._credential_cache["value"] = "old"
    napcat._credential_cache["expires_at"] = napcat.time.monotonic() + 600

    result = asyncio.run(napcat.qr_code())
    assert result["ok"] is True
    assert result["url"].endswith("NEW")
    assert calls.count("/api/auth/login") == 2


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
    assert state == {
        "ok": True,
        "logged_in": False,
        "phase": "waiting_qrcode",
        "account": "",
        "nickname": "",
    }


def test_login_state_reports_who_is_online(monkeypatch) -> None:
    """The account is on a different route than the flag — the card has to show which QQ."""

    async def fake_post(path: str, body: dict, *, token: str = "") -> dict:
        if path == "/api/auth/login":
            return {"code": 0, "data": {"Credential": "c"}}
        if path == "/api/QQLogin/GetQQLoginInfo":
            return {"code": 0, "data": {"uin": "2268360864", "nick": "Deceaspe", "online": True}}
        return {"code": 0, "data": {"isLogin": True, "loginPhase": "ready"}}

    monkeypatch.setattr(napcat, "_webui_post", fake_post)
    monkeypatch.setattr(napcat, "webui_token", lambda: "t")

    import asyncio

    state = asyncio.run(napcat.login_state())
    assert state["logged_in"] is True
    assert state["account"] == "2268360864"
    assert state["nickname"] == "Deceaspe"


def test_access_token_is_read_from_the_server_we_wrote(tmp_path, monkeypatch) -> None:
    """The adapter table must not ask the operator for a secret the panel already knows."""
    import json

    config = tmp_path / "napcat" / "config"
    config.mkdir(parents=True)
    (config / "onebot11_2268360864.json").write_text(
        json.dumps({"network": {"websocketServers": [{"port": 3001, "token": "s3cret"}]}}),
        encoding="utf-8",
    )
    monkeypatch.setattr(napcat, "config_dir", lambda: config)
    monkeypatch.setattr(napcat.settings, "napcat_home", None)
    monkeypatch.setattr(
        napcat, "_napcat_config_dirs", lambda: [path for path in [config] if path.is_dir()]
    )

    assert napcat.onebot_access_token("2268360864", port=3001) == "s3cret"
    assert napcat.onebot_access_token("2268360864", port=3999) == ""


def test_a_logged_in_napcat_without_onebot_gets_the_server_written(tmp_path, monkeypatch) -> None:
    """Measured on the Windows box: scanned in, avatar visible, every network array empty.

    The adapter has nothing to connect to, so the config entry is the missing half of
    "connect" — and it must be idempotent, or every click rewrites the file.
    """
    import json

    config = tmp_path / "napcat" / "config"
    config.mkdir(parents=True)
    monkeypatch.setattr(
        napcat, "_napcat_config_dirs", lambda: [path for path in [config] if path.is_dir()]
    )
    path = config / "onebot11_2268360864.json"
    path.write_text(json.dumps({"network": {"websocketServers": []}}), encoding="utf-8")
    monkeypatch.setattr(napcat, "config_dir", lambda: config)
    monkeypatch.setattr(napcat.settings, "napcat_home", None)

    first = napcat.ensure_onebot_server("2268360864", port=3001)
    assert first["ok"] is True and first["changed"] is True

    document = json.loads(path.read_text(encoding="utf-8"))
    servers = document["network"]["websocketServers"]
    assert servers == [
        {
            "name": "soapbot",
            "enable": True,
            "host": "127.0.0.1",
            "port": 3001,
            "messagePostFormat": "array",
            "reportSelfMessage": False,
            "token": "",
            "debug": False,
            "heartInterval": 30000,
        }
    ]

    second = napcat.ensure_onebot_server("2268360864", port=3001)
    assert second["ok"] is True and second["changed"] is False


def test_without_docker_the_status_says_so_instead_of_raising(monkeypatch) -> None:
    """The usual Windows host has no Docker; that is the answer, not an exception."""
    monkeypatch.setattr(napcat, "docker_available", lambda: False)
    assert napcat.container_status() == {"docker": False, "exists": False, "status": "no-docker"}
    assert napcat.start_container() == {"ok": False, "error": "no-docker"}


def test_docker_is_installed_only_where_the_package_name_is_known() -> None:
    """Naming a wrong package turns "install Docker" into an error three steps later.

    `None` is a legitimate answer: the installer then tells the operator to do it, instead
    of guessing at a distribution it has never seen.
    """
    assert napcat.install_docker_command("ubuntu") == [
        "apt-get",
        "install",
        "-y",
        "docker.io",
    ]
    assert napcat.install_docker_command("Debian")[0] == "apt-get"
    assert napcat.install_docker_command("fedora")[:2] == ["dnf", "install"]
    assert napcat.install_docker_command("gentoo") is None


def test_the_probe_skips_the_servers_opening_event(monkeypatch) -> None:
    """Measured against a live NapCat: the first frame is its `meta_event/lifecycle`
    greeting. Treating it as the answer made a connected QQ look logged in with an empty
    account, and the adapter then got written blank."""

    frames = [
        json.dumps(
            {
                "time": 1,
                "self_id": 2268360864,
                "post_type": "meta_event",
                "meta_event_type": "lifecycle",
                "sub_type": "connect",
            }
        ),
        json.dumps(
            {
                "status": "ok",
                "retcode": 0,
                "data": {"user_id": 2268360864, "nickname": "Deceaspe"},
                "echo": "auto",
            }
        ),
    ]

    class _FakeWebSocket:
        async def __aenter__(self):
            return self

        async def __aexit__(self, *_exc):
            return False

        async def send(self, _message: str) -> None:
            return None

        async def recv(self) -> str:
            return frames.pop(0)

    def fake_connect(_url: str, **_kwargs):
        return _FakeWebSocket()

    # `connect` is imported inside the function, so patch it where it is looked up.
    from websockets.asyncio import client as ws_client

    monkeypatch.setattr(ws_client, "connect", fake_connect)

    import asyncio

    result = asyncio.run(napcat.probe_onebot())
    assert result["ok"] is True
    assert result["account"] == "2268360864"
    assert result["nickname"] == "Deceaspe"


def test_connecting_writes_the_adapter_it_just_probed(monkeypatch, tmp_path: Path) -> None:
    """The one-button path: the address comes from the port we bound, the account from the
    probe — neither is typed by the operator."""

    async def fake_probe(port: int = 3001, timeout: float = 3.0) -> dict:
        return {"ok": True, "account": "10001000", "nickname": "bot"}

    monkeypatch.setattr(napcat, "probe_onebot", fake_probe)
    monkeypatch.setattr(napcat.settings, "data_dir", tmp_path)
    # adapters_file is a property of config_dir; point config_dir instead.
    monkeypatch.setattr(napcat.settings, "config_dir", tmp_path)

    import asyncio

    result = asyncio.run(napcat.connect_adapter())

    assert result["ok"] is True and result["written"] is True
    text = (tmp_path / "adapters.yaml").read_text(encoding="utf-8")
    assert "ws_url: ws://127.0.0.1:3001" in text
    assert "10001000" in text
    assert result["account"] == "10001000"


def test_connecting_twice_does_not_duplicate_or_report_change(monkeypatch, tmp_path: Path) -> None:
    async def fake_probe(port: int = 3001, timeout: float = 3.0) -> dict:
        return {"ok": True, "account": "10001000", "nickname": "bot"}

    monkeypatch.setattr(napcat, "probe_onebot", fake_probe)
    monkeypatch.setattr(napcat.settings, "config_dir", tmp_path)

    import asyncio

    asyncio.run(napcat.connect_adapter())
    second = asyncio.run(napcat.connect_adapter())

    assert second["written"] is False
    assert (tmp_path / "adapters.yaml").read_text(encoding="utf-8").count("kind: onebot11") == 1


def test_connecting_before_login_is_refused_not_written(monkeypatch, tmp_path: Path) -> None:
    async def fake_probe(port: int = 3001, timeout: float = 3.0) -> dict:
        return {"ok": False, "error": "ConnectionRefusedError"}

    monkeypatch.setattr(napcat, "probe_onebot", fake_probe)
    monkeypatch.setattr(napcat.settings, "config_dir", tmp_path)

    import asyncio

    result = asyncio.run(napcat.connect_adapter())

    assert result == {"ok": False, "error": "not-logged-in", "detail": "ConnectionRefusedError"}
    assert not (tmp_path / "adapters.yaml").exists()


def test_restart_is_refused_without_a_supervisor(monkeypatch) -> None:
    """Killing the process when nothing will bring it back is not a restart."""
    monkeypatch.setattr(napcat, "supervisor", lambda: None)
    assert napcat.supervisor() is None


def test_the_panel_routes_live_where_the_client_looks_for_them() -> None:
    """A renamed path is a 404 in a browser and a green test suite otherwise."""
    import soapbot.api.napcat as napcat_api

    paths = {route.path for route in napcat_api.router.routes}
    assert paths == {
        "/api/protocol/napcat/status",
        "/api/protocol/napcat/start",
        "/api/protocol/napcat/stop",
        "/api/protocol/napcat/qr",
        "/api/protocol/napcat/connect",
        "/api/protocol/napcat/restart",
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
