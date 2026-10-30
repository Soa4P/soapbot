"""Connectivity probes: "is this address actually reachable?" — asked from the panel.

Why this exists
---------------
Every deployment failure in this project's history had the same shape: configuration was
saved, the panel showed a green row, and the bot still could not answer — because the
``base_url`` pointed at a host that did not resolve, the ``/v1`` prefix was missing, or
NapCat was never listening. The operator's only recourse was SSH plus ``curl``, which is
exactly the thing the panel is supposed to remove.

So there are two probes, and they answer two deliberately different questions:

* **provider** — ``GET {base_url}/models`` with **no credential**. A 401 is a pass: a
  server that rejects you is a server that answered, and never sending the key means a
  screenshot, a log line or a bug report cannot contain one. Shares
  :func:`soapbot.security.posture.probe_endpoint` with ``doctor --probe`` so the browser
  and the CLI cannot disagree.
* **adapter** — a full WebSocket handshake plus one ``get_login_info``. A handshake alone
  does not prove the far side is OneBot; a ``user_id``/``nickname`` answer does. Reverse
  mode is the opposite problem: *we* are the listener, so nothing can be dialled. What is
  knowable is whether the port can be bound — free means "not listening yet", ``EADDRINUSE``
  means "something is already there, probably the running adapter".

The security trade-off, stated rather than hidden
-------------------------------------------------
These endpoints take a URL from a user and make the server connect to it, which is the
textbook SSRF shape. Private and loopback addresses are **not** blocked, on purpose:
``http://127.0.0.1:11434/v1`` is Ollama and ``ws://127.0.0.1:3001`` is a same-host
NapCat — the two most common real deployments in this project. Blocking them would make
the feature useless for its main audience. The risk is held down by three properties
instead: ``MANAGE_CONFIG`` (ADMIN and above, loopback callers are owners), a sliding
window of 30 probes per minute per caller so the panel cannot be used as a port scanner,
and the provider probe sending no credential that could be captured by a redirect.

Nothing here writes configuration. A probe is a read of the network, and the audit entry
records field names only — never a URL path, never a token.
"""

from __future__ import annotations

import asyncio
import contextlib
import json
import logging
import socket
import time
from typing import Any
from urllib.parse import urlsplit

from fastapi import APIRouter, Depends, HTTPException, Request
from pydantic import BaseModel, Field

from soapbot.api.auth import require_api_auth
from soapbot.api.config_write import _audit, _caller_label, _require_permission
from soapbot.config import settings
from soapbot.core import config_write
from soapbot.core.config_files import ConfigError, resolve_secret
from soapbot.security.posture import probe_endpoint
from soapbot.security.principal import Permission
from soapbot.security.ratelimit import SlidingWindowLimiter

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/config", tags=["config"])

#: 30 per minute is generous for a human clicking "test" on a handful of rows, and far
#: too slow to walk an internal /24 looking for open ports.
PROBE_LIMIT = 30
PROBE_WINDOW_SECONDS = 60.0
_limiter = SlidingWindowLimiter(limit=PROBE_LIMIT, window_seconds=PROBE_WINDOW_SECONDS)

_HTTP_SCHEMES = frozenset({"http", "https"})
_WS_SCHEMES = frozenset({"ws", "wss"})

#: The handshake is the slow part on a long route (measured 4.0 s of TCP to DeepSeek);
#: 8 s keeps a working link from being reported as dead without hanging the page.
WS_OPEN_TIMEOUT = 8.0
#: One request/response after the handshake. A NapCat that is still starting answers
#: within a second; five is already generous and still keeps the button responsive.
WS_REPLY_TIMEOUT = 5.0
WS_CLOSE_TIMEOUT = 2.0


class ProviderProbeRequest(BaseModel):
    """The draft row, not the saved one: an operator must be able to test before saving."""

    id: str = ""
    base_url: str = Field(..., min_length=1, max_length=2048)
    timeout: float = Field(default=15.0, gt=0, le=60)


class AdapterProbeRequest(BaseModel):
    kind: str = "onebot11"
    mode: str = "forward"
    ws_url: str = ""
    host: str = ""
    port: int | None = Field(default=None, ge=0, le=65535)
    access_token: str = ""


