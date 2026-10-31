"""Management views, read-only except for knowledge content.

Why configuration writes are absent **from this module**
--------------------------------------------------------
Write endpoints for providers, personas and adapters would each be a separate
authorization decision with its own failure mode: a persona edit can remove the
safety paragraph from the system prompt, a provider edit can repoint traffic at
someone else's endpoint. Those deserve their own design and their own review.

Provider writes now exist, in :mod:`soapbot.api.config_write`, and the design they
got is the one this docstring was asking for: read (secrets masked) → diff computed
against the real file and validated with the startup parser, nothing written → apply,
which re-checks that the file has not moved and that the operator approved exactly
these lines. The earlier claim that "configuration changes stay in files, where they
are versioned and reviewed" described an intent, not the deployment: the file was
not in version control and the review did not happen. A diff shown before the write,
plus an audit entry naming the changed fields, is the first version of that review
that actually occurs.

Personas remain unwritable here. Persona cards are Markdown with front matter, and a
form that renders them as fields would silently drop the prose between the front
matter and the body — worse than leaving the section read-only.

Why knowledge *is* writable
---------------------------
The rule above is about **configuration**: things that change what the bot is
allowed to do. A knowledge document is **data** — text the bot may cite, which the
retrieval path already treats as untrusted (``wrap_untrusted(kind="knowledge")``)
and which cannot widen a permission no matter what it says. Holding it to the
same standard as a persona would be consistency for its own sake.

The cost of not having it was concrete: ``chunk``, ``add_document``, FTS indexing
and vector storage were implemented, tested and consumed by the retriever, while
nothing in the service ever called the write side. The knowledge page could only
ever be empty, and the feature was unreachable rather than merely unfinished.

Redaction
---------
Nothing in this file may return a credential. Provider descriptions come from
``BaseProvider.describe()``, which never included the key; the rule is upheld here by
not reaching into ``config.api_key`` at all rather than by remembering to mask it.
"""

from __future__ import annotations

import logging
import re
import time
from typing import Any

from fastapi import APIRouter, Depends, HTTPException, Query, Request
from pydantic import BaseModel, Field

from soapbot import __version__
from soapbot.api.auth import require_api_auth
from soapbot.api.locale import request_locale
from soapbot.i18n import t
from soapbot.security.audit import get_audit_log
from soapbot.security.principal import PERMISSION_MIN_ROLE, Permission, Role

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/api", tags=["admin"])


def _role_of(auth: dict[str, Any]) -> Role:
    """Read the caller's role from what ``require_api_auth`` already returned.

    An unknown string degrades to ANONYMOUS rather than raising: a token carrying a
    role this build does not know must not be treated as "some role, probably fine".
    """
    try:
        return Role(str(auth.get("role") or "anonymous"))
    except ValueError:
        return Role.ANONYMOUS

_PROMPT_PREVIEW_CHARS = 4000

#: Document ids reach a filesystem-adjacent namespace in some deployments and are
#: used in URL paths here, so the charset is narrow and traversal is impossible by
#: construction rather than by a later check.
_DOC_ID_RE = re.compile(r"^[A-Za-z0-9_-]{1,64}$")


def _runtime():
    from soapbot.app import get_runtime

    runtime = get_runtime()
    if runtime is None:
        raise HTTPException(status_code=503, detail="bot runtime is not initialised")
    return runtime


def _scheduler():
    from soapbot.app import get_scheduler

    return get_scheduler()


@router.get("/runtime")
async def runtime_status(_: dict = Depends(require_api_auth)) -> dict:
    """One page that answers "is the bot actually working?".

    Reports three layers separately because they fail independently and the difference
    matters when diagnosing: the *process* (HTTP up), the *runtime* (pipeline built,
    adapters connected), and the *scheduler* (periodic work ticking). A green health
    check with zero online adapters was exactly the state this project shipped in
    before the runtime was wired up, and it looked healthy from every angle.
    """
    from soapbot.app import get_startup_errors

    runtime = _runtime()
    if runtime is None:
        # "Runtime off" and "runtime broken" produced the same red banner, and the honest
        # one is "you turned it off": a panel-only deployment (a fresh install that has no
        # provider yet) is a supported state, not a failure. Answering 503 there made the
        # first screen of a working install look like an error page.
        from soapbot.config import settings

        if not settings.enable_runtime:
            return {
                "version": __version__,
                "enabled": False,
                "running": False,
                "metrics": {},
                "adapters": {},
                "adapter_count": 0,
                "scheduler": {"running": False},
                "startup_errors": [],
                "config": {
                    "providers_file": str(settings.providers_file),
                    "adapters_file": str(settings.adapters_file),
                },
            }
        raise HTTPException(status_code=503, detail="bot runtime failed to start; see the log")

    scheduler = _scheduler()
    status = runtime.status()
    return {
        "version": __version__,
        "enabled": True,
        "running": status["running"],
        "metrics": status["metrics"],
        "adapters": status["adapters"],
        "adapter_count": len(runtime.adapters),
        "scheduler": scheduler.status() if scheduler is not None else {"running": False},
        "startup_errors": get_startup_errors(),
        "config": {
            "providers_file": str(_settings().providers_file),
            "adapters_file": str(_settings().adapters_file),
            "budget_enabled": runtime.budget is not None,
            "memory_enabled": runtime.memory is not None,
            "plugins_loaded": len(runtime.plugins.loader.loaded) if runtime.plugins else 0,
            "plugin_isolation": getattr(runtime.plugins, "supervisor", None) is not None,
        },
    }


