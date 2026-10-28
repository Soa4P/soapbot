"""Host-side dispatcher for worker callbacks — the single authorization point.

Every privileged thing a plugin process asks for arrives here as
``(surface, args, caller)``. This module is the **only** place that decides whether
the request is allowed, and it is deliberately the only place: a second decision
point would be a second thing to keep in sync, and the isolation review already
showed what a stale second check looks like (a capability declared but never
enforced).

Why this is stronger than the in-process check
----------------------------------------------
In-process, ``CapabilityGuard`` lives in the same interpreter as the plugin. Sealing
it (review I1) stops the naive ``ctx._guard.grant = ...``, but ``object.__setattr__``
still reaches it. That is not a flaw in the seal — it is the boundary being in the
wrong place.

Here the guard is in the parent process. The plugin cannot see it, cannot import it,
cannot patch it. The worst a hostile plugin can do is *ask*, and every ask is
re-checked against a grant object that lives in an address space it has no access to.

Scope handling is the other half. ``_FORBIDDEN_ARG_KEYS`` in ``supervisor.py``
rejects any attempt by the child to supply ``scope``/``session_key``, and this module
then derives the scope from the caller the host itself resolved. So:

    child asks:   memory.recall {"query": "cat", "scope": "group:999"}   -> refused
    child asks:   memory.recall {"query": "cat"}                         -> scoped to caller

Refusing rather than ignoring is intentional. Silently dropping ``scope`` would let
the plugin believe it had crossed the boundary and act on an empty result; a refusal
is visible in the audit trail and unambiguous in the plugin's own logs.

Auditing
--------
Denials are recorded with the **plugin name and the surface**, never the arguments
(arguments contain user text and possibly credentials). An operator reading the audit
log wants to know "plugin X tried to send to an unobserved group", not the message
body.
"""

from __future__ import annotations

import logging
from typing import Any

from soapbot.plugins.manifest import Capability
from soapbot.plugins.memory_api import (
    PluginKnowledgeAPI,
    PluginMemoryAPI,
    build_session_view,
)
from soapbot.plugins.sandbox import CapabilityDeniedError, CapabilityGuard

logger = logging.getLogger(__name__)


