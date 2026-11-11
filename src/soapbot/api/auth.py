"""Authentication for the management API.

The browser uses an ``HttpOnly`` session cookie. A bearer token remains available for
scripts and the CLI, which cannot rely on a browser cookie jar. Both carry the same
signed token, so revocation and expiry work identically on either path.

A loopback client with no credential may still *read*. It may not change anything
once ``strict_loopback_auth`` is on (the default). That distinction matters: a
reverse proxy in front of the service makes remote requests genuinely arrive from
loopback, so "came from 127.0.0.1" was never proof of being the operator.

Cookie-authenticated writes also need a same-origin ``Origin`` and a CSRF header
matching a separate readable cookie. A browser attaches cookies automatically; it
cannot attach the header from another origin without a preflight we do not allow.
Bearer-authenticated writes are exempt because a cross-site page cannot supply a
bearer token in the first place.

Login is rate limited: the bootstrap token is short, high-value, and the endpoint is
reachable without any credential at all.
"""

from __future__ import annotations

import hmac
import logging
import secrets
from dataclasses import dataclass, field
from typing import Any
from urllib.parse import urlsplit

from fastapi import APIRouter, Depends, HTTPException, Request, Response
from pydantic import BaseModel, Field

from soapbot.config import settings
from soapbot.security.audit import get_audit_log
from soapbot.security.ratelimit import SlidingWindowLimiter
from soapbot.security.tokens import (
    BOOTSTRAP_FILE,
    BootstrapToken,
    TokenError,
    TokenService,
)

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/api/auth", tags=["auth"])

_LOOPBACK_HOSTS = frozenset({"127.0.0.1", "::1", "localhost", "testclient", ""})

SESSION_COOKIE = "soapbot_session"
CSRF_COOKIE = "soapbot_csrf"
CSRF_HEADER = "X-CSRF-Token"
"""The session cookie is unreadable from JavaScript; the CSRF cookie is deliberately
readable, because the double-submit check needs the page to echo its value in a
header. Two values, not one: echoing the session cookie itself would put the
credential back into script-reachable space."""

def _new_login_limiter() -> SlidingWindowLimiter:
    """Five attempts per five minutes per client address.

    A bootstrap token is ~32 characters of base64url; the limit is not what makes guessing
    infeasible, but it is what stops a credential-stuffing script from turning the log
    into noise while the real operator is trying to log in.
    """
    return SlidingWindowLimiter(limit=5, window_seconds=300.0)


@dataclass
class AuthState:
    """The auth objects one app instance owns.

    These used to be module-level globals. That made "which token service is this
    request using" a question about import order and the last writer, not about the
    app: two ``create_app()`` calls in one process (a test fixture plus the app under
    test, or a panel process that restarts its own runtime) silently shared one token
    service, one bootstrap credential and one login budget. A revoked token could come
    back to life because another instance reconfigured the globals.

    Holding them on ``app.state`` keeps the blast radius of a misconfiguration inside
    the instance that owns it, and makes the object lifetime explicit: it is created in
    the lifespan and dies with the app.
    """

    token_service: TokenService | None = None
    bootstrap: BootstrapToken | None = None
    #: The store the token service consults. Held here too so the endpoints can revoke
    #: without reaching through the service's private state.
    revocations: Any = None
    login_limiter: SlidingWindowLimiter = field(default_factory=_new_login_limiter)

    #: A fresh bootstrap token means a fresh login budget: carrying a previous app
    #: instance's failed attempts into this one would lock out the operator for five
    #: minutes after a restart, which is the opposite of what the limit is for.
    def reset_login_budget(self) -> None:
        self.login_limiter = _new_login_limiter()

    def clear(self) -> None:
        """Forget every installed object, including any login throttling."""
        self.token_service = None
        self.bootstrap = None
        self.revocations = None
        self.reset_login_budget()


