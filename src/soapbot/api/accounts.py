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
    create_invite,
    create_owner,
    grant_membership,
    list_accounts,
    list_memberships,
    redeem_invite,
)
from soapbot.accounts.service import account_from_claims
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
    account = await account_from_claims(db, auth)
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
    account = await account_from_claims(_db(request), auth)
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
            {"id": a.id, "username": a.username, "role": a.role, "status": a.status}
            for a in rows
        ]
    }


@router.post("/memberships")
async def grant(
    payload: GrantRequest,
    request: Request,
    auth: dict[str, Any] = Depends(require_role(Role.OWNER, require_credential=True)),
) -> dict[str, Any]:
    account = await account_from_claims(_db(request), auth)
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
