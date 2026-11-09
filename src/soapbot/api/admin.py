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

Persona cards *are* writable, and the objection above — "a form that renders them as
fields would silently drop the prose between the front matter and the body" — is
answered by not rendering them as fields. The card is edited as the file it is: the
prompt is a textarea holding the body verbatim, the front matter is a small set of
inputs, and the save path re-serialises with :func:`soapbot.ai.persona.dump_persona_file`
so unknown front-matter keys survive. The alternative was what actually shipped: a
"persona card" feature whose only editor was a text editor over SSH, on a box the
operator reaches through this panel.

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

import asyncio
import logging
import re
import time
from typing import Any

from fastapi import APIRouter, Depends, HTTPException, Query, Request
from pydantic import BaseModel, Field

from soapbot import __version__
from soapbot.api.auth import require_api_auth, require_role
from soapbot.api.errors import safe_detail
from soapbot.api.locale import request_locale
from soapbot.api.service_hint import restart_hint
from soapbot.i18n import t
from soapbot.security.audit import get_audit_log
from soapbot.security.principal import PERMISSION_MIN_ROLE, Permission, Role

logger = logging.getLogger(__name__)
# Every management read needs an identified caller. In strict mode an unauthenticated
# loopback GET is only MEMBER, which is enough to see the views but not enough for
# any write — authenticate() refuses those before a handler runs. Individual
# handlers below keep their own stricter permission checks where they change state.
router = APIRouter(prefix="/api", tags=["admin"], dependencies=[Depends(require_role(Role.MEMBER))])


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


def _require_doc_id(value: str, locale: str = "") -> str:
    """One validator for every doc_id entry point.

    Two of the four handlers used to skip this check. They reached a parameterised
    SQL query rather than a filesystem path, so the practical risk was low — but
    "low" was an accident of the storage layer, and the next backend to use the id
    as a key would have inherited an unvalidated value. Validation belongs at the
    boundary, not in whichever store happens to be installed today.
    """
    candidate = (value or "").strip()
    if not _DOC_ID_RE.match(candidate):
        raise HTTPException(status_code=400, detail=t("api.doc_id_invalid", locale))
    return candidate


def _runtime():
    from soapbot.app import get_runtime

    runtime = get_runtime()
    if runtime is None:
        raise HTTPException(status_code=503, detail="bot runtime is not initialised")
    return runtime


def _scheduler():
    from soapbot.app import get_scheduler

    return get_scheduler()


def _breaker_status(runtime) -> dict[str, Any]:
    """Circuit-breaker state, or a closed one when no router is available."""
    router = getattr(getattr(runtime, "engine", None), "router", None)
    if router is None or not hasattr(router, "breaker_status"):
        return {"open": False, "retry_after": 0.0, "consecutive_total_failures": 0}
    return router.breaker_status()


def _quota_status(runtime) -> dict[str, Any]:
    """Per-user quota configuration and how many turns it refused.

    Counts only — never the limiter's keys, which are user ids.
    """
    pipeline = getattr(runtime, "pipeline", None)
    stages = getattr(pipeline, "stages", None) or []
    for stage in stages:
        if getattr(stage, "name", "") == "model_quota" and hasattr(stage, "status"):
            return stage.status()
    return {"limit": 0, "window_seconds": 0.0, "refused": 0}


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
        # Two states that used to be invisible from here. Both are failures the bot
        # absorbs silently: the breaker answers with a notice, the quota refuses quietly
        # from the user's side. Without them the panel shows a healthy bot that talks to
        # nobody, and the first diagnosis is "the model is bad".
        "breaker": _breaker_status(runtime),
        "quota": _quota_status(runtime),
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
                # ``silent_for`` is what turns a false green light into a visible one:
                # a socket can stay ESTABLISHED forever after the peer stops answering,
                # and ``online`` alone reported exactly that as healthy for seventeen
                # hours. The number is seconds since the last frame or successful probe,
                # so the panel can say "last heard from 6h ago" instead of "online".
                "last_seen_at": health.last_seen_at,
                "silent_for": (
                    round(time.time() - health.last_seen_at, 1)
                    if health.last_seen_at
                    else None
                ),
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
async def list_personas(
    request: Request, auth: dict[str, Any] = Depends(require_api_auth)
) -> dict:
    """Installed persona cards and the group/user bindings in force.

    Even truncated, this is configuration: 4000 characters of the body plus the style,
    the banned-word list and the wake words. Guarded like the write path — see
    :func:`_require_persona_access`.
    """
    _require_persona_access(auth, request, action="persona_read")
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