_STATE_KEY = "soapbot_auth_state"
_FALLBACK_STATE = AuthState()
"""Used when an endpoint is reached without a running app.

Two legitimate cases, both of which want "auth is not initialised" rather than a
traceback: a unit test that calls a route function directly, and an ASGI server that
never ran the lifespan (a misconfiguration worth surfacing as 503). Keeping a single
process-wide fallback for those is deliberately *not* the old behaviour — nothing
installs objects into it, so no instance can observe another's credentials.
"""


def _auth_state(request: Request | None = None) -> AuthState:
    if request is None:
        return _FALLBACK_STATE
    app = getattr(request, "app", None)
    state = getattr(app, "state", None)
    if state is None:
        return _FALLBACK_STATE
    existing = getattr(state, _STATE_KEY, None)
    if existing is None:
        existing = AuthState()
        setattr(state, _STATE_KEY, existing)
    return existing


def configure_auth(
    *,
    service: TokenService | None,
    bootstrap: BootstrapToken | None,
    revocations: Any = None,
    app: Any = None,
    request: Request | None = None,
) -> AuthState:
    """Install the auth objects for one app instance (called from the app lifespan).

    ``app`` is passed explicitly by the lifespan. Tests that used to call this to set
    up a route function directly keep working: with no ``app`` and no ``request`` the
    objects land on the process fallback state, which is exactly what those call sites
    read back through the accessors below.
    """
    state = _state_for(app) if app is not None else _auth_state(request)
    state.token_service = service
    state.bootstrap = bootstrap
    state.revocations = revocations
    state.reset_login_budget()
    return state


def _state_for(app: Any) -> AuthState:
    state = getattr(app, "state", None)
    if state is None:
        return _FALLBACK_STATE
    existing = getattr(state, _STATE_KEY, None)
    if existing is None:
        existing = AuthState()
        setattr(state, _STATE_KEY, existing)
    return existing


def reset_auth(app: Any = None, request: Request | None = None) -> None:
    """Test seam: forget the installed objects and any login throttling.

    Scoped to one app when ``app`` is given; otherwise the process fallback, which is
    what tests that never build an app rely on.
    """
    state = _state_for(app) if app is not None else _auth_state(request)
    state.clear()


def get_token_service(request: Request | None = None) -> TokenService | None:
    return _auth_state(request).token_service


def get_bootstrap(request: Request | None = None) -> BootstrapToken | None:
    return _auth_state(request).bootstrap


def get_revocations(request: Request | None = None) -> Any:
    return _auth_state(request).revocations


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


def _cookie(request: Request) -> str:
    # ``getattr`` rather than a direct attribute read: several callers (and the
    # unit tests that pin the loopback rules) build a minimal request stand-in
    # without a cookie jar. A missing jar means "no cookie", not a crash.
    cookies = getattr(request, "cookies", None) or {}
    return cookies.get(SESSION_COOKIE, "") or ""


def _credential(request: Request) -> tuple[str, str]:
    """Return ``(token, carrier)``. A bearer header wins over the cookie.

    The header wins so a script can deliberately use a different identity from the
    one in its browser cookie jar, instead of getting a confusing mix of both.
    """
    bearer = _bearer(request)
    if bearer:
        return bearer, "token"
    cookie = _cookie(request)
    if cookie:
        return cookie, "cookie"
    return "", "none"


def _set_session(response: Response, token: str, ttl_seconds: int) -> None:
    response.set_cookie(
        SESSION_COOKIE,
        token,
        max_age=max(1, ttl_seconds),
        httponly=True,
        samesite="lax",
        secure=settings.cookie_secure,
        path="/",
    )
    # Readable on purpose. Rotated on every login so an old value cannot be
    # replayed against a new session.
    response.set_cookie(
        CSRF_COOKIE,
        secrets.token_urlsafe(24),
        max_age=max(1, ttl_seconds),
        httponly=False,
        samesite="lax",
        secure=settings.cookie_secure,
        path="/",
    )


def _clear_session(response: Response) -> None:
    response.delete_cookie(SESSION_COOKIE, path="/", httponly=True, samesite="lax")
    response.delete_cookie(CSRF_COOKIE, path="/", httponly=False, samesite="lax")


