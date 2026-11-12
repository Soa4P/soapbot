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
import time
from typing import Any

from soapbot.plugins.manifest import Capability
from soapbot.plugins.memory_api import (
    PluginKnowledgeAPI,
    PluginMemoryAPI,
    build_session_view,
)
from soapbot.plugins.sandbox import (
    CapabilityDeniedError,
    CapabilityGuard,
    StorageUnavailable,
)

logger = logging.getLogger(__name__)

#: A rolling one-minute budget for ``log.write``. The surface is not privileged, but
#: an unbounded writer is a log-flooding primitive: it can bury a denial from another
#: plugin in noise, which is a way of hiding an unauthorised action.
LOG_WRITES_PER_MINUTE = 60


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
        bilibili_cookie_provider=None,
        bilibili_client_factory=None,
        sender_media=None,
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
        self._bilibili_cookie_provider = bilibili_cookie_provider
        self._bilibili_client_factory = bilibili_client_factory
        self._sender_media = sender_media
        self._log_writes: list[float] = []

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

    async def _send_media(self, args: dict[str, Any], caller) -> Any:
        self._guard.check(Capability.SEND_MEDIA, detail="send_media")
        target = str(args.get("session_key") or "")
        image_b64 = str(args.get("image_b64") or "")
        caption = str(args.get("caption") or "")
        if self._ledger is None or not self._ledger.permits(self._plugin, target):
            self._audit_denied("send_media.request", "target session not observed")
            raise PermissionError("session not authorised for this plugin")
        # Decode-and-cap lives HERE, not only in the in-process context: for isolated
        # plugins this router is the boundary, and a cap that exists on one path only
        # is a cap the default path does not have. Payload validation runs before the
        # sender check, so the error a hostile payload sees says nothing about whether
        # the host happens to have media delivery installed.
        import base64 as _base64
        import binascii as _binascii

        from soapbot.plugins.sandbox import MAX_PLUGIN_MEDIA_BYTES

        try:
            decoded = _base64.b64decode(image_b64, validate=True)
        except (_binascii.Error, ValueError) as exc:
            raise ValueError("image_b64 is not valid base64") from exc
        if len(decoded) > MAX_PLUGIN_MEDIA_BYTES:
            raise ValueError(
                f"image exceeds the {MAX_PLUGIN_MEDIA_BYTES // (1024 * 1024)} MiB cap "
                f"({len(decoded)} bytes)"
            )
        if self._sender_media is None:
            raise RuntimeError("host has no media sender installed")
        # Audit carries sizes only; image bytes never enter a log line.
        if self._audit is not None:
            self._audit.record(
                kind="plugin",
                action="surface:send_media.request",
                outcome="allow",
                detail=f"plugin={self._plugin} b64_chars={len(image_b64)}",
            plugin=self._plugin,
        )
        await self._sender_media(target, image_b64, caption)
        return True

    async def _media_observe(self, args: dict[str, Any], caller) -> Any:
        """Hand over the current message's image references, once, to an approved plugin.

        The session key comes from the caller the host bound for this invocation,
        never from ``args``: the wire rejects scope-bearing keys, and this handler
        does not read one. Audit carries a count — a short-lived signed URL must not
        end up in a log line simply because a plugin asked for a picture.
        """
        self._guard.check(Capability.MEDIA_OBSERVE, detail="media observe")
        session_key = str(getattr(caller, "session_key", "") or "")
        if not session_key:
            raise PermissionError("media observation needs a bound caller")
        from soapbot.plugins.media_inbox import MEDIA_INBOX

        images = MEDIA_INBOX.take(session_key)
        if self._audit is not None:
            self._audit.record(
                kind="plugin",
                action="surface:media.observe",
                outcome="allow",
                detail=f"plugin={self._plugin} count={len(images)}",
                plugin=self._plugin,
            )
        return {"images": images}

    async def _browse_page(self, url: str) -> Any:
        """Read one public page with a client that consumes the BROWSE capability.

        The same SafeHttpClient provides SSRF checks, DNS pinning, redirect refusal
        and the header allow-list; only the capability it consumes differs. Building
        it here (in the parent) is what keeps an isolated worker from ever holding a
        client that could bypass the guard.
        """
        from soapbot.browse.reader import (
            USER_AGENT,
            BrowsePolicy,
            ReadError,
            read_public_page,
        )
        from soapbot.plugins.sandbox import SafeHttpClient

        policy = BrowsePolicy.from_settings()
        client = SafeHttpClient(
            self._guard,
            allowed_hosts=policy.allowed_hosts,
            capability=Capability.BROWSE,
        )

        async def fetcher(target: str, headers: dict[str, str], timeout: float):
            return await client.fetch(
                target,
                method="GET",
                headers={"User-Agent": USER_AGENT},
                timeout=timeout,
            )

        try:
            return await read_public_page(url, policy=policy, fetcher=fetcher)
        except ReadError as exc:
            # Every ReadError carries a sentence the host wrote, not a URL echoed
            # back from the response.
            raise ValueError(str(exc)) from exc

    def _browse_audit(self, action: str, page, *, extra: str = "") -> None:
        if self._audit is None:
            return
        self._audit.record(
            kind="plugin",
            action=f"surface:{action}",
            outcome="allow",
            detail=(
                f"plugin={self._plugin} host={page.host} "
                f"bytes={page.bytes_read}{extra}"
            ),
            plugin=self._plugin,
        )

    async def _browse_read(self, args: dict[str, Any], caller) -> Any:
        self._guard.check(Capability.BROWSE, detail="browse read")
        page = await self._browse_page(str(args.get("url") or ""))
        self._browse_audit("browse.read", page)
        return page.to_dict()

    async def _browse_propose(self, args: dict[str, Any], caller) -> Any:
        """Read a page, pre-check the caps, and create one pending spend request."""
        self._guard.check(Capability.BROWSE, detail="browse propose")
        from soapbot.app import get_runtime
        from soapbot.browse.proposal import propose_purchase

        runtime = get_runtime()
        store = getattr(runtime, "budget", None) if runtime is not None else None
        if store is None:
            raise RuntimeError("budget ledger is not enabled")
        session_key = str(getattr(caller, "session_key", "") or "")
        if not session_key:
            raise PermissionError("a bound caller is required to propose a purchase")

        page = await self._browse_page(str(args.get("url") or ""))
        override = args.get("amount_minor")
        result = await propose_purchase(
            store,
            page,
            session_key=session_key,
            requester_id=f"plugin:{self._plugin}",
            requester_name=self._plugin,
            amount_override_minor=int(override) if override is not None else None,
        )
        self._browse_audit(
            "browse.propose",
            page,
            extra=f" created={result.created} reason={result.reason}",
        )
        return result.to_dict()

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

    async def _bilibili(self, args: dict[str, Any], caller) -> Any:
        # Re-checked here even though the in-process client checks again: in the
        # isolated path this router *is* the security boundary — the child has no
        # guard at all, and this is the object that decides.
        self._guard.check(Capability.BILIBILI, detail="bilibili.request")
        path = str(args.get("path") or "")
        if not path:
            raise ValueError("bilibili.request needs a path")
        raw_params = args.get("params") or {}
        if not isinstance(raw_params, dict):
            raise ValueError("params must be an object of string->string")
        from soapbot.plugins.sandbox import BilibiliClient

        client = BilibiliClient(
            self._guard,
            cookie_provider=self._bilibili_cookie_provider or _default_bilibili_cookie,
            client_factory=self._bilibili_client_factory,
        )
        # The client audits the request with the path only; the cookie value never
        # enters a detail string, a log line or an error message.
        return await client.get_json(path, params=raw_params)

    async def _storage_get(self, args: dict[str, Any], caller) -> Any:
        self._guard.check(Capability.STORAGE, detail="storage.get")
        if self._storage is None:
            return args.get("default")
        return self._storage.get(str(args.get("key") or ""), args.get("default"))

    async def _storage_set(self, args: dict[str, Any], caller) -> Any:
        self._guard.check(Capability.STORAGE, detail="storage.set")
        if self._storage is None:
            # Same refusal as the in-process path (``PluginContext.storage``), so a
            # plugin behaves identically whether or not it was isolated: no key
            # material means no store, never a plaintext one.
            raise StorageUnavailable(
                "plugin storage is disabled: no master key is loaded. Set "
                "SOAPBOT_MASTER_KEY or let the bot create data/secret.key, then restart."
            )
        self._storage.set(str(args.get("key") or ""), args.get("value"))
        return True

    async def _storage_delete(self, args: dict[str, Any], caller) -> Any:
        self._guard.check(Capability.STORAGE, detail="storage.delete")
        if self._storage is None:
            return False
        return bool(self._storage.delete(str(args.get("key") or "")))

    async def _log(self, args: dict[str, Any], caller) -> Any:
        # Still deliberately not capability-gated: a plugin writing to its own log
        # line is not a privileged operation, and gating it would push plugins toward
        # ``print``, which lands in the host's stdout unredacted. But "not privileged"
        # is not "unobserved": every write is audited with the plugin name, and a
        # deterministic rate limit keeps one plugin from burying another's denial.
        now = time.monotonic()
        self._log_writes = [ts for ts in self._log_writes if now - ts < 60.0]
        if len(self._log_writes) >= LOG_WRITES_PER_MINUTE:
            self._audit_denied("log.write", "rate limited")
            return False
        self._log_writes.append(now)
        message = str(args.get("message") or "")[:300]
        logger.info("plugin message plugin=%s msg=%s", self._plugin, message)
        if self._audit is not None:
            self._audit.record(
                kind="plugin",
                action="surface:log.write",
                outcome="allow",
                detail=f"plugin={self._plugin} chars={len(message)}",
                plugin=self._plugin,
            )
        return True


def _as_int(value: Any, default: int) -> int:
    try:
        return int(value)
    except (TypeError, ValueError):
        return default


def _default_bilibili_cookie() -> str:
    """Lazy settings read, mirroring ``api.chat.surfaces()``.

    ``None``/empty returns ``""`` so the client raises its own specific
    "not configured" error rather than an AttributeError here.
    """
    from soapbot.config import settings

    value = getattr(settings, "bili_cookie", None)
    if value is None:
        return ""
    return value.get_secret_value() if hasattr(value, "get_secret_value") else str(value)


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
    "bilibili.request": SurfaceRouter._bilibili,
    "send_media.request": SurfaceRouter._send_media,
    "media.observe": SurfaceRouter._media_observe,
    "browse.read": SurfaceRouter._browse_read,
    "browse.propose": SurfaceRouter._browse_propose,
    "storage.get": SurfaceRouter._storage_get,
    "storage.set": SurfaceRouter._storage_set,
    "storage.delete": SurfaceRouter._storage_delete,
    "log.write": SurfaceRouter._log,
}
