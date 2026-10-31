"""Find the protocol end that is already running on this machine.

The gap this closes is the one every tutorial has: "install NapCat, then configure the
adapter". Someone who has just installed NapCat has no idea which port it opened, whether
it is running, or whether it is even the right kind of server — and the panel asks them to
type a WebSocket URL. Asking a person to know that is asking them to know the architecture.

So the panel looks instead. It walks a short, fixed list of ports that OneBot protocol
ends actually use (plus whatever the saved adapters already point at), and for each one
answers the only three questions that matter:

* ``onebot`` — the handshake completed and ``get_login_info`` answered. This is a protocol
  end that is logged in, and the reply even names the account, which is the value the
  adapter's ``account_id`` wants.
* ``http`` — something answers HTTP. Usually NapCat's own WebUI (6099), i.e. "installed but
  not logged in yet". Naming it is the difference between "nothing is listening" and
  "it is running, go scan the QR".
* ``closed`` — nothing there.

Deliberately not a general port scanner: loopback only, a fixed candidate list, at most 16
ports per call, capped hits, and the same 30/minute budget as the probe buttons. A learned
lesson from the probe endpoints: anything that answers "what is on this address" is also a
map of the network, and the answer must be expensive to abuse.
"""

from __future__ import annotations

import asyncio
import logging
from typing import Any

import httpx
from fastapi import APIRouter, Depends, HTTPException, Query, Request

from soapbot.api.auth import require_api_auth
from soapbot.api.config_probe import _enforce_rate, probe_forward
from soapbot.api.config_write import _audit, _caller_label, _require_permission
from soapbot.config import settings
from soapbot.core import config_write
from soapbot.security.principal import Permission

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api", tags=["protocol"])

#: Ports OneBot protocol ends actually listen on, most likely first. 3001 is NapCat's
#: default WebSocket server, 6099 its WebUI (so "installed, not logged in"), the rest are
#: Lagrange / go-cqhttp / older NapCat conventions and the adapter probes' own defaults.
CANDIDATE_PORTS: tuple[int, ...] = (3001, 6099, 6700, 8080, 6199, 3000)

#: Hard cap even when the caller passes ?ports=. Six candidates plus saved adapters is
#: already more than any real machine has; more than this is a scan, not a lookup.
MAX_PORTS = 16

#: Loopback handshakes either complete in well under a second or the port is not speaking
#: OneBot. Long timeouts here would make the button feel broken while nothing is wrong.
OPEN_TIMEOUT = 1.5
REPLY_TIMEOUT = 2.0
HTTP_TIMEOUT = 1.5


def _saved_ports() -> list[int]:
    """Ports the operator's own adapters point at — a hint, and the fastest thing to check."""
    ports: list[int] = []
    try:
        document = config_write.read_document(settings.adapters_file)
    except Exception:  # unreadable config is not this endpoint's problem to report
        return ports
    for entry in document.get("adapters") or []:
        if not isinstance(entry, dict):
            continue
        raw = entry.get("port")
        try:
            if raw is not None:
                ports.append(int(str(raw)))
        except ValueError:
            continue
        url = str(entry.get("ws_url") or "")
        if url.rsplit(":", 1)[-1].isdigit():
            ports.append(int(url.rsplit(":", 1)[-1]))
    return ports


def _http_alive(port: int) -> dict[str, Any] | None:
    """Any HTTP answer means "a server exists here", which is all this needs to say.

    The body is never read: a NapCat WebUI page is large, and its content is not the point —
    the point is that something is listening and speaking HTTP.
    """
    try:
        # trust_env=False is load-bearing: with a system proxy configured (common on
        # Windows and on developer machines), httpx routes the loopback request through it,
        # the proxy answers 502 for a closed port, and every closed port is then reported as
        # "something is listening". A LOCALHOST probe must never consult proxy settings.
        response = httpx.get(
            f"http://127.0.0.1:{port}/",
            timeout=HTTP_TIMEOUT,
            follow_redirects=False,
            trust_env=False,
        )
    except Exception:
        return None
    return {"status_code": response.status_code}


