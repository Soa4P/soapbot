"""Security API: audit trail and effective permission matrix.

Why expose this over HTTP at all: a denial log nobody reads is not a control. The
operator needs to see, in one place, who is being refused and why — that is how a
quiet enumeration attempt in a group chat becomes visible at all.
"""

from __future__ import annotations

import logging

from fastapi import APIRouter, Depends, Query

from soapbot.api.auth import require_api_auth, require_role
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
# Audit records contain operator actions and refusal reasons. An anonymous viewer
# should not be able to enumerate them from a loopback tab.
router = APIRouter(
    prefix="/api/security", tags=["security"], dependencies=[Depends(require_role(Role.MEMBER))]
)


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


class GroupScopePatch(BaseModel):
    """Where the bot speaks, and where it learns. Empty list means "everywhere"."""

    reply_groups: list[str] = []
    memory_collect_groups: list[str] = []


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

    # The first-run owner is re-inserted on every write so the panel can never lock
    # itself out. It has to happen *before* the conflict check: inserting it afterwards
    # could put the same account in ``owners`` and ``admins`` — the exact state this
    # check exists to prevent — and the operator would have no way to fix it, because
    # that account is not in their payload.
    inherited = normalize_id(settings.first_run_owner)
    if inherited:
        if inherited not in owners:
            owners.insert(0, inherited)
        # Owner outranks both, so a stale entry in a lower list is dropped rather than
        # reported as a conflict the operator cannot resolve.
        admins = [qq for qq in admins if qq != inherited]
        members = [qq for qq in members if qq != inherited]

    # One account, one role. Permission resolution takes the highest rank, so a number
    # in both ``owners`` and ``members`` behaves as owner — but the list then reads as
    # "this person is a member", and removing them from the lower list appears to do
    # nothing. The write is refused instead of silently producing a self-contradicting
    # file.
    conflicts = sorted(
        (set(owners) & set(admins))
        | (set(owners) & set(members))
        | (set(admins) & set(members))
    )
    if conflicts:
        detail = ", ".join(
            f"{qq}("
            + "/".join(
                name
                for name, group in (("owner", owners), ("admin", admins), ("member", members))
                if qq in group
            )
            + ")"
            for qq in conflicts
        )
        _get_audit_log().record(
            kind="authz",
            action="authority_write",
            outcome="deny",
            role=role.value,
            detail=f"role_conflict {detail}",
        )
        raise HTTPException(
            status_code=400,
            detail=t("api.authorityRoleConflict", locale, detail=detail),
        )

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


@router.get("/group-scope")
async def read_group_scope(request: Request, _: dict = Depends(require_api_auth)) -> dict:
    """What the *running* process currently uses, not just what the file says.

    Empty means every group, for each list independently — the same rule in the policy,
    the panel and the docs. ``effective_collect`` is kept as an alias of the collect list
    so older panel builds do not break, but it no longer inherits from the reply list:
    that inheritance made narrowing replies silently stop archiving.
    """
    from soapbot.config import settings

    reply = list(settings.reply_groups or [])
    legacy = list(settings.group_allowlist or [])
    if not reply and legacy:
        reply = legacy
    collect = list(settings.memory_collect_groups or [])

    return {
        "reply_groups": reply,
        "memory_collect_groups": collect,
        "effective_collect": collect,
        "legacy_alias_in_use": bool(legacy and not settings.reply_groups),
        "reply_scope": "all" if not reply else "listed",
        "collect_scope": "all" if not collect else "listed",
    }


@router.post("/group-scope")
async def write_group_scope(
    payload: GroupScopePatch, request: Request, auth: dict = Depends(require_api_auth)
) -> dict:
    """Persist the two lists into ``.env``; the running process picks them up on restart.

    Admin rather than owner: this narrows where the bot is *seen*, it cannot grant
    anyone a role or open a private channel.
    """
    from soapbot.api.settings import _env_path, _rewrite_env
    from soapbot.core.config_write import write_atomic

    role = _role_of(auth)
    locale = request_locale(request)
    if role.rank < Role.ADMIN.rank:
        _get_audit_log().record(
            kind="authz",
            action="group_scope_write",
            outcome="deny",
            role=role.value,
            detail=f"from={request.client.host if request.client else '-'}",
        )
        raise HTTPException(status_code=403, detail=t("api.role_required", locale, role="admin"))

    reply = _clean_ids(payload.reply_groups)
    collect = _clean_ids(payload.memory_collect_groups)

    # A group that is collected but never replied to is a legitimate combination, so it
    # is not rejected. A group that is neither cannot be expressed here — it simply stays
    # out of both lists.
    updates = {
        "SOAPBOT_REPLY_GROUPS": ",".join(reply),
        "SOAPBOT_MEMORY_COLLECT_GROUPS": ",".join(collect),
        # An explicit empty value must override the deprecated alias on restart.
        "SOAPBOT_GROUP_ALLOWLIST": "",
    }
    path = _env_path()
    try:
        existing = path.read_text(encoding="utf-8") if path.is_file() else ""
    except OSError as exc:
        raise HTTPException(status_code=500, detail=t("api.write_failed", locale)) from exc

    _get_audit_log().record(
        kind="config",
        action="group_scope_write",
        outcome="allow",
        role=role.value,
        detail=(
            f"reply={len(reply)} collect={len(collect)} "
            f"from={request.client.host if request.client else '-'}"
        ),
    )
    write_atomic(path, _rewrite_env(existing, updates))

    # Same shape as the GET, computed the same way. Reporting `collect or reply` here
    # while the GET reports only `collect` made the panel show "all groups" right after
    # saving two groups, and "listed" after a reload.
    return {
        "ok": True,
        "restart_required": True,
        "reply_groups": reply,
        "memory_collect_groups": collect,
        "effective_collect": collect,
        "reply_scope": "all" if not reply else "listed",
        "collect_scope": "all" if not collect else "listed",
    }