class PersonaBindingPatch(BaseModel):
    """Which card applies in which group: ``群号:人格ID`` pairs, comma separated.

    A string rather than a map because that is the shape ``.env`` can hold, and the
    panel's write path goes through ``_rewrite_env`` like every other setting. Keeping
    one representation avoids a second parser that would accept what the first rejects.
    """

    group_personas: str = ""


@router.post("/personas/binding")
async def write_persona_binding(
    payload: PersonaBindingPatch, request: Request, auth: dict[str, Any] = Depends(require_api_auth)
) -> dict:
    """Persist the per-group bindings; they take effect on the next start.

    Validated against the cards that actually exist before writing. A typo used to be
    dropped silently at load time, which reads as "the binding does not work" — the
    person has no way to tell a wrong ID from a broken feature.
    """
    from soapbot.api.settings import _env_path
    from soapbot.core import config_write
    from soapbot.security.principal import Role

    role = _role_of(auth)
    locale = request_locale(request)
    if role.rank < Role.ADMIN.rank:
        raise HTTPException(status_code=403, detail=t("api.role_required", locale, role="admin"))

    raw = payload.group_personas.strip()
    runtime = _runtime()
    known = {p.id for p in runtime.personas.all()} if runtime.personas else set()

    pairs: list[str] = []
    for pair in raw.replace("；", ";").replace(",", ";").split(";"):
        pair = pair.strip()
        if not pair:
            continue
        if ":" not in pair:
            raise HTTPException(
                status_code=400, detail=t("api.personaBindingFormat", locale, pair=pair)
            )
        group_id, _, persona_id = pair.partition(":")
        group_id = group_id.strip()
        persona_id = persona_id.strip()
        if not group_id.isdigit():
            raise HTTPException(
                status_code=400, detail=t("api.personaBindingGroup", locale, pair=pair)
            )
        if known and persona_id not in known:
            raise HTTPException(
                status_code=400, detail=t("api.personaBindingUnknown", locale, id=persona_id)
            )
        pairs.append(f"{group_id}:{persona_id}")

    value = ",".join(pairs)
    path = _env_path()
    try:
        config_write.write_env_updates(path, {"SOAPBOT_GROUP_PERSONAS": value})
    except OSError as exc:
        raise HTTPException(status_code=500, detail=t("api.write_failed", locale)) from exc

    get_audit_log().record(
        kind="config",
        action="persona_binding_write",
        outcome="allow",
        role=role.value,
        detail=f"bindings={len(pairs)}",
    )
    return {"ok": True, "restart_required": True, "group_personas": value}


class PersonaWrite(BaseModel):
    """One persona card, as the panel's editor holds it.

    ``system_prompt`` is the Markdown body verbatim — not a summary, not a preview.
    ``id`` is validated against ``_DOC_ID_RE`` before it can become a filename.
    """

    id: str = Field(min_length=1, max_length=64)
    name: str = ""
    system_prompt: str = ""
    style: str = ""
    wake_words: list[str] = Field(default_factory=list)
    banned_words: list[str] = Field(default_factory=list)
    max_reply_chars: int = Field(default=500, ge=0, le=8000)
    temperature: float | None = Field(default=None, ge=0.0, le=2.0)
    enabled: bool = True
    locale: str = ""


def _require_persona_access(
    auth: dict[str, Any], request: Request, *, action: str = "persona_write"
) -> Role:
    """Reading a persona card is a config action, not a chat action.

    The card's body *is* the first section of the system prompt (``Persona`` is what
    ``Engine._system_prompt`` starts from), and the detail endpoint returns it verbatim.
    Before this, that read required only ``require_api_auth`` while writing the same file
    required ``MANAGE_CONFIG`` — so the text the bot is instructed by was easier to read
    than to change, and any future role-scoped token would have been able to read the
    operator's configuration without being allowed to touch it.

    ``action`` distinguishes read from write in the audit trail; the threshold is the same
    because both operate on the same file.
    """
    role = _role_of(auth)
    minimum = PERMISSION_MIN_ROLE.get(Permission.MANAGE_CONFIG, Role.OWNER)
    if role.rank < minimum.rank:
        get_audit_log().record(
            kind="authz",
            action=action,
            outcome="deny",
            role=role.value,
            detail=f"from={request.client.host if request.client else '-'}",
        )
        raise HTTPException(
            status_code=403,
            detail=t("api.role_required", request_locale(request), role=minimum.value),
        )
    return role