async def _classify(port: int, token_for: dict[int, str]) -> dict[str, Any]:
    entry: dict[str, Any] = {"port": port, "kind": "closed"}
    probe = await probe_forward(
        f"ws://127.0.0.1:{port}",
        token=token_for.get(port, ""),
        open_timeout=OPEN_TIMEOUT,
        reply_timeout=REPLY_TIMEOUT,
    )
    if probe.get("state") == "handshake_ok":
        entry.update(
            kind="onebot",
            ok=True,
            account=str(probe.get("detail", "")).split("nickname=")[0].replace("user_id=", "").strip(),
            detail=probe.get("detail", ""),
            ws_url=f"ws://127.0.0.1:{port}",
        )
        return entry

    http = await asyncio.to_thread(_http_alive, port)
    if http is not None:
        entry.update(kind="http", status_code=http["status_code"])
        # NapCat's WebUI lives on 6099. Naming it turns "there is an HTTP server" into
        # "NapCat is installed and waiting for you to log in", which is the actionable fact.
        if port == 6099:
            entry["hint"] = "napcat_webui"
        return entry

    if probe.get("state") == "unauthorized":
        # A WS server that refused our handshake is still a WS server.
        entry.update(kind="onebot_locked", status_code=probe.get("status_code"))
        return entry

    return entry


async def scan_ports(ports: list[int], token_for: dict[int, str] | None = None) -> list[dict[str, Any]]:
    """Public for tests: classify each port, best answer first."""
    token_for = token_for or {}
    unique: list[int] = []
    for port in ports:
        if 0 < port < 65536 and port not in unique:
            unique.append(port)
    results = await asyncio.gather(*(_classify(port, token_for) for port in unique[:MAX_PORTS]))
    order = {"onebot": 0, "onebot_locked": 1, "http": 2, "closed": 3}
    return sorted(results, key=lambda item: (order.get(item["kind"], 9), item["port"]))


@router.get("/protocol/scan")
async def scan(
    request: Request,
    auth: dict[str, Any] = Depends(require_api_auth),
    ports: str = Query("", description="comma separated; defaults to the known ports"),
) -> dict[str, Any]:
    """Which of the known local ports is a logged-in OneBot, a WebUI, or nothing.

    Writes nothing. Returns a ``suggestion`` the panel can apply in one click, because the
    whole purpose is that the operator should not have to retype what was just discovered.
    """
    _require_permission(auth, request, Permission.MANAGE_CONFIG)
    _enforce_rate(auth, request)

    requested: list[int] = []
    if ports.strip():
        for chunk in ports.split(","):
            chunk = chunk.strip()
            if not chunk:
                continue
            if not chunk.isdigit():
                raise HTTPException(status_code=400, detail="ports 只能是逗号分隔的数字")
            requested.append(int(chunk))
        if len(requested) > MAX_PORTS:
            raise HTTPException(status_code=400, detail=f"一次最多 {MAX_PORTS} 个端口")

    candidates = requested or list(dict.fromkeys([*_saved_ports(), *CANDIDATE_PORTS]))
    results = await scan_ports(candidates)

    found = next((item for item in results if item["kind"] == "onebot"), None)
    suggestion: dict[str, Any] | None = None
    if found:
        suggestion = {
            "kind": "onebot11",
            "mode": "forward",
            "ws_url": found["ws_url"],
            "account_id": found.get("account") or "",
        }

    _audit(
        _caller_label(request),
        "allow",
        "protocol_scan",
        [f"port:{item['port']}={item['kind']}" for item in results],
    )
    logger.info("protocol scan: %s", {item["port"]: item["kind"] for item in results})
    return {"scanned": len(results), "results": results, "suggestion": suggestion}
