"""Account endpoints for the web/app archive clients.

Two credentials coexist on purpose:

* the one-time bootstrap token (existing ``/api/auth/login``) still creates the first
  operator session, because a fresh install has no account to log in with;
* username/password accounts are the long-lived path, invite-only, and carry a
  numeric subject so membership checks can find the row.

Nothing here issues a token for a disabled account, and nothing trusts a role from
the request body.
"""

from __future__ import annotations

import logging
from typing import Any

from fastapi import APIRouter, Depends, HTTPException, Request, Response
from pydantic import BaseModel, Field

from soapbot.accounts import (
    Account,
    AccountError,
    authenticate,
    bind_qq_user,
    create_invite,
    create_owner,
    grant_membership,
    list_accounts,
    list_memberships,
    redeem_invite,
    set_account_status,
    unbind_qq_user,
)
from soapbot.accounts.service import active_account_from_claims
from soapbot.api.auth import (
    _auth_state,
    _client_host,
    _reject_cross_site,
    _set_session,
    require_api_auth,
    require_role,
)
from soapbot.security.principal import Role

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/api/accounts", tags=["accounts"])


def _db(request: Request):
    from soapbot.app import get_runtime

    runtime = get_runtime()
    if runtime is None or getattr(runtime, "memory", None) is None:
        raise HTTPException(status_code=503, detail="bot runtime is not initialised")
    return runtime.memory.db


class Credentials(BaseModel):
    username: str = Field(..., min_length=3, max_length=32)
    password: str = Field(..., min_length=8, max_length=128)


class RegisterRequest(Credentials):
    invite: str = Field(..., min_length=8, max_length=128)


class InviteRequest(BaseModel):
    role: str = Field("member", pattern="^(member|owner)$")
    hours: int = Field(72, ge=1, le=24 * 30)
    max_uses: int = Field(1, ge=1, le=100)
    session_keys: list[str] = Field(default_factory=list, max_length=200)


class GrantRequest(BaseModel):
    account_id: int = Field(..., ge=1)
    session_key: str = Field(..., min_length=1, max_length=128)


class StatusRequest(BaseModel):
    status: str = Field(..., pattern="^(active|disabled)$")


def _issue(request: Request, response: Response, account: Account) -> dict[str, Any]:
    state = _auth_state(request)
    service = state.token_service
    if service is None:
        raise HTTPException(status_code=503, detail="auth is not initialised")
    token, claims = service.issue(str(account.id), role=account.role)
    _set_session(response, token, service.ttl_seconds)
    return {
        "account": {
            "id": account.id,
            "username": account.username,
            "role": account.role,
        },
        "access_token": token,
        "token_type": "bearer",
        "expires_in": service.ttl_seconds,
        "expires_at": claims.expires_at,
    }


@router.post("/owner")
async def create_first_owner(
    payload: Credentials,
    request: Request,
    response: Response,
    _auth: dict[str, Any] = Depends(require_role(Role.ADMIN, require_credential=True)),
) -> dict[str, Any]:
    """Create the first owner once, using the bootstrap admin credential.

    Deliberately not public: the bootstrap token is the only thing that can reach it,
    and it stops working for this purpose as soon as one account exists.
    """
    try:
        account = await create_owner(_db(request), username=payload.username, password=payload.password)
    except AccountError as exc:
        raise HTTPException(status_code=409, detail=exc.message) from exc
    logger.info("owner account created username=%s", account.username)
    return _issue(request, response, account)


@router.post("/register")
async def register(payload: RegisterRequest, request: Request, response: Response) -> dict[str, Any]:
    _reject_cross_site(request)
    try:
        account = await redeem_invite(
            _db(request),
            code=payload.invite,
            username=payload.username,
            password=payload.password,
        )
    except AccountError as exc:
        raise HTTPException(status_code=400, detail=exc.message) from exc
    logger.info("account registered username=%s", account.username)
    return _issue(request, response, account)


@router.post("/login")
async def login(payload: Credentials, request: Request, response: Response) -> dict[str, Any]:
    _reject_cross_site(request)
    host = _client_host(request) or "unknown"
    state = _auth_state(request)
    verdict = state.login_limiter.check(host)
    if verdict.limited:
        raise HTTPException(
            status_code=429,
            detail="too many login attempts",
            headers={"Retry-After": str(int(verdict.retry_after) + 1)},
        )
    account = await authenticate(_db(request), username=payload.username, password=payload.password)
    if account is None:
        # Same answer for unknown user and wrong password: the difference is an
        # account-enumeration oracle.
        raise HTTPException(status_code=401, detail="invalid username or password")
    state.login_limiter.reset(host)
    return _issue(request, response, account)


@router.get("/me")
async def me(
    request: Request,
    auth: dict[str, Any] = Depends(require_api_auth),
) -> dict[str, Any]:
    db = _db(request)
    account = await active_account_from_claims(db, auth)
    if account is None:
        raise HTTPException(status_code=401, detail="account no longer exists")
    sessions = await list_memberships(db, account.id) if account.id else []
    return {
        "id": account.id,
        "username": account.username,
        "role": account.role,
        "sessions": sessions,
    }