@router.get("/mcp")
async def mcp_status(_: dict = Depends(require_api_auth)) -> dict:
    """External tool sources: which servers are configured, how many tools each.

    A server that failed to start is listed with its error rather than omitted. "This
    server has no tools" and "this server crashed" are the same empty list otherwise,
    and they call for opposite fixes.
    """
    runtime = _runtime()
    manager = getattr(runtime, "mcp", None)
    if manager is None:
        return {"configured": False, "servers": [], "tools": 0}
    return {"configured": True, **manager.status()}


@router.post("/mcp/refresh")
async def refresh_mcp(request: Request, auth: dict = Depends(require_api_auth)) -> dict:
    """Re-enumerate tools from every configured MCP server.

    The manager's own docstring says a dead server "is retried on the next refresh",
    and until now nothing could trigger one: ``ensure_tools`` ran once, inside
    ``runtime.start()``. So a server that was down at boot stayed tool-less until the
    process restarted — the documented recovery path did not exist. That is the same
    defect shape as the rest of this round: a capability described in prose with no
    caller.

    Authorised as a config change (ADMIN), not as a read: it starts subprocesses and
    re-decides which tools the model may see.
    """
    auth_role = _role_of(auth)
    minimum = PERMISSION_MIN_ROLE.get(Permission.MANAGE_CONFIG, Role.OWNER)
    if auth_role.rank < minimum.rank:
        get_audit_log().record(
            kind="authz",
            action="mcp_refresh",
            outcome="deny",
            role=auth_role.value,
            detail=f"from={request.client.host if request.client else '-'}",
        )
        locale = request_locale(request)
        raise HTTPException(
            status_code=403,
            detail=t("api.role_required", locale, role=minimum.value),
        )

    runtime = _runtime()
    manager = getattr(runtime, "mcp", None)
    if manager is None:
        raise HTTPException(status_code=503, detail=t("api.mcp_disabled", request_locale(request)))

    await manager.ensure_tools()
    status = manager.status()
    # The servers' error strings and tool counts are the whole point of the response:
    # an operator who just pressed "reconnect" needs to know whether it worked.
    get_audit_log().record(
        kind="config",
        action="mcp_refresh",
        outcome="allow",
        role=auth_role.value,
        detail=f"tools={status.get('tools', 0)}",
    )
    logger.info("mcp tool refresh requested tools=%s", status.get("tools", 0))
    return {"ok": True, **status}


@router.get("/adapters")
async def list_adapters(_: dict = Depends(require_api_auth)) -> dict:
    """Configured adapters with live connection health."""
    runtime = _runtime()
    items = []
    for name, adapter in runtime.adapters.items():
        health = adapter.health
        items.append(
            {
                "name": name,
                "display_name": adapter.meta.display_name,
                "protocol": adapter.meta.protocol,
                "docs_url": adapter.meta.docs_url,
                "notes": adapter.meta.notes,
                "online": health.online,
                "last_error": health.last_error,
                "connected_at": health.connected_at,
                "reconnect_attempts": health.reconnect_attempts,
                "capabilities": sorted(str(c) for c in adapter.capabilities),
            }
        )
    return {"adapters": items, "count": len(items)}


@router.get("/providers")
async def list_providers(_: dict = Depends(require_api_auth)) -> dict:
    """Provider chain in failover order, with health counters."""
    runtime = _runtime()
    if runtime.providers is None:
        return {"providers": [], "stats": {}, "count": 0}
    providers = runtime.providers.list_providers()
    return {
        "providers": providers,
        "stats": runtime.providers.stats(),
        "count": len(providers),
    }


