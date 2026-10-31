"""Start a protocol end for the operator, instead of telling them to install one.

The remaining manual step in this project was always the same: "install NapCat, log your QQ
in, then type its WebSocket address into a form". The address part is now discoverable
(:mod:`soapbot.api.protocol`), but installing and logging in are still a second piece of
software, a second set of ports and a QR code in someone else's window.

Where a machine has Docker, that whole step can be one button: run the official NapCat
image with the panel's own data volume, hand back the QR code it prints, and let the
operator scan it with their phone. The panel then already knows the WebSocket port, because
it chose it — which is why :func:`start_container` binds the ports explicitly rather than
letting Docker assign them.

Where a machine has no Docker (the common Windows case), this module says so and points at
the WebUI that the installed NapCat already serves. It does not download an installer or
launch a QQ client silently: both are actions a person should take deliberately, and the
picture the user has to scan has to be in *their* client, not in ours.

Everything here is a thin wrapper over ``docker`` plus two HTTP calls to NapCat's own WebUI.
No new dependency and no reimplementation of the protocol: when NapCat changes its WebUI,
the container it ships changes too, and this module only has to keep matching it.
"""

from __future__ import annotations

import asyncio
import contextlib
import hashlib
import json
import logging
import os
import shutil
import subprocess
from pathlib import Path
from typing import Any

import httpx

from soapbot.config import settings

logger = logging.getLogger(__name__)

#: The official image. Pinned by digest in a deployment that cares; `latest` here because
#: the panel is a convenience path and an operator who wants reproducibility will use the
#: documented docker-compose route instead.
IMAGE = "mlikiowa/napcat-docker:latest"
CONTAINER = "soapbot-napcat"

#: The ports NapCat itself uses inside the container. Bound explicitly on the host so the
#: panel can write the adapter without asking, and bound on loopback so a protocol end with
#: a QQ session in it is not reachable from the network.
WS_PORT = 3001
WEBUI_PORT = 6099

#: Starting a container means pulling ~1GB on a cold machine. Long, but bounded: a command
#: that can hang for ever is worse than one that fails and says so.
START_TIMEOUT = 180.0
STATUS_TIMEOUT = 20.0
HTTP_TIMEOUT = 8.0


def install_docker_command(distro: str) -> list[str] | None:
    """How to install Docker on this distro, or ``None`` when we have no business guessing.

    Only the two families that are actually supported are named. A wrong package name on an
    unfamiliar distribution is worse than saying "install it yourself": the error arrives
    three steps later, from a package manager, in a language about repositories.
    """
    name = distro.lower()
    if name in {"ubuntu", "debian", "pop", "linuxmint", "raspbian"}:
        # `docker.io` from the distribution, not Docker's own repository: one apt command,
        # no curl|sh, no third-party key added to a server somebody else operates.
        return ["apt-get", "install", "-y", "docker.io"]
    if name in {"fedora", "rhel", "centos", "rocky", "almalinux"}:
        return ["dnf", "install", "-y", "docker"]
    return None


def docker_available() -> bool:
    """Is there a Docker *daemon* to talk to (not just a CLI on PATH)?"""
    if not shutil.which("docker"):
        return False
    probe = subprocess.run(
        ["docker", "version", "--format", "{{.Server.Version}}"],
        capture_output=True,
        text=True,
        encoding="utf-8",
        errors="replace",
        timeout=STATUS_TIMEOUT,
    )
    return probe.returncode == 0


def _docker(*args: str, timeout: float = STATUS_TIMEOUT) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        ["docker", *args],
        capture_output=True,
        text=True,
        encoding="utf-8",
        errors="replace",
        timeout=timeout,
    )


def webui_reachable(port: int = WEBUI_PORT, timeout: float = 2.0) -> bool:
    """Is a NapCat WebUI answering on this host?

    The panel has to be able to tell "there is no protocol end here" from "there is one,
    installed by hand, and it is waiting for a scan". Without this the Configure page led
    with the Docker advice on a machine that already had NapCat running.
    """
    try:
        response = httpx.get(f"http://127.0.0.1:{port}/", timeout=timeout, trust_env=False)
    except Exception:
        return False
    return response.status_code < 500


