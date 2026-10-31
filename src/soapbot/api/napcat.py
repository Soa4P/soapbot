"""Panel routes for the protocol end: start it, show its QR, say whether QQ is logged in.

Three endpoints, all of them conveniences over :mod:`soapbot.protocol.napcat`:

* ``GET  /api/protocol/napcat/status`` — what state the container and the login are in;
* ``POST /api/protocol/napcat/start``  — start it in the background, because a cold machine
  pulls about a gigabyte before anything runs and a request that hangs for three minutes
  looks broken (and is killed by every proxy in between);
* ``POST /api/protocol/napcat/stop``   — the same, in reverse;
* ``GET  /api/protocol/napcat/qr``     — the QR as a data URL, for the panel to render.

Permission is ``MANAGE_CONFIG``, which is what writing the adapter needs anyway. Starting a
container is more privileged than that in the abstract — it runs code on the host — but the
panel already loads plugins in-process for anyone with ``MANAGE_PLUGINS``, so pretending
this endpoint is the boundary would be theatre. It is loopback-only in practice because the
whole panel is, and it refuses to touch a container name it does not own.
"""

from __future__ import annotations

import asyncio
import contextlib
import logging
import os
from typing import Any

from fastapi import APIRouter, Depends, HTTPException, Request

from soapbot.api.auth import require_api_auth
from soapbot.api.config_probe import _enforce_rate
from soapbot.api.config_write import _audit, _caller_label, _require_permission
from soapbot.config import settings
from soapbot.protocol import napcat
from soapbot.security.principal import Permission

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/protocol/napcat", tags=["protocol"])

#: One background start at a time. Two clicks must not race to `docker run` the same name.
_start_task: asyncio.Task[Any] | None = None


def _background_start() -> None:
    global _start_task
    if _start_task is not None and not _start_task.done():
        return
    _start_task = asyncio.create_task(asyncio.to_thread(_start_and_wait))


def _start_and_wait() -> None:
    result = napcat.start_container()
    if not result.get("ok"):
        logger.warning("napcat start failed: %s", result)
        return
    ready = asyncio.run(napcat.wait_until_ready(120.0))
    if not ready.get("ok"):
        logger.warning("napcat WebUI did not become ready: %s", ready)


@router.get("/status")
async def status(
    request: Request,
    auth: dict[str, Any] = Depends(require_api_auth),
) -> dict[str, Any]:
    """Everything the panel needs to decide which button to show."""
    _require_permission(auth, request, Permission.MANAGE_CONFIG)
    state = await asyncio.to_thread(napcat.container_status)
    login: dict[str, Any] = {"ok": False, "logged_in": False, "account": "", "phase": ""}
    # Ask NapCat itself whenever its WebUI answers — not only when *our* container runs.
    # A hand-installed NapCat that has just been scanned in is logged in, and the panel said
    # otherwise for exactly as long as it took to configure an OneBot server it never needed.
    reachable = await asyncio.to_thread(napcat.webui_reachable)
    if state.get("status") == "running" or reachable:
        login = await napcat.login_state()
    # A hand-installed NapCat has no container and no WebUI token we know, but its OneBot
    # port answers — and that is the same evidence the adapter will get. Without this the
    # "Connect" button never appeared for exactly the people who installed it themselves.
    if not login.get("logged_in"):
        probe = await napcat.probe_onebot()
        if probe.get("ok"):
            login = {
                "ok": True,
                "logged_in": True,
                "account": probe.get("account", ""),
                "phase": "onebot",
            }
    # NapCat's own WebUI is token-protected, and the panel already knows where that token
    # lives — handing it over here is the difference between "press a button" and "go read
    # a log to find a secret". It is the operator's own NapCat on their own host, and the
    # route already requires MANAGE_CONFIG.
    webui_token = ""
    with contextlib.suppress(Exception):
        webui_token = await asyncio.to_thread(napcat.webui_token)
    # The token the OneBot server was configured with (usually none). The adapter form needs
    # it, and "read it out of a JSON file yourself" is not an answer.
    access_token = ""
    with contextlib.suppress(Exception):
        access_token = await asyncio.to_thread(
            napcat.onebot_access_token, str(login.get("account") or "")
        )

    return {
        **state,
        "starting": _start_task is not None and not _start_task.done(),
        "image": napcat.IMAGE,
        "ws_url": f"ws://127.0.0.1:{settings.napcat_ws_port}",
        "webui_url": f"http://127.0.0.1:{napcat.WEBUI_PORT}",
        # A hand-installed NapCat is not ours, but it is right there: the page has to say so
        # instead of talking about Docker on a host that never needed it.
        "webui_reachable": await asyncio.to_thread(napcat.webui_reachable),
        "webui_token": webui_token,
        "access_token": access_token,
        "access_token": access_token,
        "logged_in": login.get("logged_in", False),
        "account": login.get("account", ""),
        "phase": login.get("phase", ""),
    }


