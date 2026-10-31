"""Security API: audit trail and effective permission matrix.

Why expose this over HTTP at all: a denial log nobody reads is not a control. The
operator needs to see, in one place, who is being refused and why — that is how a
quiet enumeration attempt in a group chat becomes visible at all.
"""

from __future__ import annotations

import logging

from fastapi import APIRouter, Depends, Query

from soapbot.api.auth import require_api_auth
from soapbot.api.locale import request_locale
from soapbot.i18n import t
from soapbot.security.audit import get_audit_log
from soapbot.security.principal import (
    PERMISSION_MIN_ROLE,
    Permission,
    Principal,
    PrincipalResolver,
    Role,
)

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/api/security", tags=["security"])


@router.get("/audit")
async def audit_events(
    limit: int = Query(100, ge=1, le=1000),
    kind: str = Query("", description="authz / injection / memory / command / rate_limit"),
    _: dict = Depends(require_api_auth),
) -> dict:
    """Recent security events, newest last."""
    audit = get_audit_log()
    return {
        "events": audit.recent(limit=limit, kind=kind),
        "total_denials": audit.denials,
        "total_blocks": audit.blocks,
    }


@router.get("/denials")
async def denials(
    limit: int = Query(100, ge=1, le=1000),
    _: dict = Depends(require_api_auth),
) -> dict:
    """Denials only — the view an operator actually triages."""
    audit = get_audit_log()
    events = [e for e in audit.recent(limit=1000) if e["outcome"] == "deny"]
    return {"events": events[-limit:], "count": len(events)}


@router.get("/permissions")
async def permission_matrix(_: dict = Depends(require_api_auth)) -> dict:
    """Declared permission floors, for the WebUI's access-control page.

    Showing the floor next to each permission makes a mistake visible: an operator
    who sees ``approve_payment -> owner`` immediately understands why an admin
    cannot approve it.
    """
    return {
        "permissions": [
            {"name": p.value, "min_role": PERMISSION_MIN_ROLE.get(p, Role.OWNER).value}
            for p in Permission
        ],
        "roles": [
            {"name": r.value, "rank": r.rank}
            for r in sorted(Role, key=lambda r: r.rank)
        ],
    }


@router.get("/whoami")
async def whoami(
    user_id: str = Query(..., description="QQ number to resolve"),
    _: dict = Depends(require_api_auth),
) -> dict:
    """Preview how a given id would be judged.

    Useful when an operator is debugging "why can't this user run /kb?" — they can
    check the resolved role without needing the user to send a message.
    """
    principal: Principal = PrincipalResolver().resolve(_StubEvent(user_id))
    return {
        "user_id": principal.user_id,
        "role": principal.role.value,
        "source": principal.source,
        "authenticated": principal.authenticated,
        # Derived from the role, not stored: granted already holds the explicit
        # set, but permissions implied by rank are computed by can().
        "permissions": sorted(p.value for p in Permission if principal.can(p)),
    }


class _StubEvent:
    """Minimal event-shaped object for identity previewing."""

    def __init__(self, user_id: str) -> None:
        self.adapter = "onebot11"
        self.group_id = ""
        self.scene = "group"
        self.sender = _StubSender(user_id)
        self.trace_id = "preview"
        self.transport_authenticated = True


class _StubSender:
    def __init__(self, user_id: str) -> None:
        self.user_id = user_id
        self.display_name = user_id
        self.role = "member"


# ------------------------------------------------------------------ authority lists
#
# The QQ-number allow-lists are the only source of bot privilege, and until now the only
# way to edit them was a text editor on the host. The panel already *shows* the lists
# (04 安全审计 → 角色与授权名单); showing a control room without controls is how "who may
# do what" quietly becomes "whatever the config file says last month".

from fastapi import HTTPException, Request  # noqa: E402
from pydantic import BaseModel  # noqa: E402

from soapbot.api.admin import _role_of  # noqa: E402
from soapbot.security.audit import get_audit_log as _get_audit_log  # noqa: E402
from soapbot.security.principal import normalize_id  # noqa: E402


class AuthorityPatch(BaseModel):
    """Full replacement lists. Normalised and validated before anything is written."""

    owners: list[str] = []
    admins: list[str] = []
    members: list[str] = []


def _clean_ids(raw: list[str]) -> list[str]:
    """Normalize, de-duplicate, and require actual account numbers.

    ``normalize_id`` already folds full-width digits, zero-width characters and leading
    ``+``; the digit check is what stops "owner": " fooled you" from ever reaching the
    file. Order is preserved so the panel round-trips what the operator typed.
    """
    ids: list[str] = []
    for item in raw:
        nid = normalize_id(item)
        if not nid:
            continue
        if not nid.isdigit():
            raise HTTPException(status_code=400, detail=f"not a QQ number: {item!r}")
        if nid not in ids:
            ids.append(nid)
    return ids


@router.post("/authority")
async def write_authority(
    payload: AuthorityPatch, request: Request, auth: dict = Depends(require_api_auth)
) -> dict:
    """Replace the owner/admin/member lists, then say ``restart_required``.

    Owner-only, and guarded against the classic self-lockout: the effective owner set
    after the write must not be empty, and a ``first_run_owner`` configured in the
    environment is carried into the written list (it stops being consulted the moment
    ``owner_ids`` is non-empty, so dropping it here would silently demote the one person
    who can undo the mistake).
    """
    from soapbot.api.settings import _env_path, _rewrite_env
    from soapbot.config import settings
    from soapbot.core.config_write import write_atomic

    role = _role_of(auth)
    locale = request_locale(request)
    if role.rank < Role.OWNER.rank:
        _get_audit_log().record(
            kind="authz",
            action="authority_write",
            outcome="deny",
            role=role.value,
            detail=f"from={request.client.host if request.client else '-'}",
        )
        raise HTTPException(status_code=403, detail=t("api.role_required", locale, role="owner"))

    owners = _clean_ids(payload.owners)
    admins = _clean_ids(payload.admins)
    members = _clean_ids(payload.members)

    inherited = normalize_id(settings.first_run_owner)
    if inherited and inherited not in owners:
        owners.insert(0, inherited)

    if not owners:
        raise HTTPException(status_code=400, detail=t("api.authorityLastOwner", locale))

    updates = {
        "SOAPBOT_OWNER_IDS": ",".join(owners),
        "SOAPBOT_ADMIN_IDS": ",".join(admins),
        "SOAPBOT_MEMBER_IDS": ",".join(members),
    }
    path = _env_path()
    try:
        existing = path.read_text(encoding="utf-8") if path.is_file() else ""
    except OSError as exc:
        raise HTTPException(status_code=500, detail=t("api.write_failed", locale)) from exc

    _get_audit_log().record(
        kind="config",
        action="authority_write",
        outcome="allow",
        role=role.value,
        detail=(
            f"owners={len(owners)} admins={len(admins)} members={len(members)} "
            f"from={request.client.host if request.client else '-'}"
        ),
    )
    write_atomic(path, _rewrite_env(existing, updates))

    return {
        "ok": True,
        "restart_required": True,
        "owners": owners,
        "admins": admins,
        "members": members,
        "inherited_owner": inherited,
    }