def container_status() -> dict[str, Any]:
    """``exists`` and ``status`` for our container, without assuming Docker is there."""
    if not docker_available():
        return {"docker": False, "exists": False, "status": "no-docker"}
    found = _docker("inspect", "-f", "{{.State.Status}}", CONTAINER)
    if found.returncode != 0:
        return {"docker": True, "exists": False, "status": "absent"}
    return {"docker": True, "exists": True, "status": found.stdout.strip() or "unknown"}


def _owns_container() -> bool:
    """Was this container created by us? Checks the label, not the name."""
    found = _docker("inspect", "-f", '{{ index .Config.Labels "soapbot.protocol" }}', CONTAINER)
    return found.returncode == 0 and found.stdout.strip() == "napcat"


def config_dir() -> Path:
    """Where NapCat's own config lives, on the host side of the bind mount."""
    return settings.data_dir / "napcat" / "config"


def webui_token() -> str:
    """The NapCat WebUI token, from an explicit setting or from NapCat's own config.

    Order matters: a token someone typed wins over a guess, and the container path we mount
    ourselves comes last because a hand-installed NapCat is a different layout — measured on
    Windows: ``<home>\\napcat\\config\\webui.json``, one level deeper than the Linux container's
    ``/app/napcat/config/webui.json``.
    """
    if settings.napcat_webui_token:
        return settings.napcat_webui_token

    candidates: list[Path] = [config_dir() / "webui.json"]
    if settings.napcat_home is not None:
        candidates += [
            settings.napcat_home / "config" / "webui.json",
            settings.napcat_home / "napcat" / "config" / "webui.json",
        ]

    for path in candidates:
        try:
            payload = json.loads(path.read_text(encoding="utf-8"))
        except (OSError, ValueError):
            continue
        token = payload.get("token")
        if token:
            return str(token)
    return ""


def start_container() -> dict[str, Any]:
    """Run the image with our own volume and loopback ports. Idempotent.

    Ports are bound explicitly to 127.0.0.1 for the same reason the panel itself binds
    loopback: this container holds a logged-in QQ session, and a QQ session reachable from
    the network is an account takeover waiting for a scanner.
    """
    if not docker_available():
        return {"ok": False, "error": "no-docker"}

    state = container_status()
    if state["exists"] and not _owns_container():
        # Same lesson as the systemd unit: a container with this name may belong to an
        # earlier deployment. Starting it would run somebody's QQ session under our ports.
        return {"ok": False, "error": "container-name-taken"}
    if state["exists"] and state["status"] == "running":
        return {"ok": True, "started": False, "status": "running"}
    if state["exists"]:
        # Stopped container: start it rather than creating a second one, or the volume and
        # the session state in it get orphaned on every click.
        result = _docker("start", CONTAINER)
        return {"ok": result.returncode == 0, "started": result.returncode == 0, "status": "starting"}

    config_dir().mkdir(parents=True, exist_ok=True)
    (settings.data_dir / "napcat" / "qq").mkdir(parents=True, exist_ok=True)

    result = _docker(
        "run",
        "-d",
        "--name",
        CONTAINER,
        "--restart",
        "unless-stopped",
        # Marks it as ours, so a later start never adopts a container someone else made.
        "--label",
        "soapbot.protocol=napcat",
        "-p",
        # Inside the container NapCat always listens on 3001; the host side is ours to pick,
        # which is what makes two instances (or an existing NapCat) coexist.
        f"127.0.0.1:{settings.napcat_ws_port}:{WS_PORT}",
        "-p",
        f"127.0.0.1:{WEBUI_PORT}:{WEBUI_PORT}",
        "-v",
        f"{config_dir()}:/app/napcat/config",
        "-v",
        f"{settings.data_dir / 'napcat' / 'qq'}:/app/.config/QQ",
        IMAGE,
        timeout=START_TIMEOUT,
    )
    if result.returncode != 0:
        detail = (result.stderr or result.stdout or "").strip().splitlines()[-3:]
        return {"ok": False, "error": "docker-run-failed", "detail": "\n".join(detail)}
    return {"ok": True, "started": True, "status": "starting"}


def stop_container() -> dict[str, Any]:
    if not docker_available():
        return {"ok": False, "error": "no-docker"}
    result = _docker("stop", CONTAINER, timeout=60.0)
    return {"ok": result.returncode == 0}