def _require_persona_write(auth: dict[str, Any], request: Request) -> Role:
    return _require_persona_access(auth, request, action="persona_write")


@router.get("/personas/{persona_id}")
async def read_persona(
    persona_id: str, request: Request, auth: dict[str, Any] = Depends(require_api_auth)
) -> dict:
    """The full card, body included.

    The list endpoint truncates the prompt to keep the table light; an editor cannot
    work from a truncated prompt, and saving one back would destroy the rest of it.

    Untruncated is exactly why this needs the config permission: the returned body is the
    text the model is instructed by, and it was previously readable by any authenticated
    caller while writing it required ``MANAGE_CONFIG``.
    """
    _require_persona_access(auth, request, action="persona_read")
    runtime = _runtime()
    if runtime.personas is None:
        raise HTTPException(status_code=503, detail="persona store is not initialised")
    persona = runtime.personas.get(persona_id)
    if persona is None:
        raise HTTPException(status_code=404, detail=f"no persona {persona_id!r}")
    return {
        "id": persona.id,
        "name": persona.name,
        "system_prompt": persona.system_prompt,
        "style": persona.style,
        "wake_words": list(persona.wake_words),
        "banned_words": list(persona.banned_words),
        "max_reply_chars": persona.max_reply_chars,
        "temperature": persona.temperature,
        "enabled": persona.enabled,
        "locale": persona.locale,
        "version": persona.version,
        "file": str(runtime.personas.path_for(persona.id) or ""),
    }