# --------------------------------------------------------------------- providers
async def probe_provider(base_url: str, *, timeout: float = 15.0) -> dict[str, Any]:
    """Thin alias so the route and the tests share one name.

    Kept as a function rather than calling ``probe_endpoint`` inline for one reason: a
    test that monkeypatches this cannot accidentally hit the network, and the route's
    contract stays the thing under test.
    """
    return await probe_endpoint(base_url, timeout=timeout)


def _check_scheme(url: str, allowed: frozenset[str], *, field: str) -> str:
    """Reject anything that is not a plain HTTP(S)/WS(S) URL with a host.

    ``file:``, ``gopher:`` and bare host names are refused before the socket is touched:
    the allow-list is the cheapest half of the SSRF answer, and it is the half that needs
    no judgement about which private address is "fine".
    """
    text = str(url or "").strip()
    if not text:
        raise HTTPException(status_code=400, detail=f"{field} 不能为空")
    split = urlsplit(text)
    if split.scheme.lower() not in allowed:
        raise HTTPException(
            status_code=400,
            detail=f"{field} 只支持 {'/'.join(sorted(allowed))} 协议",
        )
    if not split.netloc:
        raise HTTPException(status_code=400, detail=f"{field} 缺少主机名")
    return text


@router.post("/providers/test")
async def test_provider(
    payload: ProviderProbeRequest,
    request: Request,
    auth: dict[str, Any] = Depends(require_api_auth),
) -> dict[str, Any]:
    """One ``/models`` request against the *draft* ``base_url``. Writes nothing."""
    _require_permission(auth, request, Permission.MANAGE_CONFIG)
    base_url = _check_scheme(payload.base_url, _HTTP_SCHEMES, field="base_url")
    _enforce_rate(auth, request)

    result = await probe_provider(base_url, timeout=payload.timeout)
    logger.info(
        "probe provider id=%s host=%s ok=%s status=%s ms=%s",
        payload.id or "-",
        result.get("target") or "-",
        result.get("ok"),
        result.get("status_code"),
        result.get("elapsed_ms"),
    )
    # Field names only. The audit log is exported to people who may not see the config.
    _audit(_caller_label(request), "allow" if result.get("ok") else "deny", "probe_provider", [])
    return result


# ---------------------------------------------------------------------- adapters
def _stored_adapter(kind: str) -> dict[str, Any]:
    """The saved entry for ``kind``, used only to recover a token the form masked.

    Without this, testing a saved row would always fail: the read endpoint returns
    ``********`` for a literal token, and sending the mask as a bearer token produces a
    401 that says "your token is wrong" about a token that is fine.
    """
    if not kind:
        return {}
    try:
        document = config_write.read_document(settings.adapters_file)
    except (ConfigError, OSError):
        return {}
    for entry in document.get("adapters") or []:
        if isinstance(entry, dict) and str(entry.get("kind") or "") == kind:
            return entry
    return {}


def _effective_token(raw: str, stored: dict[str, Any]) -> tuple[str, str]:
    """Resolve the token to send, and a problem string when it cannot be resolved.

    Returns the real value (never echoed to the client) or ``""`` when there is simply no
    token configured — which is a valid state for forward mode against a local NapCat.
    """
    value = str(raw or "").strip()
    if not value or value == config_write.MASK:
        value = str(stored.get("access_token") or stored.get("token") or "").strip()
    if not value or value == config_write.MASK:
        return "", ""
    try:
        return resolve_secret(value, field_name="adapters.access_token"), ""
    except ConfigError as exc:
        return "", str(exc)


def _blank_adapter_result(mode: str, target: str) -> dict[str, Any]:
    return {
        "ok": False,
        "mode": mode,
        "target": target,
        "state": "error",
        "status_code": None,
        "elapsed_ms": 0,
        "error": "",
        "hint": "",
        "detail": "",
        "credential_sent": False,
    }