async def _webui_post(path: str, body: dict[str, Any], *, token: str = "") -> dict[str, Any]:
    """One call to NapCat's own WebUI API, without a system proxy in the way."""
    headers = {"Content-Type": "application/json"}
    if token:
        headers["Authorization"] = f"Bearer {token}"
    async with httpx.AsyncClient(
        base_url=f"http://127.0.0.1:{WEBUI_PORT}",
        timeout=HTTP_TIMEOUT,
        trust_env=False,  # a loopback call must never consult proxy settings
    ) as client:
        response = await client.post(path, json=body, headers=headers)
    try:
        payload = response.json()
    except ValueError:
        return {"code": response.status_code, "data": None, "raw": response.text[:200]}
    return payload if isinstance(payload, dict) else {"code": 0, "data": payload}


async def login_token() -> str:
    """Exchange the on-disk WebUI token for a credential, the way NapCat's own UI does.

    Not ``{"token": raw}``: the WebUI posts ``sha256(token + ".napcat")`` as ``hash``, and
    the raw token is rejected with "token is empty". This was read out of the bundle NapCat
    ships (``static/assets/*.js``: ``SHA256(t+".napcat").toString()``) and then confirmed
    against a running container — guessing the shape produced exactly that error.
    """
    raw = webui_token()
    if not raw:
        return ""
    digest = hashlib.sha256(f"{raw}.napcat".encode()).hexdigest()
    payload = await _webui_post("/api/auth/login", {"hash": digest})
    data = payload.get("data") or {}
    if isinstance(data, dict):
        for key in ("Credential", "credential"):
            if data.get(key):
                return str(data[key])
    if isinstance(data, str):
        return data
    return ""


async def qr_code(wait_seconds: float = 0.0) -> dict[str, Any]:
    """The login QR **URL**, not an image.

    Measured against the running container: ``GetQQLoginQrcode`` returns
    ``{"data": {"qrcode": "https://txz.qq.com/p?k=…"}}`` — the WebUI draws that URL into a
    QR in the browser. Assuming a base64 PNG produced an empty screen and a 68-character
    "image"; returning the URL and letting the panel render it is both correct and smaller.

    ``wait_seconds`` exists because the honest sequence is "press Start, press Show QR" and
    the container needs the better part of a minute before its WebUI answers. Returning 409
    instantly turned that normal race into an error the operator had to retry by hand.
    """
    credential = ""
    with contextlib.suppress(httpx.HTTPError, OSError):
        credential = await login_token()
    if not credential and wait_seconds > 0:
        await wait_until_ready(wait_seconds)
        with contextlib.suppress(httpx.HTTPError, OSError):
            credential = await login_token()
    if not credential:
        # Distinguish "still booting" from "booting finished but the login exchange failed".
        # The latter is the state that reads as "准备不好" forever: the WebUI answers, the
        # token is there, and still no credential — a stale NapCat process, fixed by restart.
        if webui_reachable():
            return {"ok": False, "error": "webui-login-failed"}
        return {"ok": False, "error": "webui-not-ready"}

    try:
        payload = await _webui_post(
            "/api/QQLogin/GetQQLoginQrcode", {"qrcode": True}, token=credential
        )
    except (httpx.HTTPError, OSError) as exc:
        return {"ok": False, "error": "webui-unreachable", "detail": str(exc)[:200]}

    data = payload.get("data")
    url = str(data.get("qrcode") or data.get("qrcodeurl") or "") if isinstance(data, dict) else ""
    if not url:
        return {"ok": False, "error": "no-qrcode", "detail": json.dumps(payload)[:300]}
    return {"ok": True, "url": url}


async def login_state() -> dict[str, Any]:
    """Whether the QQ account has been scanned in yet.

    ``loginPhase`` is carried along: "waiting_qrcode" and "waiting_confirm" look identical
    from ``isLogin: false`` alone, and the difference is what the person in front of the
    screen needs to be told (scan it / confirm on your phone).
    """
    try:
        credential = await login_token()
        payload = await _webui_post("/api/QQLogin/CheckLoginStatus", {}, token=credential)
    except (httpx.HTTPError, OSError):
        return {"ok": False, "logged_in": False, "phase": ""}
    data = payload.get("data") or {}
    if not isinstance(data, dict):
        return {"ok": True, "logged_in": False, "phase": ""}
    logged_in = bool(data.get("isLogin"))

    # CheckLoginStatus says *whether*, not *who* — the account is on the login-info route.
    # Without it the panel can only say "logged in", and the operator has to open another
    # window to learn which of their QQ numbers just went online.
    account = ""
    nickname = ""
    if logged_in:
        with contextlib.suppress(httpx.HTTPError, OSError):
            info = await _webui_post("/api/QQLogin/GetQQLoginInfo", {}, token=credential)
            info_data = info.get("data") or {}
            if isinstance(info_data, dict):
                account = str(info_data.get("uin") or "")
                nickname = str(info_data.get("nick") or "")

    return {
        "ok": True,
        "logged_in": logged_in,
        "phase": str(data.get("loginPhase") or ""),
        "account": account,
        "nickname": nickname,
    }


