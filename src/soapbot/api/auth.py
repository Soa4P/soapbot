"""Authentication for the management API.

Two ways in, and only two:

1. **A bearer token** obtained from ``POST /api/auth/login`` using the bootstrap
   token. This is the only path that works from another machine, and the only one
   that should exist once a reverse proxy is in front of the service.
2. **A loopback client with no token**, kept for local development and for the
   single-operator case where the WebUI is opened on the same host.

The second path is deliberately narrow rather than absent: an operator who starts the
service and opens ``http://127.0.0.1:6185`` should not have to read a log to find a
token before the dashboard renders anything. It is *not* a security boundary — a
reverse proxy makes remote requests genuinely arrive from loopback, which is why it is
paired with an Origin check (see ``_reject_cross_site``) and why the docs say to set
``SOAPBOT_INIT_TOKEN`` and go through login on any exposed deployment.

Login is rate limited: the bootstrap token is short, high-value, and the endpoint is
reachable without any credential at all.
"""

from __future__ import annotations

import logging
from typing import Any
from urllib.parse import urlsplit

from fastapi import APIRouter, HTTPException, Request
from pydantic import BaseModel, Field

from soapbot.security.audit import get_audit_log
from soapbot.security.ratelimit import SlidingWindowLimiter
from soapbot.security.tokens import BootstrapToken, TokenError, TokenService

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/api/auth", tags=["auth"])

_LOOPBACK_HOSTS = frozenset({"127.0.0.1", "::1", "localhost", "testclient", ""})

_token_service: TokenService | None = None
_bootstrap: BootstrapToken | None = None

def _new_login_limiter() -> SlidingWindowLimiter:
    return SlidingWindowLimiter(limit=5, window_seconds=300.0)


_login_limiter = _new_login_limiter()
"""Five attempts per five minutes per client address.

A bootstrap token is ~32 characters of base64url; the limit is not what makes guessing
infeasible, but it is what stops a credential-stuffing script from turning the log
into noise while the real operator is trying to log in.
"""


def configure_auth(*, service: TokenService | None, bootstrap: BootstrapToken | None) -> None:
    """Install the process-wide auth objects (called from the app lifespan)."""
    global _token_service, _bootstrap, _login_limiter
    _token_service = service
    _bootstrap = bootstrap
    # A fresh bootstrap token means a fresh login budget: carrying a previous app
    # instance's failed attempts into this one would lock out the operator for five
    # minutes after a restart, which is the opposite of what the limit is for.
    _login_limiter = _new_login_limiter()


def get_token_service() -> TokenService | None:
    return _token_service


def get_bootstrap() -> BootstrapToken | None:
    return _bootstrap


def reset_auth() -> None:
    """Test seam: forget the installed objects and any login throttling."""
    global _token_service, _bootstrap, _login_limiter
    _token_service = None
    _bootstrap = None
    _login_limiter = _new_login_limiter()


def _client_host(request: Request) -> str:
    client = request.client
    return (client.host if client else "") or ""


def is_loopback(request: Request) -> bool:
    return _client_host(request) in _LOOPBACK_HOSTS


def _bearer(request: Request) -> str:
    header = request.headers.get("Authorization", "") or ""
    if header.lower().startswith("bearer "):
        return header[7:].strip()
    return ""


_MUTATING = frozenset({"POST", "PUT", "PATCH", "DELETE"})


def _reject_cross_site(request: Request) -> None:
    """Refuse unauthenticated state changes triggered by a page on another site.

    Loopback-only access is not the same as same-origin access. A page at
    ``evil.example`` can issue a form POST to ``http://127.0.0.1:6185/api/plugins/x/load``
    and the request arrives from loopback with no CORS preflight, because a plain form
    submission is not subject to one. Requiring a same-host ``Origin`` closes that.

    Only applies to requests that carry no bearer token — a token is not attached by a
    browser automatically, so a cross-site page cannot supply one.
    """
    if request.method not in _MUTATING:
        return
    origin = request.headers.get("Origin", "") or ""
    if not origin:
        # Non-browser clients (curl, the test client, the CLI) send no Origin. Allowing
        # them is the point of the loopback path.
        return
    host = urlsplit(origin).hostname or ""
    if host not in _LOOPBACK_HOSTS:
        logger.warning("blocked cross-site API call origin=%s path=%s", origin, request.url.path)
        raise HTTPException(status_code=403, detail="cross-site request refused")


