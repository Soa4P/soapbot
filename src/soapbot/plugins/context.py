"""The plugin-facing API object (``ctx``).

Design rule
-----------
**A plugin receives a narrow, mediated object; it never receives the runtime, the
pipeline, the database session or an adapter.** Every path out of the plugin goes
through a method here, so this file is the complete list of things a plugin can do
through the sanctioned API. That is what makes the capability model auditable: if
it is not a method on ``PluginContext``, a plugin cannot do it *with permissions
granted by the host*.

The same object is handed to every hook, so ordering matters: capabilities are
checked at call time, not at registration time, because a plugin might register a
command while holding ``COMMAND`` but then attempt ``HTTP`` from inside the
handler — that second call is the one that must be refused.

Input hygiene
-------------
Everything a plugin passes *in* is validated here (argument shapes, lengths,
ids), and everything it hands *out* (messages, tool results) is validated on the
way out by :func:`soapbot.plugins.sandbox.scrub_plugin_output`. Validating in both
directions is not redundancy: inbound validation stops malformed data reaching
the host, outbound validation stops host data reaching a chat.
"""

from __future__ import annotations

import contextvars
import logging
from collections.abc import Awaitable, Callable
from contextlib import contextmanager
from dataclasses import dataclass, field
from typing import Any

from soapbot.plugins.manifest import Capability
from soapbot.plugins.sandbox import (
    CapabilityGuard,
    EncryptedPluginStorage,
    PluginStorage,
    SafeHttpClient,
    scrub_plugin_output,
    validate_command_name,
)
from soapbot.security.principal import Principal, Role

logger = logging.getLogger(__name__)

#: The caller of the plugin handler currently executing on this task.
#:
#: Set by :func:`bind_caller` in the host's dispatch paths, never by plugin code.
#: It is a ``ContextVar`` rather than an attribute so that two conversations being
#: handled concurrently on different tasks cannot see each other's identity — the
#: per-plugin context object is shared, but the caller is not.
#:
#: A plugin *can* call ``bind_caller`` itself (it is an ordinary import), which is
#: why this is a convenience/scoping mechanism and not the authorisation boundary:
#: ``CapabilityGuard.check`` is what actually decides. Pinning the scope here removes
#: the ability to *express* a cross-session read; the capability check removes the
#: ability to perform one without a grant. Both are needed, for different attacks.
_CURRENT_CALLER: contextvars.ContextVar[CallerContext | None] = contextvars.ContextVar(
    "soapbot_plugin_caller", default=None
)


@contextmanager
def bind_caller(caller: CallerContext):
    """Host-side: make ``caller`` the identity for ``ctx.memory`` / ``ctx.session``.

    Used as ``with bind_caller(caller): await handler(...)`` in every dispatch path.
    The token is always reset, including on exception, so a failed handler cannot
    leave its caller bound for the next invocation on the same task.
    """
    token = _CURRENT_CALLER.set(caller)
    try:
        yield
    finally:
        _CURRENT_CALLER.reset(token)

#: Hard ceiling on a plugin command's reply. The core uses the same budget, so a
#: plugin cannot out-shout the bot or flood a group.
MAX_REPLY_CHARS = 2000
MAX_ARGS = 16
MAX_ARG_CHARS = 200


@dataclass(slots=True)
class CallerContext:
    """The narrow view of the caller a plugin is allowed to see.

    Deliberately *not* the raw event: an event carries the adapter, the raw
    protocol payload and other groups' routing data. A plugin gets identity, role
    and scope — enough to be useful, not enough to pivot into another session.
    """

    user_id: str
    display_name: str
    role: str
    session_key: str
    scene: str
    group_id: str = ""
    is_privileged: bool = False

    @classmethod
    def from_principal(cls, principal: Principal | None, session_key: str = "") -> CallerContext:
        if principal is None:
            return CallerContext(
                user_id="", display_name="", role="anonymous", session_key=session_key, scene=""
            )
        return CallerContext(
            user_id=principal.user_id,
            display_name=principal.display_name,
            role=str(principal.role),
            session_key=session_key or principal.session_key,
            scene=principal.scene,
            group_id=principal.group_id,
            is_privileged=principal.is_privileged,
        )

    def at_least(self, role: Role) -> bool:
        """Role comparison a plugin may use, based on the *host's* resolution.

        The plugin never decides a role; it asks the host to compare the role the
        host already resolved. A plugin therefore cannot promote anyone.
        """
        try:
            return Role(self.role).rank >= role.rank
        except ValueError:
            return False