@router.post("/personas")
async def write_persona(
    payload: PersonaWrite,
    request: Request,
    auth: dict = Depends(require_api_auth),
) -> dict:
    """Create or replace a card, then apply it to the running bot immediately.

    Unlike the ``.env`` settings, this needs no restart: the persona store is the object
    the pipeline reads on every message, so updating it *is* the apply. Saying
    "restart required" here would be a lie that costs the operator a restart.
    """
    from soapbot.ai.persona import Persona

    role = _require_persona_write(auth, request)
    locale = request_locale(request)

    pid = payload.id.strip()
    if not _DOC_ID_RE.match(pid):
        raise HTTPException(status_code=400, detail=t("api.personaIdInvalid", locale))

    runtime = _runtime()
    store = runtime.personas
    if store is None:
        raise HTTPException(status_code=503, detail="persona store is not initialised")

    existing = store.get(pid)
    persona = Persona(
        id=pid,
        name=payload.name.strip() or pid,
        system_prompt=payload.system_prompt.strip(),
        style=payload.style.strip(),
        banned_words=[w.strip() for w in payload.banned_words if w.strip()],
        wake_words=[w.strip() for w in payload.wake_words if w.strip()],
        max_reply_chars=payload.max_reply_chars,
        temperature=payload.temperature,
        enabled=payload.enabled,
        locale=payload.locale.strip(),
        # Keep the version counter moving so a cached prompt can be invalidated, and
        # keep any front-matter key this form does not know about.
        version=(existing.version + 1) if existing else 1,
        extra=dict(existing.extra) if existing else {},
    )

    try:
        path = store.save(persona)
    except (OSError, RuntimeError) as exc:
        # RuntimeError is "this store has nowhere to write" — a wiring fault, not a
        # client error, but it must not escape as a bare 500 with no audit trail.
        get_audit_log().record(
            kind="config",
            action="persona_write",
            outcome="deny",
            role=role.value,
            detail=f"write_failed:{exc.__class__.__name__}",
        )
        raise HTTPException(status_code=500, detail=t("api.write_failed", locale)) from exc

    get_audit_log().record(
        kind="config",
        action="persona_write",
        outcome="allow",
        role=role.value,
        detail=f"id={pid} chars={len(persona.system_prompt)}",
    )
    return {
        "ok": True,
        "id": pid,
        "file": str(path),
        "version": persona.version,
        # The store the pipeline reads was updated in place, so the next message uses
        # this card. No restart, and the panel can say so.
        "applied": True,
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
        raise HTTPException(status_code=400, detail=safe_detail(400, exc, "admin")) from exc
    return {"session_key": session_key, "messages": rows, "count": len(rows)}


@router.get("/memory/stats")
async def memory_stats(_: dict = Depends(require_api_auth)) -> dict:
    """Row counts per memory layer, plus the most recent summary."""
    from soapbot.memory.store import MemoryLayer

    runtime = _runtime()
    if runtime.memory is None:
        return {"layers": {}, "total": 0}

    # One `GROUP BY` instead of one `COUNT` per layer. The loop cost four to five round
    # trips for a single screen, and each one could observe a different snapshot, so the
    # total and the sum of its parts could disagree under load. `-1` still means "this
    # screen could not read the counts", not "zero rows" — the panel renders the two
    # differently, and collapsing them would make a broken read look like an empty layer.
    try:
        counts = await runtime.memory.count_by_layer()
        layers = {str(layer): counts.get(str(layer), 0) for layer in MemoryLayer}
    except Exception:  # pragma: no cover - a count must not fail the page
        logger.warning("memory layer counts failed", exc_info=True)
        layers = {str(layer): -1 for layer in MemoryLayer}
    total = sum(count for count in layers.values() if count >= 0)
    return {"layers": layers, "total": total}


@router.get("/memory/items")
async def memory_items(
    request: Request,
    scope: str = Query("", max_length=200),
    layer: str = Query("", max_length=16),
    limit: int = Query(50, ge=1, le=200),
    offset: int = Query(0, ge=0),
    auth: dict = Depends(require_api_auth),
) -> dict:
    """The memory rows themselves, newest first.

    Separate from ``/memory/timeline``, which returns archived *messages*. The two were
    conflated in the panel's mental model — "the memory page shows what the bot
    remembers" — but a message is what was said and a memory is what was distilled from
    it, and only the latter can be deleted by id.

    Gated on ``MANAGE_CONFIG`` like the scene endpoints: memory content is verbatim
    conversation, which is the most private data in the system. A read-only member
    listing every scope would be a worse leak than the one the scene gate closed.
    """
    _require_scene_access(auth, request, action="memory_list")
    runtime = _runtime()
    store = runtime.memory
    if store is None:
        return {"memories": [], "count": 0}

    from soapbot.memory.store import MemoryLayer

    wanted: MemoryLayer | None = None
    if layer:
        try:
            wanted = MemoryLayer(layer)
        except ValueError as exc:
            raise HTTPException(
                status_code=400,
                detail=t("api.layer_invalid", request_locale(request), layer=layer),
            ) from exc

    items = await store.list_memories(
        scope=scope.strip(), layer=wanted, limit=limit, offset=offset
    )
    return {
        "memories": [
            {
                "id": item.id,
                "layer": item.layer,
                "scope": item.scope,
                "subject": item.subject,
                "content": item.content,
                "importance": item.importance,
                "created_at": item.created_at,
            }
            for item in items
        ],
        "count": len(items),
        "offset": offset,
        "limit": limit,
    }


@router.delete("/memory/{memory_id}")
async def delete_memory(
    memory_id: int,
    request: Request,
    auth: dict[str, Any] = Depends(require_api_auth),
) -> dict:
    """Delete one memory row by id.

    The panel could list memories but never remove one, so a wrong or stale memory had
    exactly one removal path: typing ``/forget <id>`` into the group chat. That is the
    wrong audience — the operator reading the memory page is the person who noticed the
    problem, and the chat command is also scoped to the *caller's* conversation, which
    an operator is usually not in.

    Two rules carried over from ``/forget``, because they are the reason that command is
    safe:

    * **Ownership is checked before the delete.** An integer id is trivially enumerable,
      so the endpoint must not delete by primary key alone.
    * **"Missing" and "not yours" answer identically** — same status, same text. A
      distinct 403 for the second case would turn this into an existence oracle, which
      is precisely the probe ``/forget`` was fixed to close.

    Unlike ``/forget`` the operator token reaches every scope: the panel is already
    showing those rows, and hiding the delete behind a scope the caller cannot name
    would make the button a decoration. The audit entry records the scope, never the
    content.
    """
    role = _role_of(auth)
    minimum = PERMISSION_MIN_ROLE.get(Permission.MANAGE_MEMORY, Role.ADMIN)
    locale = request_locale(request)
    if role.rank < minimum.rank:
        get_audit_log().record(
            kind="authz",
            action="memory_delete",
            outcome="deny",
            role=role.value,
            detail=f"from={request.client.host if request.client else '-'}",
        )
        raise HTTPException(
            status_code=403, detail=t("api.role_required", locale, role=minimum.value)
        )

    runtime = _runtime()
    store = runtime.memory
    if store is None:
        raise HTTPException(status_code=503, detail=t("api.memory_disabled", locale))

    item = await store.get_memory(memory_id)
    if item is None:
        get_audit_log().record(
            kind="memory",
            action="memory_delete",
            outcome="deny",
            role=role.value,
            detail=f"id={memory_id} missing",
        )
        raise HTTPException(status_code=404, detail=t("api.memory_not_found", locale))

    removed = await store.delete_memory(memory_id)
    if not removed:
        # Lost a race with another deleter. Same answer as "never existed": the caller's
        # intent is satisfied, and a different message would describe our concurrency.
        raise HTTPException(status_code=404, detail=t("api.memory_not_found", locale))

    # The card and portrait were derived from this row, so they now describe evidence
    # that no longer exists. Best-effort: the delete already happened, and reporting a
    # failure here would make the operator retry a delete that succeeded.
    scene = getattr(runtime, "scene", None)
    if scene is not None and item.scope:
        try:
            await scene.unlink_all(memory_id)
            await scene.refresh(item.scope)
        except Exception as exc:  # pragma: no cover - derived view must not fail the call
            logger.warning("scene refresh failed after memory delete: %s", exc)

    get_audit_log().record(
        kind="memory",
        action="memory_delete",
        outcome="allow",
        role=role.value,
        detail=f"id={memory_id} scope={item.scope or '-'}",
    )
    return {"ok": True, "id": memory_id}


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
    doc_id = _require_doc_id(doc_id, locale)

    result = await runtime.kb.ingest_document(doc_id, body.title.strip(), body.content)
    if result["chunks"] == 0:
        raise HTTPException(status_code=400, detail=t("api.content_empty", locale))
    return {"ok": True, **result}


@router.delete("/knowledge/{doc_id}")
async def delete_knowledge(
    doc_id: str, request: Request, _: dict = Depends(require_api_auth)
) -> dict:
    locale = request_locale(request)
    doc_id = _require_doc_id(doc_id, locale)
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
    doc_id = _require_doc_id(doc_id, locale)
    runtime = _runtime()
    if runtime.kb is None:
        raise HTTPException(status_code=503, detail=t("api.kb_disabled", locale))
    detail = await runtime.kb.document_detail(doc_id)
    if detail is None:
        raise HTTPException(status_code=404, detail=t("api.doc_not_found", locale))
    return detail


# --------------------------------------------------------------------- scene layer
#
# The scene layer existed, was tested, and was injected into every prompt — and had no
# interface at all. The only way to see a card was to read the database, and the only way
# to produce a skill was to call ``SkillForge`` from a REPL. That is the same shape as the
# knowledge-base gap this module already fixed: a capability that is real, wired into the
# pipeline, and unreachable from the panel that is supposed to describe it.
#
# Three rules govern the endpoints below:
#
# * **Rebuild is explicit.** ``refresh`` recomputes from stored memories; it never invents
#   anything. The card and portrait are derived views, so "regenerate" cannot produce a
#   summary the evidence does not support.
# * **Skills are files.** Generating one writes a Markdown file under the data volume,
#   which is why deletion goes through ``SkillForge.delete`` rather than the database.
# * **A scene is private.** A card is a summary of one conversation and a skill body is
#   *verbatim* memory content from it. Both are more sensitive than a persona card, and
#   the persona read already requires ``MANAGE_CONFIG``. Requiring only
#   ``require_api_auth`` here would have made the most private data in the system the
#   easiest to read — and ``/memory/scenes`` enumerates every scope, so the leak needs no
#   guessing.


def _require_scene_access(
    auth: dict[str, Any], request: Request, *, action: str = "scene_read"
) -> Role:
    """Gate every scene/skill endpoint on the config permission.

    The reasoning mirrors :func:`_require_persona_access`, and the conclusion is stronger:
    a persona card is text the operator wrote, while a scene card is a summary of what a
    group actually said and a skill body is quoted memory content. If the former needs
    ``MANAGE_CONFIG`` to read, the latter cannot need less.

    Reads are gated too, not just writes. ``/memory/scenes`` lists every scope, so a
    read-only leak is one request away from a full enumeration — gating only the mutation
    endpoints would leave the enumeration open.
    """
    role = _role_of(auth)
    minimum = PERMISSION_MIN_ROLE.get(Permission.MANAGE_CONFIG, Role.OWNER)
    if role.rank < minimum.rank:
        get_audit_log().record(
            kind="authz",
            action=action,
            outcome="deny",
            role=role.value,
            detail=f"from={request.client.host if request.client else '-'}",
        )
        raise HTTPException(
            status_code=403,
            detail=t("api.role_required", request_locale(request), role=minimum.value),
        )
    return role


def _scene_pair_or_503():
    """The scene layer and the forge, or a 503 naming the one that is missing.

    Returned together because ``build_runtime`` creates both or neither — but the message
    still names the missing field, because a hand-assembled runtime (tests, scripts) can
    have one without the other, and "skill forge is not initialised" sends an operator to
    check the wrong thing when it is the scene layer that is absent.
    """
    runtime = _runtime()
    scene = getattr(runtime, "scene", None)
    if scene is None:
        raise HTTPException(status_code=503, detail="scene layer is not initialised")
    return scene, getattr(runtime, "skills", None)


def _forge_or_503():
    runtime = _runtime()
    forge = getattr(runtime, "skills", None)
    if forge is None:
        raise HTTPException(status_code=503, detail="skill forge is not initialised")
    return forge


def _checked_scope(scope: str, request: Request) -> str:
    """Reject a scope that cannot name a folder, before any filesystem call.

    Without this, an invalid scope produced three different answers from four endpoints:
    ``/skills`` and ``/skills/candidates`` returned empty lists (because ``load`` swallows
    an unsafe scope), while ``POST /skills`` raised ``ValueError`` out of ``save`` and
    surfaced as a 500. Same input, three statuses — and the empty list is the worst of
    them, because it reads as "this scene has no skills" rather than "you asked for
    something that cannot exist".
    """
    from soapbot.memory.skills import _safe_scope

    if not _safe_scope(scope):
        raise HTTPException(
            status_code=400, detail=t("api.scope_invalid", request_locale(request))
        )
    return scope


@router.get("/memory/scenes")
async def memory_scenes(
    request: Request,
    limit: int = Query(100, ge=1, le=500),
    auth: dict = Depends(require_api_auth),
) -> dict:
    """Every conversation the bot has memories for, with its card state.

    Driven by memories rather than by stored cards: a scope with memories and no card is
    the case the panel most needs to show, because it is the one an operator can act on.
    """
    _require_scene_access(auth, request, action="scene_list")
    rows = await _scene_pair_or_503()[0].list_scenes(limit=limit)
    return {"scenes": rows, "count": len(rows)}


@router.get("/memory/scene")
async def memory_scene(
    request: Request,
    scope: str = Query(..., min_length=1, max_length=200),
    auth: dict = Depends(require_api_auth),
) -> dict:
    """The stored card and portrait for one scope.

    ``None`` for either is a real answer, not an error: a conversation can hold memories
    and have no card yet, and the panel renders that as "not built" rather than as a
    failure. Returning 404 would make the normal first-visit case look broken.
    """
    _require_scene_access(auth, request, action="scene_read")
    scene, _forge = _scene_pair_or_503()
    card = await scene.get_card(scope)
    portrait = await scene.get_portrait(scope)
    return {
        "scope": scope,
        "card": _card_json(card),
        "portrait": _portrait_json(portrait),
    }


@router.post("/memory/scene/refresh")
async def memory_scene_refresh(
    request: Request,
    scope: str = Query(..., min_length=1, max_length=200),
    auth: dict = Depends(require_api_auth),
) -> dict:
    """Rebuild and persist the card and portrait from stored memories.

    Idempotent and cheap to repeat: both views are derived, so a second call over
    unchanged evidence produces the same result. The portrait is *dropped* rather than
    kept when the scope falls below the evidence threshold, which is what makes this safe
    to run after a deletion.

    ``portrait`` is ``None`` when withheld, matching what ``GET /memory/scene`` returns
    for the same state. Returning an empty-but-present portrait here meant the panel
    rendered a portrait block with no content after a rebuild, and then made it disappear
    on the next read — the same state, two shapes, from two endpoints.
    """
    _require_scene_access(auth, request, action="scene_refresh")
    scene, _forge = _scene_pair_or_503()
    card, portrait = await scene.refresh(scope)
    withheld = portrait.confidence <= 0.0
    return {
        "ok": True,
        "scope": scope,
        "card": _card_json(card),
        "portrait": None if withheld else _portrait_json(portrait),
        "portrait_withheld": withheld,
    }


def _card_json(card: Any) -> dict | None:
    if card is None:
        return None
    return {
        "scope": card.scope,
        "title": card.title,
        "summary": card.summary,
        "topics": list(card.topics),
        "people": list(card.people),
        "memory_count": card.memory_count,
        "updated_at": card.updated_at,
        # The rendered form is what the model actually receives. Showing it verbatim is
        # the difference between "the panel describes the feature" and "the panel shows
        # the artefact" — an operator can see the exact text and the token cost.
        "prompt": card.to_prompt(),
    }


def _portrait_json(portrait: Any) -> dict | None:
    if portrait is None:
        return None
    return {
        "scope": portrait.scope,
        "headline": portrait.headline,
        "themes": list(portrait.themes),
        "tone": portrait.tone,
        "recurring_questions": list(portrait.recurring_questions),
        "memory_count": portrait.memory_count,
        "confidence": portrait.confidence,
        "updated_at": portrait.updated_at,
        "prompt": portrait.to_prompt(),
    }


@router.get("/memory/skills")
async def memory_skills(
    request: Request,
    scope: str = Query(..., min_length=1, max_length=200),
    auth: dict = Depends(require_api_auth),
) -> dict:
    """Skills stored for one scene.

    Scoped by construction: ``SkillForge.load`` reads exactly one folder, and there is no
    "all skills" endpoint on purpose. A private skill that any scope could enumerate would
    not be private, and the leak would be silent — the content would simply appear in a
    list nobody expected to be cross-scope.

    A skill body is *verbatim memory content*, which is why this read is gated as tightly
    as the write.
    """
    _require_scene_access(auth, request, action="skill_read")
    _checked_scope(scope, request)
    forge = _forge_or_503()
    # `load` walks the directory and reads every `.md` synchronously. Inline, that walk
    # held the event loop for its whole duration; on a scope with a few hundred skills
    # every other panel request queued behind it.
    skills = await asyncio.to_thread(forge.load, scope)
    return {
        "scope": scope,
        "skills": [
            {
                "skill_id": s.skill_id,
                "title": s.title,
                "body": s.body,
                "support": s.support,
                "confidence": s.confidence,
                # Relative to the skills root, not the bare file name: the name alone is
                # ambiguous across scopes (every scene has its own folder), so an operator
                # reading "部署.md" would not know which conversation's file it is.
                "file": _relative_to_root(s.path, forge.root),
            }
            for s in skills
        ],
        "count": len(skills),
    }


def _relative_to_root(path: Any, root: Any) -> str:
    """Path relative to the skills root, for display. Empty when unknown.

    The fallback is empty, not ``path.name``. A path outside the root means the guard in
    ``save`` failed, and in that case the *name* is still a leak of host layout — the one
    input this helper exists to handle is the one where it must say nothing.
    """
    if path is None:
        return ""
    try:
        return path.relative_to(root).as_posix()
    except ValueError:
        return ""


@router.get("/memory/skills/candidates")
async def memory_skill_candidates(
    request: Request,
    scope: str = Query(..., min_length=1, max_length=200),
    auth: dict = Depends(require_api_auth),
) -> dict:
    """Clusters that would become skills, without writing anything.

    Separate from generation so the operator can see *why* a skill would exist — which
    memories, which topic — before a file appears on disk. The whole design argument for
    keyword clustering over embeddings is that this list is checkable by a human; hiding
    it behind a one-click "generate" would throw that away.
    """
    _require_scene_access(auth, request, action="skill_candidates")
    _checked_scope(scope, request)
    scene, forge = _scene_pair_or_503()
    if forge is None:
        raise HTTPException(status_code=503, detail="skill forge is not initialised")

    triples = await scene.evidence(scope)
    candidates = forge.candidates(triples)
    existing = {s.skill_id for s in forge.load(scope)}
    return {
        "scope": scope,
        "candidates": [
            {
                "topic": c.topic,
                "support": c.support,
                "memories": list(c.memories),
                # Already on disk: the panel offers "regenerate" instead of "create", so
                # the button does not silently overwrite a skill the operator hand-edited.
                "exists": _skill_id_for(c.topic) in existing,
            }
            for c in candidates
        ],
        "count": len(candidates),
    }


def _skill_id_for(topic: str) -> str:
    """The file name a topic would produce.

    Imported from the forge rather than reimplemented: the slug rule (digest on
    truncation, digest on case collision) is exactly the kind of detail that drifts when
    copied, and a drifted copy here would report "not created yet" for a skill that
    exists.
    """
    from soapbot.memory.skills import _slug

    return _slug(topic)


class SkillGenerateIn(BaseModel):
    """One topic to promote into a skill."""

    scope: str = Field(min_length=1, max_length=200)
    topic: str = Field(min_length=1, max_length=200)


@router.post("/memory/skills")
async def memory_skill_generate(
    body: SkillGenerateIn,
    request: Request,
    auth: dict = Depends(require_api_auth),
) -> dict:
    """Write a skill for one topic, from the memories that support it.

    The topic is re-derived from stored evidence rather than trusted from the request: a
    caller could otherwise name a topic that no memory supports and get a skill whose body
    is empty. Re-running detection and picking the matching candidate makes the request a
    *selection*, not an assertion.

    Matching is on the **slug**, not the raw topic, because the slug is what names the
    file. Two different topics can slug to the same name — ``部署 脚本`` and ``部署-脚本``
    both become ``部署-脚本`` — and comparing topics would let the second one pass the
    "is this a real candidate" check and then overwrite the first one's file. Comparing
    slugs means the request names the file it will replace, which is also what the panel
    shows the operator.
    """
    locale = request_locale(request)
    _require_scene_access(auth, request, action="skill_generate")
    _checked_scope(body.scope, request)
    scene, forge = _scene_pair_or_503()
    if forge is None:
        raise HTTPException(status_code=503, detail="skill forge is not initialised")

    wanted = _skill_id_for(body.topic)
    triples = await scene.evidence(body.scope)
    match = next((c for c in forge.candidates(triples) if _skill_id_for(c.topic) == wanted), None)
    if match is None:
        raise HTTPException(status_code=404, detail=t("api.skill_no_evidence", locale))

    skill = forge.build(body.scope, match)
    # Same reason as the read above: mkdir + write_text on the request's own thread.
    path = await asyncio.to_thread(forge.save, skill)
    return {
        "ok": True,
        "scope": body.scope,
        "skill_id": skill.skill_id,
        "title": skill.title,
        "support": skill.support,
        "file": _relative_to_root(path, forge.root),
    }


@router.delete("/memory/skills/{skill_id}")
async def memory_skill_delete(
    skill_id: str,
    request: Request,
    scope: str = Query(..., min_length=1, max_length=200),
    auth: dict = Depends(require_api_auth),
) -> dict:
    """Delete one skill file.

    ``scope`` is a query parameter, not part of the path, because a skill id is only
    unique *within* a scope — two groups can both have a skill called ``部署``, and a path
    of ``/skills/部署`` would be ambiguous. Requiring the scope makes the deletion name
    exactly one file.
    """
    locale = request_locale(request)
    _require_scene_access(auth, request, action="skill_delete")
    _checked_scope(scope, request)
    forge = _forge_or_503()
    if not forge.delete(scope, skill_id):
        raise HTTPException(status_code=404, detail=t("api.skill_not_found", locale))
    return {"ok": True, "scope": scope, "skill_id": skill_id}


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
    auth: dict = Depends(require_api_auth),
) -> dict:
    """Tail of the in-process log ring buffer, with role-filtered details.

    Served from the bounded ring (``logging_setup``) rather than the log file: reading
    the file would let a caller walk arbitrary amounts of it, and it may not exist on a
    read-only container filesystem.
    """
    from soapbot.logging_setup import get_ring
    from soapbot.security.audit import _redact_detail as redact_log

    levels = {"DEBUG": 10, "INFO": 20, "WARNING": 30, "ERROR": 40, "CRITICAL": 50}
    floor = levels.get(level.upper(), 0)
    needle = contains.lower()

    entries = list(get_ring())
    if _role_of(auth).rank < Role.ADMIN.rank:
        return {
            "entries": [],
            "count": 0,
            "total": len(entries),
            "issues": sum(levels.get(str(e.get("level", "")), 0) >= 30 for e in entries),
            "details_restricted": True,
        }
    if floor:
        entries = [e for e in entries if levels.get(str(e.get("level", "")), 0) >= floor]
    if needle:
        entries = [e for e in entries if needle in str(e.get("msg", "")).lower()]
    visible = entries[-limit:]

    def safe_value(value: Any) -> Any:
        if isinstance(value, dict):
            return {
                key: "***REDACTED***" if any(
                    term in str(key).lower() for term in ("token", "secret", "password", "key", "authorization", "cookie")
                ) else safe_value(item)
                for key, item in value.items()
            }
        if isinstance(value, list):
            return [safe_value(item) for item in value]
        return redact_log(value) if isinstance(value, str) else value

    return {
        "entries": [safe_value(entry) for entry in visible],
        "count": len(visible),
        "total": len(entries),
        "issues": sum(levels.get(str(e.get("level", "")), 0) >= 30 for e in entries),
        "details_restricted": False,
    }


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
        # Rendered by the panel instead of a hard-coded command: the Windows task
        # name is not "SoapbotPanel", and a wrong hint looks like a broken save.
        "restart_hint": restart_hint(),
        "generated_at": time.time(),
    }


def _settings() -> Any:
    from soapbot.config import settings

    return settings