def authenticate(request: Request) -> dict[str, Any]:
    """Authorise a request, or raise ``HTTPException``.

    Synchronous so it can be called from plain helper functions as well as from a
    FastAPI dependency — the plugin router calls its check inline inside each handler,
    and converting every call site to an ``await`` would be churn with no benefit.
    Decoding an HS256 token is CPU-only, so there is nothing to await.
    """
    token = _bearer(request)
    if token:
        service = _token_service
        if service is None:
            raise HTTPException(status_code=503, detail="auth is not initialised")
        try:
            claims = service.verify(token)
        except TokenError as exc:
            get_audit_log().record(
                kind="login",
                action="api_token",
                outcome="deny",
                detail=f"{exc} from={_client_host(request)}",
            )
            raise HTTPException(
                status_code=401,
                detail="invalid or expired token",
                headers={"WWW-Authenticate": "Bearer"},
            ) from exc
        request.state.claims = claims
        request.state.auth_mode = "token"
        return {
            "mode": "token",
            "subject": claims.subject,
            "role": claims.role,
            "expires_at": claims.expires_at,
        }

    if not is_loopback(request):
        get_audit_log().record(
            kind="authz",
            action="api_access",
            outcome="deny",
            detail=f"unauthenticated from={_client_host(request)} path={request.url.path}",
        )
        raise HTTPException(
            status_code=401,
            detail="authentication required",
            headers={"WWW-Authenticate": "Bearer"},
        )

    _reject_cross_site(request)
    request.state.auth_mode = "loopback"
    return {"mode": "loopback", "subject": "", "role": "owner", "expires_at": 0}


async def require_api_auth(request: Request) -> dict[str, Any]:
    """FastAPI dependency wrapper around :func:`authenticate`."""
    return authenticate(request)


# ----------------------------------------------------------------- endpoint
class LoginRequest(BaseModel):
    init_token: str = Field(..., min_length=1, max_length=512)
    """The bootstrap token from ``SOAPBOT_INIT_TOKEN`` or the startup log."""


@router.post("/login")
async def login(payload: LoginRequest, request: Request) -> dict:
    """Exchange the one-time bootstrap token for an API token.

    Returns 401 for both "wrong token" and "already used" — distinguishing them would
    tell an attacker whether the operator has already logged in, and tells a legitimate
    operator nothing they cannot learn from the startup log.
    """
    host = _client_host(request)
    limit = _login_limiter.check(host or "unknown")
    if limit.limited:
        get_audit_log().record(
            kind="login",
            action="bootstrap",
            outcome="deny",
            detail=f"rate limited from={host}",
        )
        raise HTTPException(
            status_code=429,
            detail="too many login attempts",
            headers={"Retry-After": str(int(limit.retry_after) + 1)},
        )

    bootstrap = _bootstrap
    service = _token_service
    if bootstrap is None or service is None:
        raise HTTPException(status_code=503, detail="auth is not initialised")

    if not bootstrap.redeem(payload.init_token):
        get_audit_log().record(
            kind="login",
            action="bootstrap",
            outcome="deny",
            detail=f"bad or reused init token from={host}",
        )
        raise HTTPException(status_code=401, detail="invalid bootstrap token")

    token, claims = service.issue("operator")
    get_audit_log().record(
        kind="login",
        action="bootstrap",
        outcome="allow",
        detail=f"issued operator token from={host} ttl={service.ttl_seconds}s",
    )
    _login_limiter.reset(host or "unknown")
    return {
        "access_token": token,
        "token_type": "bearer",
        "expires_in": service.ttl_seconds,
        "expires_at": claims.expires_at,
        "role": claims.role,
    }


@router.post("/refresh")
async def refresh(request: Request) -> dict:
    """Re-issue a token from a still-valid one.

    Requires a bearer token explicitly: refreshing on the loopback fallback would let
    any local process mint a long-lived credential without ever knowing the bootstrap
    secret.
    """
    token = _bearer(request)
    service = _token_service
    if service is None:
        raise HTTPException(status_code=503, detail="auth is not initialised")
    if not token:
        raise HTTPException(status_code=401, detail="a bearer token is required to refresh")
    try:
        claims = service.verify(token)
    except TokenError as exc:
        raise HTTPException(status_code=401, detail="invalid or expired token") from exc

    new_token, new_claims = service.issue(claims.subject, role=claims.role)
    get_audit_log().record(
        kind="login",
        action="refresh",
        outcome="allow",
        detail=f"subject={claims.subject} from={_client_host(request)}",
    )
    return {
        "access_token": new_token,
        "token_type": "bearer",
        "expires_in": service.ttl_seconds,
        "expires_at": new_claims.expires_at,
        "role": new_claims.role,
    }


@router.get("/status")
async def auth_status(request: Request) -> dict:
    """Whether the caller is authenticated, and which method is in force.

    Unauthenticated on purpose: the login dialog needs to know whether a token is
    required before it can decide what to render, and this endpoint reveals nothing
    beyond "a token is or is not configured".
    """
    token = _bearer(request)
    mode = "none"
    subject = ""
    expires_at = 0
    if token and _token_service is not None:
        try:
            claims = _token_service.verify(token)
            mode, subject, expires_at = "token", claims.subject, claims.expires_at
        except TokenError:
            mode = "invalid"
    elif is_loopback(request):
        mode = "loopback"

    bootstrap = _bootstrap
    return {
        "mode": mode,
        "subject": subject,
        "expires_at": expires_at,
        "loopback": is_loopback(request),
        "login_available": bool(bootstrap is not None and not bootstrap.consumed),
        "init_token_generated": bool(bootstrap is not None and bootstrap.generated),
        "ttl_seconds": _token_service.ttl_seconds if _token_service else 0,
    }
