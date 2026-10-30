"""Adapter configuration endpoints: read, diff, then apply.

Same three-step shape as ``api/config_write.py`` and for the same reason — the operator
approves concrete lines, not a JSON blob they have to imagine. Kept in its own module
because the identity rule is different: providers are keyed by ``id`` and validated
field by field, while adapters are keyed by ``kind`` and carry a free-form option bag.

The one rule that cannot be relaxed is uniqueness by kind. `load_adapters` raises on a
duplicate, and the runtime registers one adapter per kind, so a second entry with the
same kind would replace the first's connection settings at startup — the kind of edit
that looks like "I added a second account" and behaves like "I broke the first one".
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
from soapbot.security.principal import Permission

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/config", tags=["config"])

MASK_HINT = "字面量密钥显示为掩码；提交时用 __UNCHANGED__ 表示保留原值。"


class AdapterEntry(BaseModel):
    """One adapter entry. Options are an open bag, so extra fields are allowed."""

    model_config = {"extra": "allow"}

    kind: str = ""
    enabled: bool | None = None


class AdaptersDiffRequest(BaseModel):
    adapters: list[AdapterEntry] = Field(default_factory=list)
    base_hash: str = ""


class AdaptersApplyRequest(AdaptersDiffRequest):
    approved_hash: str = ""


def _adapters_path():
    return settings.adapters_file


def _payload(payload: AdaptersDiffRequest) -> list[dict[str, Any]]:
    # `exclude_unset`: a field the form did not send must not be written as null. The
    # adapter form renders kind/enabled/ws_url/token, and blanking `self_id` because the
    # form never showed it is exactly the bug this flag prevents.
    return [entry.model_dump(exclude_unset=True) for entry in payload.adapters]


def _patch(path, patch: list[dict[str, Any]], base_hash: str):
    return config_write.build_patch(
        path=path,
        patch=patch,
        base_hash=base_hash,
        apply_fn=config_write.apply_adapter_patch,
        validate_fn=config_write.validate_adapters,
        filename="adapters.yaml",
    )


@router.get("/adapters")
async def read_adapters(
    _auth: dict[str, Any] = Depends(require_api_auth),
) -> dict[str, Any]:
    """The document as the editor should see it: secrets masked, hash included."""
    path = _adapters_path()
    try:
        document = config_write.read_document(path)
    except ConfigError as exc:
        # Reported, not swallowed into an empty form: saving over a file that merely had
        # a typo is worse than showing the typo.
        raise HTTPException(status_code=422, detail=str(exc)) from exc

    return {
        "document": config_write.mask_document(document),
        "base_hash": config_write.file_hash(path),
        "path": str(path),
        "mask": config_write.MASK,
        "unchanged_sentinel": config_write.UNCHANGED,
        "hint": MASK_HINT,
    }


@router.post("/adapters/diff")
async def diff_adapters(
    payload: AdaptersDiffRequest,
    request: Request,
    _auth: dict[str, Any] = Depends(require_api_auth),
) -> dict[str, Any]:
    """Compute the diff for a patch. Writes nothing."""
    from soapbot.api.config_write import _require_permission

    _require_permission(_auth, request, Permission.MANAGE_CONFIG)
    try:
        result = _patch(_adapters_path(), _payload(payload), payload.base_hash)
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


@router.post("/adapters/apply")
async def apply_adapters(
    payload: AdaptersApplyRequest,
    request: Request,
    _auth: dict[str, Any] = Depends(require_api_auth),
) -> dict[str, Any]:
    """Write the patch, but only if the operator approved the current diff."""
    from soapbot.api.config_write import _audit, _caller_label, _require_permission

    _require_permission(_auth, request, Permission.MANAGE_CONFIG)
    path = _adapters_path()
    actor = _caller_label(request)

    try:
        result = _patch(path, _payload(payload), payload.base_hash)
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
        return {"written": False, "reason": "no changes", "changed_fields": []}

    if payload.approved_hash and payload.approved_hash != result.new_hash:
        _audit(actor, "deny", "unapproved_diff", result.changed_fields)
        raise HTTPException(
            status_code=409,
            detail="确认的 diff 与实际将要写入的内容不一致，请重新预览。",
        )

    config_write.write_atomic(path, result.rendered)
    _audit(actor, "allow", "apply_adapters", result.changed_fields)
    logger.info("adapters written by %s: %s", actor, ", ".join(result.changed_fields) or "-")

    return {
        "written": True,
        "changed_fields": result.changed_fields,
        "new_hash": result.new_hash,
        "restart_required": True,
        "audit": get_audit_log().recent(limit=1),
    }