@router.post("/start")
async def start(
    request: Request,
    auth: dict[str, Any] = Depends(require_api_auth),
) -> dict[str, Any]:
    _require_permission(auth, request, Permission.MANAGE_CONFIG)
    _enforce_rate(auth, request)
    if not await asyncio.to_thread(napcat.docker_available):
        # Not an error: the common Windows install has no Docker, and the panel has an
        # honest answer for that case (open the WebUI of the NapCat already installed).
        return {"ok": False, "error": "no-docker"}
    _background_start()
    _audit(_caller_label(request), "allow", "napcat_start", [])
    return {"ok": True, "starting": True}


@router.post("/stop")
async def stop(
    request: Request,
    auth: dict[str, Any] = Depends(require_api_auth),
) -> dict[str, Any]:
    _require_permission(auth, request, Permission.MANAGE_CONFIG)
    _enforce_rate(auth, request)
    result = await asyncio.to_thread(napcat.stop_container)
    _audit(_caller_label(request), "allow", "napcat_stop", [])
    return result


@router.post("/connect")
async def connect(
    request: Request,
    auth: dict[str, Any] = Depends(require_api_auth),
) -> dict[str, Any]:
    """Write the adapter for the protocol end the panel started. One button, no typing."""
    _require_permission(auth, request, Permission.MANAGE_CONFIG)
    _enforce_rate(auth, request)
    result = await napcat.connect_adapter()
    if not result.get("ok"):
        # 409 again: "not scanned yet" is a state, not a fault.
        raise HTTPException(status_code=409, detail=result.get("error", "not-logged-in"))
    _audit(_caller_label(request), "allow", "napcat_connect", list(result.get("changed", [])))
    return result


@router.post("/restart")
async def restart(
    request: Request,
    auth: dict[str, Any] = Depends(require_api_auth),
) -> dict[str, Any]:
    """Exit so the supervisor brings the panel back with the new adapter.

    Refused when nothing supervises this process: a button that silently kills a
    manually-started service is worse than telling the truth and asking for a restart.
    """
    _require_permission(auth, request, Permission.MANAGE_CONFIG)
    _enforce_rate(auth, request)
    watcher = napcat.supervisor()
    if watcher is None:
        raise HTTPException(
            status_code=409,
            detail="no supervisor: restart the panel yourself (systemctl restart soapbot / docker restart)",
        )
    _audit(_caller_label(request), "allow", "napcat_restart", [watcher])
    # Answer first, exit after the response has a chance to flush.
    asyncio.get_running_loop().call_later(0.5, os._exit, 75)
    return {"ok": True, "restarting": True, "supervisor": watcher}


@router.get("/qr")
async def qr(
    request: Request,
    auth: dict[str, Any] = Depends(require_api_auth),
) -> dict[str, Any]:
    """The QR image the operator scans with their phone.

    Rate limited like the probes: each call drives a login attempt inside NapCat, and this
    is a route that hands out a credential-bearing image.
    """
    _require_permission(auth, request, Permission.MANAGE_CONFIG)
    _enforce_rate(auth, request)
    # A short wait covers the common "clicked Start, then clicked Show QR" case; a long one
    # would hold an HTTP request for the better part of a minute, which every proxy in
    # between eventually cuts. The card polls, so late answers are still delivered.
    result = await napcat.qr_code(wait_seconds=5.0)
    if not result.get("ok"):
        # 409 rather than 500: "not ready yet" is the normal state two seconds after start.
        # The detail is a machine token the UI maps to a sentence, so the person sees "the
        # WebUI answered but the login was refused — restart NapCat", not "409".
        raise HTTPException(status_code=409, detail=result.get("error", "no-qrcode"))
    _audit(_caller_label(request), "allow", "napcat_qr", [])
    return result