@router.get("/personas")
async def list_personas(_: dict = Depends(require_api_auth)) -> dict:
    """Installed persona cards and the group/user bindings in force."""
    runtime = _runtime()
    if runtime.personas is None:
        return {"personas": [], "binding": {}, "count": 0}
    store = runtime.personas
    binding = store.binding
    personas = []
    for persona in sorted(store.all(), key=lambda p: p.id):
        prompt = persona.system_prompt or ""
        personas.append(
            {
                "id": persona.id,
                "name": persona.name,
                "style": persona.style,
                "wake_words": list(persona.wake_words),
                "max_reply_chars": persona.max_reply_chars,
                "temperature": persona.temperature,
                "enabled": persona.enabled,
                "version": persona.version,
                "banned_words": list(persona.banned_words),
                "system_prompt": prompt[:_PROMPT_PREVIEW_CHARS],
                "system_prompt_truncated": len(prompt) > _PROMPT_PREVIEW_CHARS,
            }
        )
    return {
        "personas": personas,
        "count": len(personas),
        "binding": {
            "global_default": binding.global_default,
            "groups": dict(binding.groups),
            "users": dict(binding.users),
        },
    }


@router.get("/memory/sessions")
async def memory_sessions(
    limit: int = Query(50, ge=1, le=200),
    _: dict = Depends(require_api_auth),
) -> dict:
    """Archived conversations, most recent first."""
    runtime = _runtime()
    if runtime.memory is None:
        return {"sessions": [], "count": 0}
    sessions = await runtime.memory.list_sessions(limit=limit)
    return {"sessions": sessions, "count": len(sessions)}


@router.get("/memory/timeline")
async def memory_timeline(
    session_key: str = Query(..., min_length=1, max_length=200),
    limit: int = Query(50, ge=1, le=200),
    _: dict = Depends(require_api_auth),
) -> dict:
    """Messages of one session.

    ``session_key`` is a query parameter here — unlike the chat command of the same
    name, which pins it to the caller's own conversation. Reading another group's
    history is exactly what the operator token is for; the chat path must never gain
    that ability, which is why the two code paths do not share a helper.
    """
    runtime = _runtime()
    if runtime.memory is None:
        return {"session_key": session_key, "messages": [], "count": 0}
    try:
        rows = await runtime.memory.timeline(session_key, limit=limit)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    return {"session_key": session_key, "messages": rows, "count": len(rows)}


@router.get("/memory/stats")
async def memory_stats(_: dict = Depends(require_api_auth)) -> dict:
    """Row counts per memory layer, plus the most recent summary."""
    from soapbot.memory.store import MemoryLayer

    runtime = _runtime()
    if runtime.memory is None:
        return {"layers": {}, "total": 0}

    layers: dict[str, int] = {}
    for layer in MemoryLayer:
        try:
            layers[str(layer)] = await runtime.memory.count_memories(layer)
        except Exception:  # pragma: no cover - a single layer must not fail the page
            layers[str(layer)] = -1
    total = await runtime.memory.count_memories()
    return {"layers": layers, "total": total}


@router.get("/knowledge")
async def list_knowledge(_: dict = Depends(require_api_auth)) -> dict:
    """Uploaded documents and their chunk counts (titles only, no bodies)."""
    runtime = _runtime()
    if runtime.kb is None:
        return {"documents": [], "count": 0}
    documents = await runtime.kb.list_documents()
    return {"documents": documents, "count": len(documents)}


class KnowledgeDocumentIn(BaseModel):
    """One document as the operator types or pastes it."""

    title: str = Field(min_length=1, max_length=200)
    content: str = Field(min_length=1, max_length=200_000)
    doc_id: str = Field("", max_length=64)
    """Omit to create; supply an existing id to replace that document."""


@router.post("/knowledge")
async def upsert_knowledge(
    body: KnowledgeDocumentIn,
    request: Request,
    _: dict = Depends(require_api_auth),
) -> dict:
    """Create or replace a knowledge document.

    This endpoint is the missing half of the knowledge feature. ``ingest``,
    ``chunk``, ``add_document``, FTS indexing and vector storage all existed and
    were wired into retrieval; nothing in the service ever called the write side, so
    the knowledge page could only ever show an empty list. The capability was real
    and unreachable — the same shape as the other gaps this round fixed.

    ``content`` is capped at 200k characters. Not a product limit: the whole
    document is embedded in one call, and an unbounded upload is a way to make a
    single HTTP request occupy the embedding provider (and the bill) for minutes.
    """
    locale = request_locale(request)
    runtime = _runtime()
    if runtime.kb is None:
        raise HTTPException(status_code=503, detail=t("api.kb_disabled", locale))

    import hashlib

    doc_id = body.doc_id.strip() or (
        "doc-" + hashlib.sha256(f"{body.title}\n{body.content}".encode()).hexdigest()[:16]
    )
    if not _DOC_ID_RE.match(doc_id):
        raise HTTPException(status_code=400, detail=t("api.doc_id_invalid", locale))

    result = await runtime.kb.ingest_document(doc_id, body.title.strip(), body.content)
    if result["chunks"] == 0:
        raise HTTPException(status_code=400, detail=t("api.content_empty", locale))
    return {"ok": True, **result}