def _origin_allowed(request: Request) -> bool:
    """Reject a cross-site Origin, including opaque ones.

    ``Origin: null`` (a sandboxed iframe, or some file:// pages) used to pass
    because ``urlsplit("null").hostname`` is None and the empty string was in the
    loopback set. An opaque origin is not a loopback origin: it means we cannot
    tell where the request came from, which is a reason to refuse, not to trust.
    """
    origin = request.headers.get("Origin", "") or ""
    if not origin:
        # Non-browser clients (curl, TestClient, the CLI) send no Origin.
        return True
    host = urlsplit(origin).hostname or ""
    if not host:
        return False
    own_host = getattr(request.url, "hostname", "") or ""
    return host in _LOOPBACK_HOSTS or host == own_host


def _verify_csrf(request: Request) -> None:
    """Double-submit check for cookie-authenticated state changes."""
    if request.method not in _MUTATING:
        return
    if _bearer(request):
        # A cross-site page cannot attach a bearer header; no CSRF exposure here.
        return
    cookies = getattr(request, "cookies", None) or {}
    expected = cookies.get(CSRF_COOKIE, "") or ""
    supplied = request.headers.get(CSRF_HEADER, "") or ""
    if not expected or not supplied or not hmac.compare_digest(expected, supplied):
        raise HTTPException(status_code=403, detail="CSRF token missing or mismatched")
    if not _origin_allowed(request):
        logger.warning("blocked cross-origin cookie write origin=%s", request.headers.get("Origin"))
        raise HTTPException(status_code=403, detail="cross-site request refused")


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
    if not _origin_allowed(request):
        logger.warning(
            "blocked cross-site API call origin=%s path=%s",
            request.headers.get("Origin"),
            request.url.path,
        )
        raise HTTPException(status_code=403, detail="cross-site request refused")


def _loopback_role() -> str:
    """Read-only loopback is a viewer, not an operator, once strict mode is on."""
    return "member" if settings.strict_loopback_auth else "owner"