async def probe_forward(
    url: str,
    *,
    token: str = "",
    open_timeout: float = WS_OPEN_TIMEOUT,
    reply_timeout: float = WS_REPLY_TIMEOUT,
) -> dict[str, Any]:
    """Handshake, then ask who is on the other end.

    A completed handshake proves a WebSocket server exists; it does not prove the server
    speaks OneBot. ``get_login_info`` is the cheapest way to tell those apart, and it is
    the one call every OneBot v11 implementation answers.
    """
    from websockets.asyncio.client import connect as ws_connect
    from websockets.exceptions import InvalidStatus

    result = _blank_adapter_result("forward", url)
    result["credential_sent"] = bool(token)
    headers = {"Authorization": f"Bearer {token}"} if token else {}

    started = time.monotonic()
    # Two phases, two meanings. Folding them into one try made a closed port report
    # "connected but not OneBot" (a connect timeout arrives as TimeoutError), which sends
    # someone to audit the protocol side when the port was simply shut — the exact
    # misdiagnosis this button exists to prevent.
    try:
        ws = await ws_connect(
            url,
            additional_headers=headers,
            open_timeout=open_timeout,
            close_timeout=WS_CLOSE_TIMEOUT,
            max_size=1024 * 1024,
        )
    except InvalidStatus as exc:
        status = getattr(getattr(exc, "response", None), "status_code", None)
        result["status_code"] = status
        result["state"] = "unauthorized"
        result["error"] = f"HTTP {status}" if status else "handshake rejected"
        result["hint"] = "握手被拒绝：检查 access_token 是否与协议端一致"
    except Exception as exc:
        result["state"] = "unreachable"
        result["error"] = f"{type(exc).__name__}: {exc}"
        result["hint"] = "连不上：确认协议端已启动、端口正确、防火墙放行"
    else:
        result["status_code"] = 101
        try:
            await ws.send(json.dumps({"action": "get_login_info", "params": {}, "echo": "probe"}))
            raw = await asyncio.wait_for(ws.recv(), timeout=reply_timeout)
        # `asyncio.TimeoutError` *is* `TimeoutError` on 3.11+, and `wait_for` raises the
        # builtin; aliasing both here would only hide which one is meant.
        except TimeoutError:
            result["state"] = "not_onebot"
            result["error"] = "等待 get_login_info 回复超时"
            result["hint"] = "端口能连上，但对面没有按 OneBot 应答：确认这个端口是 OneBot 的 WS 端口"
        except Exception as exc:
            result["state"] = "not_onebot"
            result["error"] = f"{type(exc).__name__}: {exc}"
            result["hint"] = "握手成功但读不到回复：确认这个端口是 OneBot 的 WS 端口"
        else:
            _read_login_info(result, raw)
        finally:
            # Closing a probe must never raise: the answer is already in `result`, and an
            # exception here would replace a useful report with a traceback.
            with contextlib.suppress(Exception):
                await ws.close()

    result["elapsed_ms"] = int((time.monotonic() - started) * 1000)
    return result


def _read_login_info(result: dict[str, Any], raw: Any) -> None:
    """Fill in ``state``/``detail`` from the OneBot reply. Never echoes the raw body.

    The raw body is exactly the kind of thing that ends up in a ticket with a token in
    it, so only two fields survive: the account number and the nickname.
    """
    try:
        body = json.loads(raw if isinstance(raw, str) else raw.decode("utf-8", "replace"))
    except (ValueError, AttributeError):
        result["state"] = "not_onebot"
        result["error"] = "回复不是 JSON"
        result["hint"] = "对面是 WebSocket，但不像 OneBot：确认端口选的是 OneBot WS"
        return

    if not isinstance(body, dict):
        result["state"] = "not_onebot"
        result["error"] = "回复不是 OneBot 对象"
        return

    if str(body.get("status") or "").lower() == "failed" or body.get("retcode") not in (0, None, "0"):
        result["state"] = "not_onebot"
        result["retcode"] = body.get("retcode")
        result["error"] = f"retcode={body.get('retcode')}"
        result["hint"] = "对面拒绝了 get_login_info：多半不是 OneBot 端口"
        return

    payload = body.get("data")
    data: dict[str, Any] = payload if isinstance(payload, dict) else {}
    user_id = data.get("user_id")
    nickname = str(data.get("nickname") or "")
    result["ok"] = True
    result["state"] = "handshake_ok"
    result["detail"] = f"user_id={user_id} nickname={nickname}"[:200]
    result["hint"] = "握手成功且 OneBot 有应答：这条接入是通的"