class SurfaceRouter:
    """Translates a worker's callback into an authorised host operation.

    Constructed by the host with everything a surface might need. Workers never see
    this object; they only see the results of its decisions.
    """

    def __init__(
        self,
        *,
        guard: CapabilityGuard,
        plugin: str,
        memory=None,
        kb=None,
        sender=None,
        ledger=None,
        audit=None,
        http_client=None,
        storage=None,
    ) -> None:
        self._guard = guard
        self._plugin = plugin
        self._memory = memory
        self._kb = kb
        self._sender = sender
        self._ledger = ledger
        self._audit = audit
        self._http = http_client
        self._storage = storage

    def _audit_denied(self, surface: str, reason: str) -> None:
        if self._audit is None:
            logger.warning(
                "plugin surface denied plugin=%s surface=%s reason=%s",
                self._plugin,
                surface,
                reason,
            )
            return
        self._audit.record(
            kind="plugin",
            action=f"surface:{surface}",
            outcome="deny",
            detail=f"plugin={self._plugin} {reason}",
            plugin=self._plugin,
        )

    async def dispatch(self, surface: str, args: dict[str, Any], caller) -> Any:
        """Authorise and execute one callback. Raises on any denial.

        The caller is the identity the **host** recorded for this invocation. It is
        passed in by the worker's read loop, which took it from the ``invoke`` frame
        the host itself sent — so there is no path where the plugin supplies it.
        """
        handler = _SURFACE_TABLE.get(surface)
        if handler is None:
            # Supervisor already checked ALLOWED_SURFACES, so reaching here means the
            # two lists disagree — a programming error worth surfacing loudly.
            self._audit_denied(surface, "unknown surface")
            raise CapabilityDeniedError(f"surface not available: {surface}")
        try:
            return await handler(self, args, caller)
        except CapabilityDeniedError as exc:
            self._audit_denied(surface, str(exc) or "denied")
            raise

    # ------------------------------------------------------------- surfaces
    async def _memory_recall(self, args: dict[str, Any], caller) -> Any:
        api = PluginMemoryAPI(
            guard=self._guard,
            plugin=self._plugin,
            store=self._memory,
            session_key=caller.session_key,
        )
        hits = await api.recall(
            str(args.get("query") or ""), limit=_as_int(args.get("limit"), 5)
        )
        return [h.to_dict() for h in hits]

    async def _memory_about_me(self, args: dict[str, Any], caller) -> Any:
        api = PluginMemoryAPI(
            guard=self._guard,
            plugin=self._plugin,
            store=self._memory,
            session_key=caller.session_key,
        )
        hits = await api.about_me(limit=_as_int(args.get("limit"), 5))
        return [h.to_dict() for h in hits]

    async def _kb_search(self, args: dict[str, Any], caller) -> Any:
        api = PluginKnowledgeAPI(guard=self._guard, plugin=self._plugin, kb=self._kb)
        hits = await api.search(
            str(args.get("query") or ""), limit=_as_int(args.get("limit"), 3)
        )
        return [h.to_dict() for h in hits]

    async def _kb_list(self, args: dict[str, Any], caller) -> Any:
        api = PluginKnowledgeAPI(guard=self._guard, plugin=self._plugin, kb=self._kb)
        return await api.list_documents()

    async def _session_view(self, args: dict[str, Any], caller) -> Any:
        self._guard.check(Capability.SESSION, detail="session view")
        view = build_session_view(caller)
        # ``to_dict`` rather than ``asdict`` so the shape is explicit: adding a field
        # to SessionView must not silently start crossing the process boundary.
        return {
            "session_key": view.session_key,
            "scene": view.scene,
            "group_id": view.group_id,
            "user_id": view.user_id,
            "display_name": view.display_name,
            "is_group": view.is_group,
        }

    async def _send(self, args: dict[str, Any], caller) -> Any:
        self._guard.check(Capability.SEND, detail="send")
        target = str(args.get("session_key") or "")
        text = str(args.get("text") or "")
        if self._ledger is None or not self._ledger.permits(self._plugin, target):
            # The plugin asked for a session it was never invoked from. This is the
            # I3 defect's exact shape: a plugin messaging a group it has no business
            # in. The check is here, in the parent, against a host-owned ledger.
            self._audit_denied("send.message", "target session not observed")
            raise PermissionError("session not authorised for this plugin")
        if self._sender is None:
            raise RuntimeError("host has no sender installed")
        await self._sender(target, text)
        return True

    async def _http(self, args: dict[str, Any], caller) -> Any:
        self._guard.check(Capability.HTTP, detail="http")
        if self._http is None:
            raise RuntimeError("host has no http client installed")
        args_list = args.get("args") or []
        kwargs = args.get("kwargs") or {}
        method = str(args_list[0]) if args_list else "GET"
        url = str(args_list[1]) if len(args_list) > 1 else ""
        if not url:
            raise ValueError("http.request needs a url")
        resp = await self._http.request(method, url, **kwargs)
        return {"status": resp.status_code, "text": resp.text[:8000]}

    async def _storage_get(self, args: dict[str, Any], caller) -> Any:
        self._guard.check(Capability.STORAGE, detail="storage.get")
        if self._storage is None:
            return args.get("default")
        return self._storage.get(str(args.get("key") or ""), args.get("default"))

    async def _storage_set(self, args: dict[str, Any], caller) -> Any:
        self._guard.check(Capability.STORAGE, detail="storage.set")
        if self._storage is None:
            raise RuntimeError("host has no storage installed")
        self._storage.set(str(args.get("key") or ""), args.get("value"))
        return True

    async def _storage_delete(self, args: dict[str, Any], caller) -> Any:
        self._guard.check(Capability.STORAGE, detail="storage.delete")
        if self._storage is None:
            return False
        return bool(self._storage.delete(str(args.get("key") or "")))

    async def _log(self, args: dict[str, Any], caller) -> Any:
        # Deliberately ungated: a plugin writing to its own log line is not a
        # privileged operation, and gating it would push plugins toward ``print``,
        # which lands in the host's stdout unredacted.
        logger.info(
            "plugin message plugin=%s msg=%s",
            self._plugin,
            str(args.get("message") or "")[:300],
        )
        return True


def _as_int(value: Any, default: int) -> int:
    try:
        return int(value)
    except (TypeError, ValueError):
        return default


#: Surface name -> handler. Kept as a module-level table so ``dispatch`` has exactly
#: one lookup, and so adding a surface requires touching one obvious place.
_SURFACE_TABLE = {
    "memory.recall": SurfaceRouter._memory_recall,
    "memory.about_me": SurfaceRouter._memory_about_me,
    "kb.search": SurfaceRouter._kb_search,
    "kb.list_documents": SurfaceRouter._kb_list,
    "session.view": SurfaceRouter._session_view,
    "send.message": SurfaceRouter._send,
    "http.request": SurfaceRouter._http,
    "storage.get": SurfaceRouter._storage_get,
    "storage.set": SurfaceRouter._storage_set,
    "storage.delete": SurfaceRouter._storage_delete,
    "log.write": SurfaceRouter._log,
}
