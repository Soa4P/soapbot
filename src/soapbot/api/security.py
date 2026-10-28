"""Security API: audit trail and effective permission matrix.

Why expose this over HTTP at all: a denial log nobody reads is not a control. The
operator needs to see, in one place, who is being refused and why — that is how a
quiet enumeration attempt in a group chat becomes visible at all.
"""

from __future__ import annotations

import logging

from fastapi import APIRouter, Depends, Query

from soapbot.api.auth import require_api_auth
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
