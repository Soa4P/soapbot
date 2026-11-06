"""Persona growth: versions, diffs and rollback.

Growth writes apply immediately, so this module is the only place an operator can
see what changed and undo it. Every route is ADMIN: a persona body is the first
section of the system prompt, which is the same reason the existing read endpoint
requires more than a plain authenticated token.
"""

from __future__ import annotations

import re
from typing import Any

from fastapi import APIRouter, Depends, HTTPException, Query

from soapbot.ai.persona_growth import PersonaGrowthError
from soapbot.api.auth import require_role
from soapbot.security.principal import Role

router = APIRouter(
    prefix="/api/personas",
    tags=["personas"],
    dependencies=[Depends(require_role(Role.ADMIN))],
)

_PERSONA_ID_RE = re.compile(r"^[A-Za-z0-9_-]{1,64}$")


def _runtime():
    from soapbot.app import get_runtime

    runtime = get_runtime()
    if runtime is None:
        raise HTTPException(status_code=503, detail="bot runtime is not initialised")
    return runtime


def _growth():
    store = getattr(_runtime(), "personas", None)
    growth = getattr(store, "growth", None) if store is not None else None
    if store is None or growth is None:
        raise HTTPException(status_code=503, detail="persona growth is not initialised")
    return store, growth


def _checked(persona_id: str) -> str:
    if not _PERSONA_ID_RE.match(persona_id):
        raise HTTPException(status_code=400, detail="invalid persona id")
    return persona_id


@router.get("/{persona_id}/growth")
async def growth_usage(persona_id: str) -> dict[str, Any]:
    _checked(persona_id)
    store, growth = _growth()
    if store.get(persona_id) is None:
        raise HTTPException(status_code=404, detail="no such persona")
    return growth.usage(persona_id)


@router.get("/{persona_id}/versions")
async def list_versions(
    persona_id: str, limit: int = Query(default=50, ge=1, le=200)
) -> dict[str, Any]:
    _checked(persona_id)
    store, growth = _growth()
    if store.get(persona_id) is None:
        raise HTTPException(status_code=404, detail="no such persona")
    rows = growth.history.list_versions(persona_id, limit=limit)
    return {
        "persona_id": persona_id,
        "count": len(rows),
        "versions": [
            {
                "version": row.version,
                "actor": row.actor,
                "flagged": row.flagged,
                "source_session": row.source_session,
                "trace_id": row.trace_id,
                "created_at": row.created_at,
                "chars": len(row.content),
            }
            for row in rows
        ],
    }


@router.get("/{persona_id}/versions/{version}")
async def version_detail(persona_id: str, version: int) -> dict[str, Any]:
    _checked(persona_id)
    store, growth = _growth()
    if store.get(persona_id) is None:
        raise HTTPException(status_code=404, detail="no such persona")
    row = growth.history.get(persona_id, version)
    if row is None:
        raise HTTPException(status_code=404, detail="no such version")
    previous = growth.history.get(persona_id, version - 1)
    return {
        "version": row.version,
        "actor": row.actor,
        "flagged": row.flagged,
        "created_at": row.created_at,
        "source_session": row.source_session,
        "trace_id": row.trace_id,
        # Both sides are returned so the panel can render a line diff without a
        # second request, and without guessing which version came before.
        "content": row.content,
        "previous_content": previous.content if previous is not None else "",
    }


@router.post("/{persona_id}/rollback/{version}")
async def rollback(persona_id: str, version: int) -> dict[str, Any]:
    _checked(persona_id)
    store, growth = _growth()
    if store.get(persona_id) is None:
        raise HTTPException(status_code=404, detail="no such persona")
    try:
        created = growth.rollback(store, persona_id, version, actor="operator")
    except PersonaGrowthError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    return {"ok": True, "version": created.version, "restored_from": version}