@router.post("/invites")
async def create_invite_code(
    payload: InviteRequest,
    request: Request,
    auth: dict[str, Any] = Depends(require_role(Role.OWNER, require_credential=True)),
) -> dict[str, Any]:
    account = await active_account_from_claims(_db(request), auth)
    if account is None or not account.is_owner:
        raise HTTPException(status_code=403, detail="owner only")
    code = await create_invite(
        _db(request),
        created_by=account.id,
        role=payload.role,
        hours=payload.hours,
        max_uses=payload.max_uses,
        session_keys=tuple(payload.session_keys),
    )
    # The code is shown once; only its hash is stored.
    return {"invite": code, "role": payload.role, "expires_in_hours": payload.hours}


@router.get("")
async def accounts(
    request: Request,
    _auth: dict[str, Any] = Depends(require_role(Role.OWNER, require_credential=True)),
) -> dict[str, Any]:
    rows = await list_accounts(_db(request))
    return {
        "accounts": [
            {
                "id": a.id,
                "username": a.username,
                "role": a.role,
                "status": a.status,
                "qq_user_id": a.qq_user_id,
            }
            for a in rows
        ]
    }


@router.post("/{account_id}/status")
async def set_status(
    account_id: int,
    payload: StatusRequest,
    request: Request,
    auth: dict[str, Any] = Depends(require_role(Role.OWNER, require_credential=True)),
) -> dict[str, Any]:
    """Enable or disable an account.

    This is the only way to take a member out of the archive: there is no delete, on
    purpose — a deleted account would take its membership grants with it, while a
    disabled one keeps its history and can be switched back on.
    """
    actor = await active_account_from_claims(_db(request), auth)
    if actor is None or not actor.is_owner:
        raise HTTPException(status_code=403, detail="owner only")
    try:
        updated = await set_account_status(
            _db(request), account_id=account_id, status=payload.status
        )
    except AccountError as exc:
        raise HTTPException(status_code=400, detail=exc.message) from exc
    return {
        "ok": True,
        "account": {
            "id": updated.id,
            "username": updated.username,
            "role": updated.role,
            "status": updated.status,
        },
    }


@router.post("/memberships")
async def grant(
    payload: GrantRequest,
    request: Request,
    auth: dict[str, Any] = Depends(require_role(Role.OWNER, require_credential=True)),
) -> dict[str, Any]:
    account = await active_account_from_claims(_db(request), auth)
    if account is None or not account.is_owner:
        raise HTTPException(status_code=403, detail="owner only")
    try:
        await grant_membership(
            _db(request),
            account_id=payload.account_id,
            session_key=payload.session_key,
            created_by=account.id,
        )
    except AccountError as exc:
        raise HTTPException(status_code=400, detail=exc.message) from exc
    return {"ok": True}


class BindingRequest(BaseModel):
    qq_user_id: str = Field(..., min_length=5, max_length=20)


def _binding_payload(updated: Account) -> dict[str, Any]:
    return {"id": updated.id, "qq_user_id": updated.qq_user_id}


def _invalidate_session_mapper() -> None:
    """Drop the mapper's cached bindings after a bind/unbind.

    The mapper caches lookups (including misses) for a short TTL; without this, an
    unbind could keep a unified session alive for up to that TTL. Rare operation,
    cheap to invalidate wholesale.
    """
    from soapbot.app import get_runtime

    runtime = get_runtime()
    mapper = getattr(runtime, "session_mapper", None) if runtime is not None else None
    if mapper is not None:
        mapper.invalidate()


@router.put("/{account_id}/binding")
async def bind(
    account_id: int,
    payload: BindingRequest,
    request: Request,
    auth: dict[str, Any] = Depends(require_role(Role.OWNER, require_credential=True)),
) -> dict[str, Any]:
    """Bind a QQ platform user to this account (unified chat).

    This is the owner drawing the identity link by hand — a QQ user can never claim
    it themselves, so nobody can merge someone else's platform conversation into
    their own session by sending messages. A PUT (idempotent replace) rather than
    POST: rebinding is moving the link, which the service enforces via the unique
    index and the clash check.
    """
    actor = await active_account_from_claims(_db(request), auth)
    if actor is None or not actor.is_owner:
        raise HTTPException(status_code=403, detail="owner only")
    try:
        updated = await bind_qq_user(
            _db(request), account_id=account_id, qq_user_id=payload.qq_user_id
        )
    except AccountError as exc:
        raise HTTPException(status_code=400, detail=exc.message) from exc
    _invalidate_session_mapper()
    return {"ok": True, "account": _binding_payload(updated)}


@router.delete("/{account_id}/binding")
async def unbind(
    account_id: int,
    request: Request,
    auth: dict[str, Any] = Depends(require_role(Role.OWNER, require_credential=True)),
) -> dict[str, Any]:
    """Remove the QQ binding; the unified mapping stops on the next message."""
    actor = await active_account_from_claims(_db(request), auth)
    if actor is None or not actor.is_owner:
        raise HTTPException(status_code=403, detail="owner only")
    try:
        updated = await unbind_qq_user(_db(request), account_id=account_id)
    except AccountError as exc:
        raise HTTPException(status_code=400, detail=exc.message) from exc
    _invalidate_session_mapper()
    return {"ok": True, "account": _binding_payload(updated)}
