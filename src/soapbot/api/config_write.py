"""Configuration write endpoints: read, diff, then apply.

Three steps, not one, and the split is the whole point
----------------------------------------------------
``GET  /api/config/providers``            -> document with secrets masked + base_hash
``POST /api/config/providers/diff``       -> candidate diff, **nothing written**
``POST /api/config/providers/apply``      -> writes, if base_hash still matches

A single ``PUT`` would be simpler and would be wrong. The operator must see the
concrete lines that will change *before* they change — including lines the form never
showed, such as an inline comment above the provider they edited, or a field another
admin changed five minutes ago. The diff endpoint computes that against the real file
and validates the candidate with the startup parser, so what gets approved is what
will boot. The apply step then re-checks the hash: if the file moved in between, the
diff they approved no longer describes reality, and the answer is 409 with both
versions rather than a silent merge.

Why not ETag/If-Match
--------------------
``base_hash`` is the same mechanism under a different name, but kept in the JSON body
instead of an HTTP header. A header would be more idiomatic; a body field survives the
existing fetch wrapper in ``webui/src/api/client.ts`` unchanged, and this endpoint
already needs a JSON body for the patch. One less place for a proxy to strip a header.

Authorization
-------------
``Permission.MANAGE_CONFIG``, which maps to ADMIN. Loopback callers are owners by
construction (see ``api/auth.py``), so a local operator is not locked out of their own
single-host deployment — but a remote token still has to carry the role.
"""

from __future__ import annotations

import logging
from typing import Any

from fastapi import APIRouter, Depends, HTTPException, Request
from pydantic import BaseModel, Field

from soapbot.api.auth import require_api_auth
from soapbot.config import settings
from soapbot.core import config_write
from soapbot.core.config_files import ConfigError
from soapbot.security.audit import get_audit_log
from soapbot.security.principal import PERMISSION_MIN_ROLE, Permission, Role

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/api/config", tags=["config"])


def _require_permission(auth: dict[str, Any], request: Request, permission: Permission) -> None:
    """Check one permission against the caller's role.

    Takes the dict ``require_api_auth`` already returned rather than reading
    ``request.state`` again: two sources for "who is calling" is how a route ends up
    authorised against a value that was never populated.
    """
    try:
        role = Role(str(auth.get("role") or "anonymous"))
    except ValueError:
        role = Role.ANONYMOUS
    minimum = PERMISSION_MIN_ROLE.get(permission, Role.OWNER)
    if role.rank < minimum.rank:
        get_audit_log().record(
            kind="authz",
            action=permission.value,
            outcome="deny",
            role=role.value,
            detail=f"config write denied for role={role.value} from={request.client.host if request.client else '-'}",
        )
        raise HTTPException(status_code=403, detail=f"需要 {minimum.value} 及以上角色")


class ProviderPatchEntry(BaseModel):
    """One provider in a patch. Every field except ``id`` is optional."""

    id: str = Field(..., min_length=1, max_length=64)
    kind: str | None = None
    label: str | None = None
    base_url: str | None = None
    api_key: str | None = None
    """A new literal, ``env:VAR``, ``enc:v1:...``, ``__UNCHANGED__`` to keep the
    stored value, or ``""`` to clear it."""

    model: str | None = None
    embed_model: str | None = None
    vision_model: str | None = None
    timeout: float | None = None
    max_retries: int | None = None
    priority: int | None = None
    enabled: bool | None = None


class ProvidersDiffRequest(BaseModel):
    base_hash: str = ""
    providers: list[ProviderPatchEntry] = Field(default_factory=list)


class ProvidersApplyRequest(ProvidersDiffRequest):
    """Same payload as the diff step, plus the hash the operator actually approved."""

    approved_hash: str = ""


def _providers_path():
    return settings.providers_file


def _patch_payload(payload: ProvidersDiffRequest) -> list[dict[str, Any]]:
    # `exclude_unset` matters: a field the client did not send must not be written as
    # null. Without it, editing one provider's label would blank its base_url and
    # model, because the form only includes the fields it renders.
    return [entry.model_dump(exclude_unset=True) for entry in payload.providers]


@router.get("/providers")
async def read_providers(
    _auth: dict[str, Any] = Depends(require_api_auth),
) -> dict[str, Any]:
    """The document as the editor should see it: secrets masked, hash included."""
    path = _providers_path()
    try:
        document = config_write.read_document(path)
    except ConfigError as exc:
        # Parse failure is reported, not swallowed into an empty form. An operator who
        # sees an empty form and presses save would overwrite a file that merely had a
        # typo in it.
        raise HTTPException(status_code=422, detail=str(exc)) from exc

    return {
        "document": config_write.mask_document(document),
        "base_hash": config_write.file_hash(path),
        "path": str(path),
        "mask": config_write.MASK,
        "unchanged_sentinel": config_write.UNCHANGED,
        "restart_required": False,
        "hint": "字面量密钥显示为掩码；提交时用 __UNCHANGED__ 表示保留原值。",
    }