@dataclass(slots=True)
class PluginResult:
    """What a hook returns. Kept explicit so the host controls delivery."""

    reply: str = ""
    """Text to send back to the caller's session. Scrubbed by the host."""

    halt: bool = False
    """Stop the pipeline (the host still applies delivery rules)."""

    extras: dict[str, Any] = field(default_factory=dict)


class PluginContext:
    """The host API handed to a plugin instance.

    One instance per (plugin, invocation) pair would be safest, but plugins
    legitimately need to register commands at load time. So the object is per
    plugin and immutable in its identity fields; all mutable per-invocation state
    arrives as arguments to the call that needs it.
    """

    def __init__(
        self,
        *,
        plugin: str,
        guard: CapabilityGuard,
        logger_: logging.Logger | None = None,
        http_client_factory: Callable[[CapabilityGuard], SafeHttpClient] | None = None,
        storage_backend: dict[str, dict[str, Any]] | None = None,
        crypto=None,
        audit=None,
        session_ledger=None,
        memory=None,
        kb=None,
    ) -> None:
        self.plugin = plugin
        self._guard = guard
        self.log = logger_ or logging.getLogger(f"soapbot.plugin.{plugin}")
        self._commands: dict[str, dict[str, Any]] = {}
        self._tools: dict[str, dict[str, Any]] = {}
        self._message_hooks: list[Callable[..., Awaitable[Any]]] = []
        self._notice_hooks: list[Callable[..., Awaitable[Any]]] = []
        self._cron_jobs: list[dict[str, Any]] = []
        # Only this plugin's slice of the shared store — never the outer mapping.
        # Passing the whole mapping (as before) made every other plugin's secrets
        # readable via one attribute access; see sandbox.PluginStorage.__init__.
        backend = storage_backend if storage_backend is not None else {}
        self._storage_backend = backend.setdefault(plugin, {})
        self._crypto = crypto
        self._audit = audit
        self._http_factory = http_client_factory or SafeHttpClient
        # The set of sessions this plugin may send to is owned by the HOST, not by
        # this object. Keeping it here as a plain set let a plugin call
        # ``ctx._observed_sessions.add("onebot11:group:<any>")`` and then broadcast
        # anywhere — reproduced during the isolation review. The ledger is a host
        # object the plugin has no handle on.
        from soapbot.plugins.isolation import NullLedger

        # Deliberately a *null* ledger by default, not a real one. The host installs
        # a real ledger through ``_bind_sessions`` from dispatch, which the plugin
        # cannot call meaningfully. If a real ledger were exposed here as an
        # attribute, a plugin could call ``ctx._session_ledger.record(...)`` itself —
        # the same escalation as mutating the old plain set, merely one indirection
        # further away (that variant was reproduced during review).
        self._session_ledger = session_ledger or NullLedger()
        self._sender = None
        # Backing stores for the Wave 3 surfaces. ``None`` means "this host has no
        # memory configured", which the APIs report through ``.available`` rather
        # than by raising — but authorisation is still enforced per call, so an
        # absent store never becomes a way to bypass the capability check.
        self._memory_store = memory
        self._kb_store = kb

    # ------------------------------------------------------------- registration
    def command(
        self,
        name: str,
        *,
        description: str = "",
        min_role: Role = Role.MEMBER,
        usage: str = "",
    ) -> Callable[[Callable[..., Awaitable[Any]]], Callable[..., Awaitable[Any]]]:
        """Register a slash command.

        ``min_role`` is *additional* to the ``COMMAND`` capability: a plugin may
        declare a command that only admins can trigger. The stricter of the two
        wins at dispatch time (host-side check), so a plugin cannot lower a core
        requirement by declaring ``min_role=MEMBER`` on something sensitive — the
        host re-checks the caller's role itself.
        """
        self._guard.check(Capability.COMMAND, detail=f"register {name}")
        safe = validate_command_name(name)
        if safe in self._commands:
            raise ValueError(f"command {safe!r} already registered by this plugin")

        def decorator(fn: Callable[..., Awaitable[Any]]) -> Callable[..., Awaitable[Any]]:
            if not callable(fn):
                raise TypeError("command handler must be callable")
            self._commands[safe] = {
                "handler": fn,
                "description": str(description)[:200],
                "min_role": min_role,
                "usage": str(usage)[:100],
                "plugin": self.plugin,
            }
            return fn

        return decorator

    def register_proxied_command(
        self, name: str, *, worker, plugin: str, spec: dict | None = None
    ) -> None:
        """Record a command implemented inside an isolated worker process.

        Called by the **loader**, not by the plugin: the worker announced the name
        over the pipe, and the host decides whether that name is acceptable. Going
        through the same ``validate_command_name`` and capability check as
        :meth:`command` is what keeps the reserved-name guard effective — if worker
        commands bypassed it, a plugin could ship ``/forget`` and shadow a core
        command the moment it was loaded in isolated mode.

        The handler stored here is a *forwarder*. Nothing in this closure is plugin
        code; it is host code that sends the name and args to the worker.
        """
        self._guard.check(Capability.COMMAND, detail=f"register proxied {name}")
        safe = validate_command_name(name)
        if safe in self._commands:
            raise ValueError(f"command {safe!r} already registered by this plugin")

        async def _forward(caller, args):
            return await worker.invoke(safe, caller=caller, args=list(args or []))

        # ``min_role`` must come from the plugin's declaration, not a default. The
        # measured bug: hardcoding ``Role.MEMBER`` here made an admin-only command
        # available to every member as soon as the plugin ran isolated — a silent
        # privilege *downgrade* of the command's protection, introduced purely by the
        # deployment mode. Unknown role strings fall back to ADMIN rather than MEMBER:
        # if a plugin names a role this host does not know, the safe reading is "at
        # least as strict as an admin command", not "everyone".
        meta = spec or {}
        declared = str(meta.get("min_role") or "").strip().lower()
        if not declared:
            min_role = Role.MEMBER
        else:
            try:
                min_role = Role(declared)
            except ValueError:
                logger.warning(
                    "plugin %s command %s declared unknown role %r; requiring admin",
                    plugin,
                    safe,
                    declared,
                )
                min_role = Role.ADMIN

        self._commands[safe] = {
            "handler": _forward,
            "description": str(meta.get("description") or ""),
            "min_role": min_role,
            "usage": str(meta.get("usage") or ""),
            "plugin": plugin,
            "proxied": True,
        }

    def register_proxied_tool(
        self, name: str, *, worker, plugin: str, spec: dict | None = None
    ) -> None:
        """Record a tool implemented inside an isolated worker process.

        The worker announces tools through the same ``commands`` frame as ordinary
        commands, tagged ``kind: "tool"``. Before this method existed the host
        registered *every* announced name as a command, so an isolated plugin's
        tools became slash commands — reachable by typing ``/<tool-name>`` and
        invisible to the model, which is the exact opposite of their purpose.

        The forwarder is host code: it sends the name and a dict of arguments to
        the worker, and the worker's ``_invoke`` path calls the handler. No plugin
        code runs in this process even when a tool is called.
        """
        self._guard.check(Capability.TOOL, detail=f"register proxied tool {name}")
        safe = validate_command_name(name)
        if safe in self._tools:
            raise ValueError(f"tool {safe!r} already registered by this plugin")
        # A name that is both a command and a tool would resolve to one of them by
        # accident of iteration order. Refusing is the only unambiguous reading.
        if safe in self._commands:
            raise ValueError(
                f"{safe!r} is registered as a command and a tool by this plugin"
            )

        async def _forward(caller, arguments):
            return await worker.invoke(safe, caller=caller, args=[arguments or {}])

        meta = spec or {}
        declared = str(meta.get("min_role") or "").strip().lower()
        if not declared:
            min_role = Role.MEMBER
        else:
            try:
                min_role = Role(declared)
            except ValueError:
                logger.warning(
                    "plugin %s tool %s declared unknown role %r; requiring admin",
                    plugin,
                    safe,
                    declared,
                )
                min_role = Role.ADMIN

        self._tools[safe] = {
            "handler": _forward,
            "description": str(meta.get("description") or ""),
            "parameters": meta.get("parameters") or {"type": "object", "properties": {}},
            "min_role": min_role,
            "plugin": plugin,
            "proxied": True,
        }

    def on_message(
        self, fn: Callable[..., Awaitable[Any]]
    ) -> Callable[..., Awaitable[Any]]:
        """Observe messages. Observation only — cannot alter or block them."""
        self._guard.check(Capability.MESSAGE, detail="register on_message")
        if not callable(fn):
            raise TypeError("handler must be callable")
        self._message_hooks.append(fn)
        return fn

    def on_notice(
        self, fn: Callable[..., Awaitable[Any]]
    ) -> Callable[..., Awaitable[Any]]:
        self._guard.check(Capability.NOTICE, detail="register on_notice")
        if not callable(fn):
            raise TypeError("handler must be callable")
        self._notice_hooks.append(fn)
        return fn

    def tool(
        self,
        name: str,
        *,
        description: str = "",
        parameters: dict[str, Any] | None = None,
        min_role: Role = Role.MEMBER,
    ) -> Callable[[Callable[..., Awaitable[Any]]], Callable[..., Awaitable[Any]]]:
        """Expose a function-calling tool to the model.

        Tools are the most dangerous plugin surface: the *model* chooses when to
        call them, driven by text an attacker controls. Consequently:

        * the tool name is validated like a command name,
        * ``min_role`` defaults to MEMBER and is re-checked host-side,
        * every invocation is audited with the calling plugin,
        * a tool must return a string (or JSON-able value) that the host scrubs.
        """
        self._guard.check(Capability.TOOL, detail=f"register tool {name}")
        safe = validate_command_name(name)
        if safe in self._tools:
            raise ValueError(f"tool {safe!r} already registered by this plugin")

        def decorator(fn: Callable[..., Awaitable[Any]]) -> Callable[..., Awaitable[Any]]:
            if not callable(fn):
                raise TypeError("tool handler must be callable")
            self._tools[safe] = {
                "handler": fn,
                "description": str(description)[:300],
                "parameters": parameters or {"type": "object", "properties": {}},
                "min_role": min_role,
                "plugin": self.plugin,
            }
            return fn

        return decorator

    def cron(self, expr: str, *, name: str = "") -> Callable[[Callable[..., Awaitable[Any]]], Any]:
        """Register a periodic job. ``expr`` is a cron string, validated host-side."""
        self._guard.check(Capability.CRON, detail=f"cron {expr!r}")
        from croniter import croniter

        if not croniter.is_valid(expr):
            raise ValueError(f"invalid cron expression {expr!r}")

        def decorator(fn: Callable[..., Awaitable[Any]]) -> Callable[..., Awaitable[Any]]:
            self._cron_jobs.append(
                {"expr": expr, "handler": fn, "name": name or fn.__name__, "plugin": self.plugin}
            )
            return fn

        return decorator

    # ------------------------------------------------------------------ services
    @property
    def storage(self) -> PluginStorage:
        """Key-value storage, namespaced to this plugin.

        Encrypted when a crypto box is available: plugin storage is where a plugin
        puts the API token it needs, and that token must not be readable from a
        database dump.
        """
        self._guard.check(Capability.STORAGE, detail="storage access")
        if self._crypto is not None:
            return EncryptedPluginStorage(self.plugin, self._storage_backend, self._crypto)
        return PluginStorage(self.plugin, self._storage_backend)

    @property
    def http(self) -> SafeHttpClient:
        """Outbound HTTP with SSRF defence, redirect refusal and size caps."""
        return self._http_factory(self._guard)

    async def send(self, text: str, *, session_key: str) -> None:
        """Send an unsolicited message to a session.

        ``session_key`` must be a session this plugin actually observed during the
        current process run. That allow-list is what stops a plugin from
        broadcasting to arbitrary groups: the host records the sessions a plugin
        has legitimately seen, and refuses the rest.

        Delivery itself is performed by the host through a registered callback, so
        the plugin never touches an adapter.
        """
        self._guard.check(Capability.SEND, detail=f"len={len(text or '')}")
        from soapbot.plugins.sandbox import _SESSION_KEY_RE

        # Shape check plus observed-session allow-list. The shape check is the
        # cheap first gate (it rejects injection attempts and control characters);
        # the allow-list is what actually bounds *reach*. Both are needed: the
        # shape alone still permits any well-formed group id, and the allow-list
        # alone would happily accept a malformed key the host happened to observe.
        if not isinstance(session_key, str) or not _SESSION_KEY_RE.match(session_key):
            raise ValueError(
                "invalid session_key; expected 'adapter:scene:target' "
                "(e.g. onebot11:group:123456)"
            )
        # Ask the host's ledger. The plugin has no handle on it, so it cannot add
        # a target to the allow-list the way it could when the set lived here.
        if not self._session_ledger.permits(self.plugin, session_key):
            raise PermissionError(
                "plugin may only send to sessions the host recorded for it"
            )
        clean = scrub_plugin_output(text, max_chars=MAX_REPLY_CHARS)
        if not clean.strip():
            return
        if self._sender is None:
            raise RuntimeError("no sender registered; host did not enable sending")
        await self._sender(session_key, clean)

    def _init_runtime_hooks(self, *, sender=None, memory=None, kb=None) -> None:
        """Host-only wiring, called by the loader/manager after construction."""
        self._sender = sender
        if memory is not None:
            self._memory_store = memory
        if kb is not None:
            self._kb_store = kb

    # --------------------------------------------------- wave 3: memory surfaces
    #
    # These are *properties*, not methods, so a plugin writes the obvious thing:
    #
    #     hits = await ctx.memory.recall("cat")
    #     ctx.session.is_group
    #
    # The scope each call uses comes from ``_CURRENT_CALLER`` — a contextvar the
    # host sets for the duration of one handler invocation. Why a contextvar and
    # not a parameter or a field on this object:
    #
    # * A parameter is dangerously easy to fake: ``recall(q, scope=...)`` would let
    #   a plugin name any session key and read another group's memories. No such
    #   argument exists anywhere in this API, so the attack cannot be written down.
    # * A field would leak across conversations: one context object serves every
    #   call of one plugin, so storing "the current caller" on it hands group A's
    #   scope to group B as soon as two messages overlap. A contextvar is per-task.
    # * Capturing at ``setup`` time is wrong too — setup runs before any user
    #   exists, so whatever it captured would be stale forever.
    #
    # Outside an invocation (from setup, or a cron job with no session) these raise
    # a clear error instead of guessing. Failing loudly is the only correct answer
    # here: the alternative is a default scope, and a default scope is a leak.

    @property
    def memory(self):
        """``ctx.memory`` — read-only recall, scoped to the current caller."""
        from soapbot.plugins.memory_api import PluginMemoryAPI

        return PluginMemoryAPI(
            guard=self._guard,
            plugin=self.plugin,
            store=self._memory_store,
            session_key=self._require_caller("memory").session_key,
        )

    @property
    def kb(self):
        """``ctx.kb`` — knowledge-base search (global, operator-owned)."""
        from soapbot.plugins.memory_api import PluginKnowledgeAPI

        return PluginKnowledgeAPI(
            guard=self._guard, plugin=self.plugin, kb=self._kb_store
        )

    @property
    def session(self):
        """``ctx.session`` — immutable snapshot of the current conversation.

        Requires the ``session`` capability. Returns scalars only: identity, scene
        and group. Notably it does **not** return the principal's permission set, so
        a plugin cannot enumerate what the current caller is allowed to do.
        """
        from soapbot.plugins.memory_api import build_session_view

        self._guard.check(Capability.SESSION, detail="session view")
        return build_session_view(self._require_caller("session"))

    @staticmethod
    def _require_caller(surface: str) -> CallerContext:
        caller = _CURRENT_CALLER.get()
        if caller is None:
            raise RuntimeError(
                f"ctx.{surface} was used outside a plugin invocation; it is only "
                "valid inside a command/hook handler, where the host has already "
                "established who is asking"
            )
        return caller

    def remember_session(self, session_key: str) -> None:
        """Host hook: record that this plugin was invoked for ``session_key``.

        Requires the host authority token, so a plugin cannot call this to widen its
        own reach — it is exactly the call that extends the allow-list, which makes
        it exactly the call that must not be plugin-callable.
        """
        from soapbot.plugins.isolation import HOST_AUTHORITY

        if session_key and self.plugin:
            try:
                self._session_ledger.record(
                    self.plugin, session_key, authority=HOST_AUTHORITY
                )
            except PermissionError:
                # A NullLedger never raises; a real one only raises without the
                # token, which cannot happen here. Swallow defensively so a ledger
                # swap cannot break dispatch.
                logger.warning("session ledger refused host write plugin=%s", self.plugin)

    # -------------------------------------------------------------- introspection
    @property
    def commands(self) -> dict[str, dict[str, Any]]:
        return dict(self._commands)

    @property
    def tools(self) -> dict[str, dict[str, Any]]:
        return dict(self._tools)

    @property
    def cron_jobs(self) -> list[dict[str, Any]]:
        return list(self._cron_jobs)

    def exported_api(self) -> dict[str, Any]:
        """Everything this plugin registered, for the WebUI and for teardown."""
        return {
            "plugin": self.plugin,
            "commands": sorted(self._commands),
            "tools": sorted(self._tools),
            "cron_jobs": [j["name"] for j in self._cron_jobs],
            "has_message_hook": bool(self._message_hooks),
            "has_notice_hook": bool(self._notice_hooks),
        }


def validate_args(args: Any) -> list[str]:
    """Validate command arguments from any source.

    A plugin command receives arguments that ultimately came from a chat message.
    Caps on count and length stop a single message from forcing a plugin into
    pathological work, and the type check stops a non-list sneaking through a
    caller that forgot to normalise.
    """
    if args is None:
        return []
    if isinstance(args, str):
        args = args.split()
    if not isinstance(args, list | tuple):
        raise ValueError("args must be a list or string")
    if len(args) > MAX_ARGS:
        raise ValueError(f"too many arguments (max {MAX_ARGS})")
    out: list[str] = []
    for item in args:
        text = str(item)
        if len(text) > MAX_ARG_CHARS:
            text = text[:MAX_ARG_CHARS]
        out.append(text)
    return out