def probe_bind(host: str, port: int) -> dict[str, Any]:
    """Can we bind ``host:port`` right now?

    Reverse mode cannot be probed from the inside: the peer dials *us*. What is knowable
    is the port. A successful bind (immediately closed) means nothing is listening yet;
    ``EADDRINUSE`` means something is — almost certainly the running adapter, which is a
    reason for relief, not an error.

    ``SO_REUSEADDR`` is deliberately **not** set: on Windows it lets a second socket bind
    a port already in use, which would report "free" for the one case this check exists
    to detect.
    """
    result = _blank_adapter_result("reverse", f"{host}:{port}")
    family = socket.AF_INET6 if ":" in host else socket.AF_INET
    started = time.monotonic()
    sock = socket.socket(family, socket.SOCK_STREAM)
    try:
        sock.bind((host, port))
    except OSError as exc:
        in_use = getattr(exc, "errno", None) in (98, 48, 10048)  # Linux/macOS/Windows
        result["state"] = "in_use" if in_use else "error"
        result["error"] = f"{type(exc).__name__}: {exc}"
        if in_use:
            # Not a failure: an adapter that is already listening is the healthy state.
            result["ok"] = True
            result["hint"] = "端口已被占用：可能适配器已在监听（这正是期望状态）"
        else:
            result["hint"] = "无法绑定该端口：检查 host 是否是本机地址、端口是否在允许范围内"
    else:
        result["ok"] = True
        result["state"] = "free"
        result["hint"] = "端口空闲：适配器尚未监听。对方是否连进来，这里测不到"
    finally:
        sock.close()
    result["elapsed_ms"] = int((time.monotonic() - started) * 1000)
    return result


async def probe_adapter(payload: AdapterProbeRequest) -> dict[str, Any]:
    """Dispatch on ``mode`` and normalise the outcome."""
    mode = str(payload.mode or "forward").strip().lower()
    if mode == "reverse":
        host = str(payload.host or "").strip() or "127.0.0.1"
        port = payload.port or 6700
        return await asyncio.to_thread(probe_bind, host, port)

    stored = _stored_adapter(payload.kind)
    url = str(payload.ws_url or "").strip()
    if not url:
        # A reverse row switched to forward has no ws_url yet; fall back to what is saved.
        url = str(stored.get("ws_url") or "").strip()
    url = _check_scheme(url, _WS_SCHEMES, field="ws_url")

    token, problem = _effective_token(payload.access_token, stored)
    if problem:
        result = _blank_adapter_result("forward", url)
        result["error"] = problem
        result["hint"] = "令牌引用无法解析：确认环境变量已设置或密文可解密"
        return result
    return await probe_forward(url, token=token)


@router.post("/adapters/test")
async def test_adapter(
    payload: AdapterProbeRequest,
    request: Request,
    auth: dict[str, Any] = Depends(require_api_auth),
) -> dict[str, Any]:
    """Probe a *draft* adapter row: handshake + ``get_login_info``, or port availability."""
    _require_permission(auth, request, Permission.MANAGE_CONFIG)
    if str(payload.mode or "").strip().lower() not in ("forward", "reverse"):
        raise HTTPException(status_code=400, detail="mode 只能是 forward 或 reverse")
    _enforce_rate(auth, request)

    result = await probe_adapter(payload)
    logger.info(
        "probe adapter kind=%s mode=%s host=%s ok=%s state=%s ms=%s",
        payload.kind or "-",
        result.get("mode"),
        result.get("target") or "-",
        result.get("ok"),
        result.get("state"),
        result.get("elapsed_ms"),
    )
    _audit(_caller_label(request), "allow" if result.get("ok") else "deny", "probe_adapter", [])
    return result


# --------------------------------------------------------------------- rate limit
def _caller_key(auth: dict[str, Any], request: Request) -> str:
    """Limit per caller, not globally: one operator probing must not lock out another."""
    host = request.client.host if request.client else "-"
    subject = str(auth.get("subject") or "")
    return f"{host}:{subject}" if subject else host


def _enforce_rate(auth: dict[str, Any], request: Request) -> None:
    key = _caller_key(auth, request)
    verdict = _limiter.check(key)
    if verdict.allowed:
        return
    _audit(_caller_label(request), "deny", "probe_rate_limited", [])
    raise HTTPException(
        status_code=429,
        detail=f"探测过于频繁：每分钟最多 {PROBE_LIMIT} 次，请 {int(verdict.retry_after) + 1} 秒后重试",
    )