@router.post("/providers/diff")
async def diff_providers(
    payload: ProvidersDiffRequest,
    request: Request,
    _auth: dict[str, Any] = Depends(require_api_auth),
) -> dict[str, Any]:
    """Compute the diff for a patch. Writes nothing."""
    _require_permission(_auth, request, Permission.MANAGE_CONFIG)
    path = _providers_path()
    try:
        result = config_write.build_patch(
            path=path,
            patch=_patch_payload(payload),
            base_hash=payload.base_hash,
        )
    except config_write.ConfigConflictError as exc:
        raise HTTPException(
            status_code=409,
            detail={
                "message": "配置文件在你编辑期间被改动，请重新载入后再提交。",
                "current_hash": exc.current_hash,
            },
        ) from exc
    except ConfigError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc

    return {
        "diff": result.diff,
        "changed_fields": result.changed_fields,
        "base_hash": result.base_hash,
        "new_hash": result.new_hash,
        "empty": result.empty,
    }


@router.post("/providers/apply")
async def apply_providers(
    payload: ProvidersApplyRequest,
    request: Request,
    _auth: dict[str, Any] = Depends(require_api_auth),
) -> dict[str, Any]:
    """Write the patch, but only if the operator approved the current diff.

    ``approved_hash`` is compared against a freshly recomputed candidate. If the file
    changed after the diff was shown, the two differ and the write is refused: the
    lines the operator read are no longer the lines that would be written.
    """
    _require_permission(_auth, request, Permission.MANAGE_CONFIG)
    path = _providers_path()
    actor = _caller_label(request)

    try:
        result = config_write.build_patch(
            path=path,
            patch=_patch_payload(payload),
            base_hash=payload.base_hash,
        )
    except config_write.ConfigConflictError as exc:
        _audit(actor, "deny", "stale_base_hash", [])
        raise HTTPException(
            status_code=409,
            detail={
                "message": "配置文件在确认前被改动，本次未写入。",
                "current_hash": exc.current_hash,
            },
        ) from exc
    except ConfigError as exc:
        _audit(actor, "deny", "validation_failed", [])
        raise HTTPException(status_code=422, detail=str(exc)) from exc

    if result.empty:
        # Not an error, and not a write: an empty patch must not touch mtime or hash,
        # or a no-op save would invalidate another admin's open editor.
        return {"written": False, "reason": "no changes", "changed_fields": []}

    if payload.approved_hash and payload.approved_hash != result.new_hash:
        _audit(actor, "deny", "unapproved_diff", result.changed_fields)
        raise HTTPException(
            status_code=409,
            detail={
                "message": "提交的改动与你确认过的 diff 不一致，本次未写入。",
                "expected_hash": result.new_hash,
                "approved_hash": payload.approved_hash,
            },
        )

    try:
        config_write.write_atomic(path, result.rendered)
    except OSError as exc:
        _audit(actor, "deny", f"write_failed:{exc.__class__.__name__}", result.changed_fields)
        logger.exception("configuration write failed for %s", path)
        raise HTTPException(status_code=500, detail="写入失败，文件未被修改。") from exc

    _audit(actor, "allow", "providers_updated", result.changed_fields)
    return {
        "written": True,
        "changed_fields": result.changed_fields,
        "base_hash": result.new_hash,
        # Deliberately explicit rather than a hot reload: ProviderRouter holds cooldown
        # state and the pipeline was assembled at startup. Reloading means rebuilding
        # three objects and defining rollback for each, which is more risk than asking
        # the operator to restart — and the banner they see is the same one that tells
        # them the running process does not yet match the file.
        "restart_required": True,
    }


def _caller_label(request: Request) -> str:
    """Who to blame in the audit log, from the auth state already established."""
    mode = getattr(request.state, "auth_mode", "unknown")
    claims = getattr(request.state, "claims", None)
    subject = getattr(claims, "subject", "") if claims else ""
    return f"{mode}:{subject}" if subject else str(mode)


def _audit(actor: str, outcome: str, action: str, fields: list[str]) -> None:
    """Record the change. Field *names* only — never a value.

    The audit log is exported and read by people who are not allowed to see the
    credentials in this file, so a diff or a value must not enter it. What remains is
    still enough to answer "who changed the API key of provider X, and when".
    """
    get_audit_log().record(
        kind="authz",
        action=action,
        outcome=outcome,
        detail=f"actor={actor} fields={','.join(fields)[:400] or '-'}",
    )