async def probe_onebot(port: int = WS_PORT, timeout: float = 3.0) -> dict[str, Any]:
    """Ask the OneBot port who is on the other end.

    This is the honest definition of "logged in": NapCat only opens its WebSocket server
    after a QQ account has been scanned in. Checking that instead of a WebUI flag means the
    panel's answer is the same thing the adapter will see when it connects.
    """
    from websockets.asyncio.client import connect

    try:
        async with connect(
            f"ws://127.0.0.1:{port}",
            open_timeout=timeout,
            close_timeout=1.0,
            max_size=1024 * 1024,
        ) as ws:
            await ws.send(json.dumps({"action": "get_login_info", "params": {}, "echo": "auto"}))
            raw = await asyncio.wait_for(ws.recv(), timeout=timeout)
    except Exception as exc:  # websockets raises a wide family: refused, timeout, protocol
        return {"ok": False, "error": type(exc).__name__}
    try:
        payload = json.loads(raw)
    except ValueError:
        return {"ok": False, "error": "not-json"}
    if payload.get("retcode") not in (0, "0", None):
        return {"ok": False, "error": "refused"}
    data = payload.get("data") or {}
    return {
        "ok": True,
        "account": str(data.get("user_id") or ""),
        "nickname": str(data.get("nickname") or ""),
    }


def _napcat_config_dirs() -> list[Path]:
    """Every plausible place a NapCat keeps its config on this machine.

    Three layouts are real: the container's bind mount under our data dir, a hand-installed
    NapCat under its own home (``<home>/napcat/config``), and — measured on the Windows box —
    a NapCat whose ``SOAPBOT_NAPCAT_HOME`` was never set, so the only evidence is next to
    the running JetBrains-style install in ``C:\\napcat\\napcat\\config``.
    """
    dirs = [config_dir()]
    if settings.napcat_home is not None:
        dirs += [settings.napcat_home / "napcat" / "config", settings.napcat_home / "config"]
    dirs += [Path("/c/napcat/napcat/config"), Path("C:/napcat/napcat/config")]
    dirs += [Path("/app/napcat/config"), Path("/opt/napcat/config")]
    return [path for path in dirs if path.is_dir()]


def onebot_access_token(account: str = "", port: int | None = None) -> str:
    """The ``token`` our OneBot server was configured with (``""`` means none).

    The adapter table asks for an access token and the form renders an empty box, which reads
    "you must invent a secret" — when the honest answer is "whatever NapCat's entry says",
    and usually that is nothing. Reading it from the same file we write keeps the two ends
    from ever disagreeing.
    """
    target_port = port or settings.napcat_ws_port
    for base in _napcat_config_dirs():
        try:
            names = list(base.glob("onebot11_*.json"))
        except OSError:
            continue
        for path in names:
            if account and account not in path.name:
                continue
            try:
                document = json.loads(path.read_text(encoding="utf-8"))
            except (OSError, ValueError):
                continue
            servers = (document.get("network") or {}).get("websocketServers") or []
            for entry in servers:
                if not isinstance(entry, dict) or entry.get("port") != target_port:
                    continue
                token = entry.get("token")
                return str(token) if token else ""
    return ""


