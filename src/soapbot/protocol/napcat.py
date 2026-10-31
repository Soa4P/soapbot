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
    """NapCat writes its WebUI token here on first start.

    Read from the mounted volume rather than kept in a setting of our own: one source of
    truth, and an operator who changed it in NapCat's own WebUI does not have to change it
    twice. Absent or unreadable simply means "not ready yet" — the caller waits.
    """
    path = config_dir() / "webui.json"
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return ""
    token = payload.get("token")
    return str(token) if token else ""


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
        f"127.0.0.1:{WS_PORT}:{WS_PORT}",
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
    return {
        "ok": True,
        "logged_in": bool(data.get("isLogin")),
        "phase": str(data.get("loginPhase") or ""),
        "account": str(data.get("uin") or ""),
    }


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