def authenticate(request: Request) -> dict[str, Any]:
    """Authorise a request, or raise ``HTTPException``.

    Synchronous so it can be called from plain helper functions as well as from a
    FastAPI dependency — the plugin router calls its check inline inside each handler,
    and converting every call site to an ``await`` would be churn with no benefit.
    Decoding an HS256 token is CPU-only, so there is nothing to await.
    """
    token, carrier = _credential(request)
    if token:
        _verify_csrf(request)
        service = _auth_state(request).token_service
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
        request.state.auth_mode = carrier
        return {
            "mode": "token",
            "carrier": carrier,
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
    if settings.strict_loopback_auth and request.method in _MUTATING:
        get_audit_log().record(
            kind="authz",
            action="loopback_write",
            outcome="deny",
            detail=f"method={request.method} path={request.url.path}",
        )
        raise HTTPException(
            status_code=401,
            detail="a credential is required to change state",
            headers={"WWW-Authenticate": "Bearer"},
        )
    request.state.auth_mode = "loopback"
    return {
        "mode": "loopback",
        "carrier": "loopback",
        "subject": "",
        "role": _loopback_role(),
        "expires_at": 0,
    }


async def require_api_auth(request: Request) -> dict[str, Any]:
    """FastAPI dependency wrapper around :func:`authenticate`."""
    return authenticate(request)


def require_role(minimum, *, require_credential: bool = False):
    """Build a dependency that authenticates and then checks an authority floor.

    Kept as a factory so a router can declare one floor for all its routes while a
    single handler can ask for a higher one. Authentication always happens first:
    a role check over an unauthenticated request would compare "anonymous" against
    a floor and leak which endpoints are more sensitive than others.
    """
    from soapbot.security.principal import Role

    async def _dep(
        request: Request, auth: dict[str, Any] = Depends(require_api_auth)
    ) -> dict[str, Any]:
        # ``require_api_auth`` is a nested dependency rather than a direct call so
        # FastAPI's dependency_overrides still work for tests that build a bare app
        # and supply a caller. Calling authenticate() here would ignore those
        # overrides and turn a role test into an "auth not initialised" 503.
        if require_credential and auth.get("mode") != "token":
            raise HTTPException(
                status_code=401,
                detail="a credential is required",
                headers={"WWW-Authenticate": "Bearer"},
            )
        raw = str(auth.get("role") or "anonymous").lower()
        try:
            role = Role(raw)
        except ValueError:
            role = Role.ANONYMOUS
        if role.rank < minimum.rank:
            get_audit_log().record(
                kind="authz",
                action="role_gate",
                outcome="deny",
                role=role.value,
                detail=f"requires={minimum.value} path={request.url.path}",
            )
            raise HTTPException(status_code=403, detail="insufficient role")
        return auth

    return _dep


# ----------------------------------------------------------------- endpoint
class LoginRequest(BaseModel):
    init_token: str = Field(..., min_length=1, max_length=512)
    """The bootstrap token from ``SOAPBOT_INIT_TOKEN`` or the startup log."""


@router.post("/login")
async def login(payload: LoginRequest, request: Request, response: Response) -> dict:
    """Exchange the one-time bootstrap token for an API token.

    Returns 401 for both "wrong token" and "already used" — distinguishing them would
    tell an attacker whether the operator has already logged in, and tells a legitimate
    operator nothing they cannot learn from the startup log.
    """
    # This endpoint sets cookies without having a session yet, so the CSRF
    # double-submit check cannot apply. Refuse a cross-site Origin instead.
    _reject_cross_site(request)
    host = _client_host(request)
    state = _auth_state(request)
    limit = state.login_limiter.check(host or "unknown")
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

    bootstrap = state.bootstrap
    service = state.token_service
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
    state.login_limiter.reset(host or "unknown")
    _set_session(response, token, service.ttl_seconds)
    # ``access_token`` stays in the body for scripts and the CLI, which cannot use a
    # browser cookie jar. The panel ignores it entirely: its only credential is the
    # HttpOnly cookie above. A browser-side XSS can read this one response, but it
    # cannot read the cookie, cannot replay it later, and cannot persist the token.
    return {
        "access_token": token,
        "token_type": "bearer",
        "expires_in": service.ttl_seconds,
        "expires_at": claims.expires_at,
        "role": claims.role,
    }


@router.post("/refresh")
async def refresh(
    request: Request, response: Response, _auth: dict[str, Any] = Depends(require_api_auth)
) -> dict:
    """Re-issue a token from a still-valid one.

    Requires an existing credential explicitly: refreshing on the loopback fallback
    would let any local process mint a long-lived token without ever knowing the
    bootstrap secret. A cookie-backed session gets a fresh cookie back.
    """
    token, carrier = _credential(request)
    state = _auth_state(request)
    service = state.token_service
    if service is None:
        raise HTTPException(status_code=503, detail="auth is not initialised")
    if not token:
        raise HTTPException(status_code=401, detail="a credential is required to refresh")
    try:
        claims = service.verify(token)
    except TokenError as exc:
        raise HTTPException(status_code=401, detail="invalid or expired token") from exc

    new_token, new_claims = service.issue(claims.subject, role=claims.role)
    # Issuing a fresh 72h token while leaving the old one valid for its full 72h made
    # refresh an unlimited extension: a stolen credential stayed useful for days after
    # the operator "refreshed" it. Rotate by revoking the jti we just consumed. The
    # new token is minted first so a revocation-file failure cannot lock the operator
    # out; that failure is reported instead of hidden.
    previous_revoked = False
    store = state.revocations
    if store is not None:
        try:
            store.revoke(claims.token_id, claims.expires_at)
            previous_revoked = True
        except OSError as exc:
            logger.warning("refresh could not revoke the previous jti: %s", exc)
    if carrier == "cookie":
        _set_session(response, new_token, service.ttl_seconds)
    get_audit_log().record(
        kind="login",
        action="refresh",
        outcome="allow",
        detail=(
            f"subject={claims.subject} from={_client_host(request)} "
            f"previous_revoked={previous_revoked}"
        ),
    )
    return {
        "access_token": new_token,
        "token_type": "bearer",
        "expires_in": service.ttl_seconds,
        "expires_at": new_claims.expires_at,
        "role": new_claims.role,
        "previous_credential_revoked": previous_revoked,
    }


@router.get("/status")
async def auth_status(request: Request) -> dict:
    """Whether the caller is authenticated, and which method is in force.

    Unauthenticated on purpose: the login dialog needs to know whether a token is
    required before it can decide what to render, and this endpoint reveals nothing
    beyond "a token is or is not configured".
    """
    token, _carrier = _credential(request)
    state = _auth_state(request)
    mode = "none"
    subject = ""
    expires_at = 0
    role = "anonymous"
    if token and state.token_service is not None:
        try:
            claims = state.token_service.verify(token)
            mode, subject, expires_at = "token", claims.subject, claims.expires_at
            role = claims.role
        except TokenError:
            mode = "invalid"
    elif is_loopback(request):
        mode = "loopback"
        role = _loopback_role()

    bootstrap = state.bootstrap
    return {
        "mode": mode,
        "subject": subject,
        "expires_at": expires_at,
        # The panel needs this to decide whether to offer an edit affordance at all.
        # Without it a member sees a working form that the server rejects with 403,
        # which reads as a broken page rather than as a permission boundary.
        "role": role,
        "loopback": is_loopback(request),
        "login_available": bool(bootstrap is not None and bootstrap.available),
        "init_token_generated": bool(bootstrap is not None and bootstrap.generated),
        # The panel used to say only "login_available: false", which gave no way to
        # distinguish "wrong token typed" from "spent, and a restart will NOT mint a
        # new one". The operator needs the latter state to know the recovery command.
        "bootstrap_state": bootstrap.state if bootstrap is not None else "uninitialised",
        # Where to find the credential, resolved from the *actual* data dir rather than a
        # hard-coded "data/init_token.txt" that is wrong for systemd, Docker and custom
        # SOAPBOT_DATA_DIR installs. A path is not a secret: it tells an operator where to
        # look without making them guess or read the source. The value itself is never
        # returned — putting a live credential on an unauthenticated endpoint would let
        # anyone who can reach the panel log in.
        "bootstrap_path": str(settings.data_dir / BOOTSTRAP_FILE),
        "ttl_seconds": state.token_service.ttl_seconds if state.token_service else 0,
    }


# ------------------------------------------------------------- revocation
@router.post("/logout")
async def logout(
    request: Request, response: Response, auth: dict[str, Any] = Depends(require_api_auth)
) -> dict:
    """Revoke the caller's own token.

    Until this existed there was no way to end a session: a signed token was valid for
    its full 72 hours whatever the operator did, and the only remedy — rotating the
    signing secret — logged every session out at once, so nobody used it.

    Only a bearer token can be revoked. The loopback fallback carries no token, so there
    is nothing to revoke; saying so is better than returning ``ok: true`` and doing
    nothing.
    """
    store = _auth_state(request).revocations
    claims = getattr(request.state, "claims", None)
    if store is None:
        raise HTTPException(status_code=503, detail="token revocation is not initialised")
    if auth.get("mode") != "token" or claims is None:
        raise HTTPException(
            status_code=400,
            detail="this session has no token to revoke; loopback access is not a session",
        )

    revoked = store.revoke(claims.token_id, claims.expires_at)
    get_audit_log().record(
        kind="login",
        action="logout",
        outcome="allow" if revoked else "deny",
        detail=(
            f"subject={claims.subject} jti={claims.token_id[:8]} from={_client_host(request)}"
            + ("" if revoked else " (already revoked)")
        ),
    )
    _clear_session(response)
    return {"ok": True, "revoked": revoked}


@router.post("/revoke-all")
async def revoke_all_tokens(
    request: Request, response: Response, auth: dict[str, Any] = Depends(require_api_auth)
) -> dict:
    """Invalidate every token issued so far. Owner only.

    This is the "the signing key may be compromised" button. It has to work without
    knowing which tokens exist, which is why the store keeps a cut-off timestamp rather
    than only a list of ids — an operator who suspects their laptop was stolen does not
    have the ``jti`` of the token on it.

    Owner rather than admin: it logs out every operator and every open panel, and an
    admin who can do that to the owner is an admin who can deny service.
    """
    from soapbot.api.admin import _role_of
    from soapbot.security.principal import Role

    store = _auth_state(request).revocations
    if store is None:
        raise HTTPException(status_code=503, detail="token revocation is not initialised")

    role = _role_of(auth)
    if role.rank < Role.OWNER.rank:
        get_audit_log().record(
            kind="login",
            action="revoke_all",
            outcome="deny",
            role=role.value,
            detail=f"requires owner from={_client_host(request)}",
        )
        raise HTTPException(status_code=403, detail="revoking all tokens requires the owner role")

    # Two mechanisms, used together on purpose. The cut-off catches tokens the operator
    # cannot enumerate; revoking the caller's own id catches the one token the timestamp
    # cannot distinguish — its own, if it was issued in the same whole second as the
    # cut-off. Without the second step "revoke everything" can leave the caller's own
    # session alive, which is the one session the operator definitely knows about.
    caller_claims = getattr(request.state, "claims", None)
    if caller_claims is not None:
        store.revoke(caller_claims.token_id, caller_claims.expires_at)
    cut_off = store.revoke_all()

    # "Revoked" used to be a log line rather than a state: the response immediately
    # handed the caller a fresh 72h full-privilege token (and a cookie), issued *after*
    # the cut-off. Every session was gone except the one that mattered — the operator's
    # own — and getting it back required no explicit login at all.
    #
    # Closing the revocation now means: no live session token anywhere, plus a freshly
    # minted single-use bootstrap credential that must be redeemed through
    # /api/auth/login. The owner is not locked out (no host round-trip, no restart),
    # but returning is an explicit authentication step, not an automatic renewal.
    _clear_session(response)
    bootstrap = _auth_state(request).bootstrap
    new_bootstrap = bootstrap.regenerate() if bootstrap is not None else ""

    # Verify the terminal state rather than assuming the writes above did what they
    # claim. A store that silently failed to revoke, or a bootstrap that is still
    # consumed, must never be reported as a successful closure.
    caller_claims = getattr(request.state, "claims", None)
    caller_revoked = caller_claims is None or store.is_revoked(
        caller_claims.token_id, caller_claims.issued_at
    )
    way_back_in = bootstrap is None or bootstrap.available
    if not caller_revoked or not way_back_in:
        get_audit_log().record(
            kind="login",
            action="revoke_all",
            outcome="deny",
            role=role.value,
            detail=(
                f"closure_check_failed caller_revoked={caller_revoked} "
                f"bootstrap_available={way_back_in}"
            ),
        )
        raise HTTPException(
            status_code=500, detail="revocation did not reach a closed terminal state"
        )

    get_audit_log().record(
        kind="login",
        action="revoke_all",
        outcome="allow",
        role=role.value,
        detail=(
            f"revoked_before={int(cut_off)} from={_client_host(request)} "
            f"caller_revoked={caller_revoked} bootstrap_rotated={bool(new_bootstrap)} "
            "session_token_issued=False requires_login=True"
        ),
    )
    return {
        "ok": True,
        "revoked_before": cut_off,
        "bootstrap_token": new_bootstrap,
        "requires_login": True,
    }


@router.get("/revocations")
async def list_revocations(
    request: Request,
    _auth: dict[str, Any] = Depends(require_api_auth),
) -> dict[str, Any]:
    """What the panel shows on the security page. Read-only, no secrets."""
    store = _auth_state(request).revocations
    if store is None:
        return {"revoked_before": 0.0, "count": 0, "tokens": []}
    return store.snapshot()