def ensure_onebot_server(account: str, port: int | None = None) -> dict[str, Any]:
    """Give NapCat a loopback OneBot WebSocket server, because a fresh install has none.

    Measured on a hand-installed NapCat after a successful scan: ``onebot11_<uin>.json`` had
    every network array empty, so nothing listened on 3001 and the panel — which defines
    "logged in" as "the OneBot port answers" — reported false while the QQ avatar was right
    there in NapCat's own WebUI. Writing the entry is the missing half of "connect".
    """
    target_port = port or settings.napcat_ws_port
    for base in _napcat_config_dirs():
        path = base / f"onebot11_{account}.json"
        if not path.exists():
            continue
        try:
            document = json.loads(path.read_text(encoding="utf-8"))
        except (OSError, ValueError):
            return {"ok": False, "error": "unreadable", "path": str(path)}
        network = document.setdefault("network", {})
        servers = network.setdefault("websocketServers", [])
        if not isinstance(servers, list):
            return {"ok": False, "error": "unexpected-shape", "path": str(path)}
        entry = {
            "name": "soapbot",
            "enable": True,
            "host": "127.0.0.1",
            "port": target_port,
            "messagePostFormat": "array",
            "reportSelfMessage": False,
            "token": "",
            "debug": False,
            "heartInterval": 30000,
        }
        for index, existing in enumerate(servers):
            if isinstance(existing, dict) and (
                existing.get("name") == "soapbot" or existing.get("port") == target_port
            ):
                if existing.get("enable") and existing.get("port") == target_port:
                    return {"ok": True, "changed": False, "path": str(path)}
                servers[index] = {**existing, **entry}
                break
        else:
            servers.append(entry)
        path.write_text(json.dumps(document, ensure_ascii=False, indent=2), encoding="utf-8")
        logger.info("wrote OneBot WS server %s into %s", target_port, path)
        return {"ok": True, "changed": True, "path": str(path)}
    return {"ok": False, "error": "config-not-found"}


async def connect_adapter() -> dict[str, Any]:
    """Write the adapter that matches the protocol end we started.

    The address is not a guess: :func:`start_container` bound 127.0.0.1:3001, and the account
    number comes from the same ``get_login_info`` the adapter will call. This is the step
    that turns "scan the QR, then type a WebSocket URL into a table" into one button.
    """
    from soapbot.core import config_write

    probe = await probe_onebot(settings.napcat_ws_port)
    if not probe.get("ok"):
        # Not listening yet — either the account is not scanned in, or (very commonly) it is
        # scanned in but NapCat was never told to open a OneBot server. Ask the WebUI which
        # it is, and write the server entry when that is the missing piece.
        state = await login_state()
        if not state.get("logged_in"):
            return {"ok": False, "error": "not-logged-in", "detail": probe.get("error", "")}
        written = ensure_onebot_server(str(state.get("account") or ""))
        return {
            "ok": False,
            "error": "onebot-server-missing",
            "detail": written,
            "account": state.get("account", ""),
            "nickname": state.get("nickname", ""),
            "needs_restart": bool(written.get("changed")),
        }

    path = settings.adapters_file
    document = config_write.read_document(path)
    entry = {
        "kind": "onebot11",
        "mode": "forward",
        "enabled": True,
        "ws_url": f"ws://127.0.0.1:{settings.napcat_ws_port}",
        "account_id": probe.get("account", ""),
    }
    patched, changed = config_write.apply_adapter_patch(document, [entry])
    if not changed:
        return {
            "ok": True,
            "written": False,
            "reason": "unchanged",
            "ws_url": entry["ws_url"],
            "account": probe.get("account", ""),
        }
    config_write.write_atomic(path, config_write.render(patched))
    logger.info("adapter written from the managed protocol end: %s", changed)
    return {
        "ok": True,
        "written": True,
        "changed": changed,
        "ws_url": entry["ws_url"],
        "account": probe.get("account", ""),
    }


def supervisor() -> str | None:
    """What will bring this process back after it exits, if anything.

    A self-restart is only honest when something is watching: systemd (a unit with
    Restart=always), or Docker (a container restart policy). Without that, exiting from a
    button is just killing the service.
    """
    if Path("/run/systemd/system").exists() and os.environ.get("INVOCATION_ID"):
        return "systemd"
    if Path("/.dockerenv").exists():
        return "docker"
    return None


async def wait_until_ready(seconds: float = 120.0) -> dict[str, Any]:
    """Poll until the WebUI answers with a credential.

    A container that has just started has no ``webui.json`` yet — NapCat writes it after QQ
    has begun booting — so "file missing" is the normal first answer for ten or twenty
    seconds, not a failure.
    """
    deadline = asyncio.get_running_loop().time() + seconds
    while asyncio.get_running_loop().time() < deadline:
        if webui_token():
            try:
                if await login_token():
                    return {"ok": True}
            except (httpx.HTTPError, OSError):
                pass
        await asyncio.sleep(2.0)
    return {"ok": False, "error": "timeout"}
