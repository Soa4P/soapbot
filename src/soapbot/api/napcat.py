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
import logging
from typing import Any

from fastapi import APIRouter, Depends, HTTPException, Request

from soapbot.api.auth import require_api_auth
from soapbot.api.config_probe import _enforce_rate
from soapbot.api.config_write import _audit, _caller_label, _require_permission
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
    if state.get("status") == "running":
        login = await napcat.login_state()
    return {
        **state,
        "starting": _start_task is not None and not _start_task.done(),
        "image": napcat.IMAGE,
        "ws_url": f"ws://127.0.0.1:{napcat.WS_PORT}",
        "webui_url": f"http://127.0.0.1:{napcat.WEBUI_PORT}",
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
        raise HTTPException(status_code=409, detail=result.get("error", "no-qrcode"))
    _audit(_caller_label(request), "allow", "napcat_qr", [])
    return result