@router.delete("/knowledge/{doc_id}")
async def delete_knowledge(
    doc_id: str, request: Request, _: dict = Depends(require_api_auth)
) -> dict:
    locale = request_locale(request)
    runtime = _runtime()
    if runtime.kb is None:
        raise HTTPException(status_code=503, detail=t("api.kb_disabled", locale))
    removed = await runtime.kb.delete_document(doc_id)
    if removed == 0:
        raise HTTPException(status_code=404, detail=t("api.doc_not_found", locale))
    return {"ok": True, "doc_id": doc_id, "chunks_removed": removed}


@router.get("/knowledge/{doc_id}")
async def knowledge_detail(
    doc_id: str, request: Request, _: dict = Depends(require_api_auth)
) -> dict:
    locale = request_locale(request)
    runtime = _runtime()
    if runtime.kb is None:
        raise HTTPException(status_code=503, detail=t("api.kb_disabled", locale))
    detail = await runtime.kb.document_detail(doc_id)
    if detail is None:
        raise HTTPException(status_code=404, detail=t("api.doc_not_found", locale))
    return detail


@router.get("/budget")
async def budget_view(
    status: str = Query("", description="pending / approved / denied / expired / reserved"),
    limit: int = Query(100, ge=1, le=500),
    session_key: str = Query("", max_length=200),
    _: dict = Depends(require_api_auth),
) -> dict:
    """Spend requests across scopes, plus the policy in force.

    Only reachable with an operator credential; see ``BudgetStore.list_requests`` for
    why the store method is separate from the chat-scoped ones.
    """
    runtime = _runtime()
    if runtime.budget is None:
        return {"enabled": False, "requests": [], "policy": {}}
    policy = runtime.budget.policy
    requests = await runtime.budget.list_requests(
        status=status, limit=limit, session_key=session_key
    )
    return {
        "enabled": True,
        "policy": {
            "currency": policy.currency,
            "period": policy.period,
            "period_cap_minor": policy.period_cap_minor,
            "per_request_cap_minor": policy.per_request_cap_minor,
            "request_ttl_seconds": policy.request_ttl_seconds,
            "period_key": policy.period_key(),
        },
        "requests": [
            {
                "id": r.id,
                "amount_minor": r.amount_minor,
                "currency": r.currency,
                "purpose": r.purpose,
                "session_key": r.session_key,
                "requester_id": r.requester_id,
                "requester_name": r.requester_name,
                "status": str(r.status),
                "period": r.period,
                "created_at": r.created_at,
                "expires_at": r.expires_at,
                "decided_at": r.decided_at,
                "decided_by": r.decided_by,
                "decision_note": r.decision_note,
            }
            for r in requests
        ],
        "count": len(requests),
    }


@router.get("/logs")
async def recent_logs(
    limit: int = Query(200, ge=1, le=2000),
    level: str = Query("", description="minimum level: DEBUG / INFO / WARNING / ERROR"),
    contains: str = Query("", max_length=200),
    _: dict = Depends(require_api_auth),
) -> dict:
    """Tail of the in-process log ring buffer.

    Served from the bounded ring (``logging_setup``) rather than the log file: reading
    the file would let a caller walk arbitrary amounts of it, and it may not exist on a
    read-only container filesystem.
    """
    from soapbot.logging_setup import get_ring

    levels = {"DEBUG": 10, "INFO": 20, "WARNING": 30, "ERROR": 40, "CRITICAL": 50}
    floor = levels.get(level.upper(), 0)
    needle = contains.lower()

    entries = list(get_ring())
    if floor:
        entries = [e for e in entries if levels.get(str(e.get("level", "")), 0) >= floor]
    if needle:
        entries = [e for e in entries if needle in str(e.get("msg", "")).lower()]
    return {"entries": entries[-limit:], "count": min(len(entries), limit), "total": len(entries)}


@router.get("/access")
async def access_matrix(_: dict = Depends(require_api_auth)) -> dict:
    """Effective permission floors and the configured authority lists.

    The WebUI shows this next to the login screen so an operator can see why "admin"
    cannot approve spending without reading the source.
    """
    from soapbot.core.builder import build_authority

    authority = build_authority()
    return {
        "permissions": [
            {"name": p.value, "min_role": PERMISSION_MIN_ROLE.get(p, Role.OWNER).value}
            for p in Permission
        ],
        "roles": [{"name": r.value, "rank": r.rank} for r in sorted(Role, key=lambda r: r.rank)],
        "owners": sorted(authority.owners),
        "admins": sorted(authority.admins),
        "members": sorted(authority.members),
        "trust_protocol_roles": bool(authority.trust_protocol_roles),
        "generated_at": time.time(),
    }


def _settings() -> Any:
    from soapbot.config import settings

    return settings
