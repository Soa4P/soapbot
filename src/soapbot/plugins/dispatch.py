"""Plugins as pipeline stages: command dispatch, tool execution, hook fan-out.

The critical decision in this module
-----------------------------------
**The host re-checks the caller's role; it never trusts a plugin's ``min_role``.**

A plugin declares ``min_role`` on a command, and that value is used only to make
the *plugin's intent* visible. The actual allow/deny decision is computed from the
principal the host resolved, in the host's own code. If it were the other way
round, a plugin could register ``/anything`` with ``min_role=MEMBER`` and hand an
unprivileged user whatever it liked — the plugin would be deciding authorization,
which is exactly what the capability model exists to prevent.

Additional host-side rules applied to every plugin reply
--------------------------------------------------------
* scrubbed (invisible chars stripped, secrets masked),
* length-capped to the same budget as core replies,
* canary-checked — a plugin echoing untrusted framing means it fed model output or
  retrieved data straight through, so the reply is dropped,
* audited with the plugin name, so a noisy or hostile plugin is attributable.
"""

from __future__ import annotations

import asyncio
import inspect
import logging
import time
from datetime import datetime
from typing import Any
from zoneinfo import ZoneInfo

from soapbot.config import settings
from soapbot.core.pipeline import PipelineContext, Stage, StageResult
from soapbot.plugins.context import (
    CallerContext,
    PluginContext,
    PluginResult,
    bind_caller,
    validate_args,
)
from soapbot.plugins.loader import LoadedPlugin, PluginLoader, record_invocation
from soapbot.plugins.sandbox import (
    PluginInvocation,
    scrub_plugin_output,
)
from soapbot.security.audit import AuditLog, get_audit_log
from soapbot.security.injection import leaked_canary
from soapbot.security.principal import Principal, Role

logger = logging.getLogger(__name__)

_HANDLER_TIMEOUT = 8.0
"""A plugin handler that blocks must not stall the whole session.

The pipeline is per-session serialised, so one hung plugin equals one frozen
conversation. A timeout turns "the bot is dead in this group" into "that command
failed".
"""


def _normalise_result(raw: Any) -> PluginResult:
    """Accept the shapes a plugin may return, uniformly."""
    if raw is None:
        return PluginResult()
    if isinstance(raw, PluginResult):
        return raw
    if isinstance(raw, str):
        return PluginResult(reply=raw)
    if isinstance(raw, dict):
        return PluginResult(
            reply=str(raw.get("reply", "")),
            halt=bool(raw.get("halt", False)),
            extras=dict(raw.get("extras") or {}),
        )
    # Anything else is a plugin bug; report it rather than trying to coerce.
    raise TypeError(f"unsupported plugin return type: {type(raw).__name__}")


class PluginCommandStage(Stage):
    """Dispatch ``/cmd`` to plugin handlers, after the core command stage.

    Ordering: this stage is installed **after** :class:`CommandStage`, so a plugin
    can never shadow a core command. Core commands are also reserved by name in
    :func:`soapbot.plugins.sandbox.validate_command_name`, making the collision
    impossible at registration time as well — belt and braces, because a silent
    override of ``/forget`` would be a security regression, not a UX bug.
    """

    name = "plugin_command"

    def __init__(self, loader: PluginLoader, *, audit: AuditLog | None = None) -> None:
        self.loader = loader
        self.audit = audit or get_audit_log()

    async def run(self, ctx: PipelineContext) -> StageResult:
        from soapbot.core.message import SegmentType

        segments = ctx.extras.get("clean_segments") or ctx.event.segments
        text = "".join(
            s.plain() for s in segments if s.type is SegmentType.TEXT
        ).strip()
        if not text.startswith(("/", "!", "／")):
            return StageResult()

        body = text[1:].replace("／", "/")
        parts = body.split()
        if not parts:
            return StageResult()
        cmd = parts[0].lower()
        raw_args = parts[1:]

        table = self.loader.all_commands()
        meta = table.get(cmd)
        if meta is None:
            return StageResult()

        principal: Principal | None = ctx.extras.get("principal")
        plugin = meta["plugin"]

        # ---- host-side authorization. The plugin's min_role is a *hint* only. ----
        required: Role = meta.get("min_role") or Role.MEMBER
        caller_role = principal.role if principal else Role.ANONYMOUS
        if not principal or not principal.authenticated or caller_role.rank < required.rank:
            self.audit.record(
                kind="plugin",
                action=f"cmd:{cmd}",
                outcome="deny",
                principal=principal,
                detail=f"plugin={plugin} requires {required}, caller is {caller_role}",
                trace_id=ctx.event.trace_id,
                plugin=plugin,
            )
            # Same flat refusal as core: naming the plugin or the required role
            # tells an attacker which door to push on.
            ctx.model_reply = "抱歉，你没有执行该操作的权限。"
            ctx.extras["skip_model"] = True
            ctx.extras["plugin_command_denied"] = cmd
            return StageResult()

        try:
            args = validate_args(raw_args)
        except ValueError as exc:
            ctx.model_reply = "参数不合法。"
            ctx.extras["skip_model"] = True
            self.audit.record(
                kind="plugin",
                action=f"cmd:{cmd}",
                outcome="block",
                principal=principal,
                detail=f"plugin={plugin} bad args: {exc}",
                trace_id=ctx.event.trace_id,
                plugin=plugin,
            )
            return StageResult()

        loaded = self.loader.get(plugin)
        if loaded is None:
            # Registered but no longer loaded: a torn-down plugin left a stale
            # entry. Refuse rather than resolving to a dangling handler.
            logger.error("command %s maps to unloaded plugin %s", cmd, plugin)
            return StageResult()

        caller = CallerContext.from_principal(principal, ctx.event.session_key)
        loaded.context.remember_session(ctx.event.session_key)

        started = time.perf_counter()
        invocation = PluginInvocation(plugin=plugin, entry=f"cmd:{cmd}", ok=False, duration_ms=0)
        try:
            # Bind the caller for the duration of the handler so ``ctx.memory`` and
            # ``ctx.session`` resolve to *this* conversation. Without it those
            # surfaces raise rather than silently picking a scope.
            with bind_caller(caller):
                reply = await asyncio.wait_for(
                    self._call(loaded.context, meta["handler"], caller, args),
                    timeout=_HANDLER_TIMEOUT,
                )
            result = _normalise_result(reply)
            invocation.ok = True
        except TimeoutError:
            invocation.error = "timeout"
            result = PluginResult(reply="命令处理超时了，稍后再试试。")
        except Exception as exc:
            invocation.error = type(exc).__name__
            logger.exception("plugin command failed plugin=%s cmd=%s", plugin, cmd)
            # Never surface the exception text: it is plugin-controlled and can
            # contain credentials or another user's data.
            result = PluginResult(reply="命令执行失败，请联系管理员。")
        finally:
            invocation.duration_ms = (time.perf_counter() - started) * 1000
            loaded.invocations += 1
            record_invocation(self.audit, loaded, invocation)

        # ---- outbound hygiene, applied identically to core replies -------------
        reply_text = scrub_plugin_output(result.reply, max_chars=2000)
        if leaked_canary(reply_text):
            # The plugin passed untrusted framing straight through, which means it
            # forwarded retrieved/model text without treating it as data.
            self.audit.record(
                kind="plugin",
                action=f"cmd:{cmd}",
                outcome="quarantine",
                principal=principal,
                detail=f"plugin={plugin} canary leak in output",
                trace_id=ctx.event.trace_id,
                plugin=plugin,
            )
            reply_text = "命令返回了不安全的内容，已拦截。"

        if reply_text:
            ctx.model_reply = reply_text
            ctx.extras["skip_model"] = True
            ctx.extras["plugin_command"] = cmd
        if result.halt:
            return StageResult(halt=True, reason=f"plugin_halt:{plugin}")
        return StageResult()

    @staticmethod
    async def _call(
        pctx: PluginContext, handler, caller: CallerContext, args: list[str]
    ) -> Any:
        """Invoke a handler, passing only what it declares.

        Passed-by-name inspection keeps plugin handlers simple to write while
        preventing the host from accidentally handing a plugin the full context
        object (which carries the pipeline, and with it everything).
        """
        func = handler
        try:
            sig = inspect.signature(func)
        except (TypeError, ValueError):
            return await _maybe_await(func(caller, args))

        params = list(sig.parameters.values())
        if params and params[0].kind in (
            inspect.Parameter.POSITIONAL_ONLY,
            inspect.Parameter.POSITIONAL_OR_KEYWORD,
        ):
            # Handlers are written as (caller, args) or (caller,) — never (ctx,).
            if len(params) >= 2:
                return await _maybe_await(func(caller, args))
            return await _maybe_await(func(caller))
        return await _maybe_await(func())


async def _maybe_await(value: Any) -> Any:
    if inspect.isawaitable(value):
        return await value
    return value


class PluginMessageHookStage(Stage):
    """Fan out observation-only hooks. Cannot alter or block the message.

    Read-only on purpose. A plugin that could rewrite the inbound message would be
    able to substitute text *after* sanitisation and injection screening ran,
    defeating both. Hooks receive a frozen copy of the caller view.
    """

    name = "plugin_message_hooks"

    def __init__(self, loader: PluginLoader, *, audit: AuditLog | None = None) -> None:
        self.loader = loader
        self.audit = audit or get_audit_log()

    async def run(self, ctx: PipelineContext) -> StageResult:
        if not self.loader.loaded:
            return StageResult()

        principal: Principal | None = ctx.extras.get("principal")
        caller = CallerContext.from_principal(principal, ctx.event.session_key)
        text = ctx.event.text[:500]

        for loaded in list(self.loader.loaded.values()):
            hooks = loaded.context._message_hooks
            if not hooks:
                continue
            loaded.context.remember_session(ctx.event.session_key)
            for hook in hooks:
                try:
                    with bind_caller(caller):
                        await asyncio.wait_for(
                            _maybe_await(hook(caller, text)), timeout=2.0
                        )
                except Exception as exc:
                    # A failing observer must not break the conversation.
                    logger.warning(
                        "plugin message hook failed plugin=%s err=%s",
                        loaded.name,
                        type(exc).__name__,
                    )
        return StageResult()


class PluginToolRegistry:
    """Exposes plugin tools to the model, with host-side role checks.

    The model decides to call a tool based on text it was given — text an attacker
    influences. So a tool call is authorised against the *current* principal every
    time, and a tool is never allowed to run for a caller below its ``min_role``
    regardless of how convincingly the prompt asks.
    """

    def __init__(
        self,
        loader: PluginLoader,
        *,
        audit: AuditLog | None = None,
        sources: list[Any] | None = None,
    ) -> None:
        self.loader = loader
        self.audit = audit or get_audit_log()
        self._sources: list[Any] = list(sources or [])

    def register_source(self, source: Any) -> None:
        """Add an external tool source (currently: an MCP server group).

        Deliberately the same registry and the same ``available_for`` filter. A second
        path for MCP tools would be a second place to remember the role check, and the
        one that gets forgotten is the one an attacker uses.
        """
        self._sources.append(source)

    def available_for(self, principal: Principal | None) -> list[dict[str, Any]]:
        """Tool schemas visible to this caller. Filtered, not just gated.

        Hiding a tool the caller cannot use is better than offering it and
        refusing: an offered-but-refused tool still confirms its existence and
        invites the model to keep trying.
        """
        role = principal.role if principal else Role.ANONYMOUS
        out: list[dict[str, Any]] = []
        for name, meta in self.loader.all_tools().items():
            required: Role = meta.get("min_role") or Role.MEMBER
            if role.rank < required.rank:
                continue
            out.append(
                {
                    "name": name,
                    "description": meta["description"],
                    "parameters": meta["parameters"],
                }
            )
        for source in self._sources:
            try:
                out.extend(source.schemas(principal))
            except Exception as exc:  # pragma: no cover - a source must not break chat
                logger.warning("tool source failed to list: %s", exc)
        return out

    async def _invoke_external(
        self, name: str, arguments: dict[str, Any], *, principal: Principal | None
    ) -> str:
        """Route an external tool call, audited like a plugin tool.

        The source decides authorisation — it is the only object that knows each
        server's ``min_role``. This method's job is that a refusal and a failure both
        land in the same audit stream as plugin calls, so an operator does not need a
        second place to look.
        """
        for source in self._sources:
            try:
                result = await source.call(name, arguments, principal=principal)
            except Exception as exc:
                self.audit.record(
                    kind="plugin",
                    action=f"tool:{name}",
                    outcome="deny",
                    principal=principal,
                    detail=f"external tool failed: {exc}",
                )
                logger.warning("external tool failed name=%s: %s", name, exc)
                return "错误：外部工具调用失败。"
            if result is None:
                continue
            self.audit.record(
                kind="plugin",
                action=f"tool:{name}",
                outcome="allow",
                principal=principal,
                detail="external tool",
            )
            return str(result)
        return "错误：没有这个工具。"

    async def invoke(
        self,
        name: str,
        arguments: dict[str, Any],
        *,
        principal: Principal | None,
        session_key: str = "",
    ) -> str:
        if name.startswith("mcp__"):
            return await self._invoke_external(name, arguments, principal=principal)

        meta = self.loader.all_tools().get(name)
        if meta is None:
            return "错误：没有这个工具。"

        required: Role = meta.get("min_role") or Role.MEMBER
        role = principal.role if principal else Role.ANONYMOUS
        if not principal or not principal.authenticated or role.rank < required.rank:
            self.audit.record(
                kind="plugin",
                action=f"tool:{name}",
                outcome="deny",
                principal=principal,
                detail=f"plugin={meta['plugin']} requires {required}, caller is {role}",
                plugin=meta["plugin"],
            )
            return "错误：没有权限使用该工具。"

        if not isinstance(arguments, dict):
            return "错误：参数格式不正确。"

        loaded = self.loader.get(meta["plugin"])
        if loaded is None:
            return "错误：工具所属插件未加载。"

        caller = CallerContext.from_principal(principal, session_key)
        loaded.context.remember_session(session_key)
        started = time.perf_counter()
        invocation = PluginInvocation(
            plugin=loaded.name, entry=f"tool:{name}", ok=False, duration_ms=0
        )
        try:
            with bind_caller(caller):
                raw = await asyncio.wait_for(
                    _maybe_await(meta["handler"](caller, arguments)),
                    timeout=_HANDLER_TIMEOUT,
                )
            invocation.ok = True
        except TimeoutError:
            invocation.error = "timeout"
            return "错误：工具执行超时。"
        except Exception as exc:
            invocation.error = type(exc).__name__
            logger.exception("plugin tool failed plugin=%s tool=%s", loaded.name, name)
            return "错误：工具执行失败。"
        finally:
            invocation.duration_ms = (time.perf_counter() - started) * 1000
            loaded.invocations += 1
            record_invocation(self.audit, loaded, invocation)

        # Tool results go into the model's context, so they get the strongest
        # treatment: scrubbed, capped, and framed as untrusted data by the caller.
        text = raw if isinstance(raw, str) else str(raw)
        text = scrub_plugin_output(text, max_chars=4000)
        if leaked_canary(text):
            self.audit.record(
                kind="plugin",
                action=f"tool:{name}",
                outcome="quarantine",
                detail=f"plugin={loaded.name} canary leak",
                plugin=loaded.name,
            )
            return "错误：工具返回了不安全的内容。"
        return text


async def dispatch_notice(
    loader: PluginLoader, *, caller: CallerContext, notice: dict[str, Any]
) -> None:
    """Fan out an inbound notice (join/leave/mute) to registered hooks.

    Notices are observation-only for the same reason messages are: they arrive
    before any sanitisation the reply path applies, and a hook that could act on
    them synchronously could interfere with the adapter's own bookkeeping.

    Errors are logged with the exception *type* only. A notice payload contains
    group and member ids; letting a plugin's exception message reach the log would
    publish exactly the data this path is most likely to mishandle.
    """
    for loaded in list(loader.loaded.values()):
        hooks = loaded.context._notice_hooks
        if not hooks:
            continue
        loaded.context.remember_session(caller.session_key)
        for hook in hooks:
            try:
                with bind_caller(caller):
                    await asyncio.wait_for(
                        _maybe_await(hook(caller, notice)), timeout=2.0
                    )
            except Exception as exc:
                logger.warning(
                    "plugin notice hook failed plugin=%s err=%s",
                    loaded.name,
                    type(exc).__name__,
                )


class PluginCronRunner:
    """Runs plugin-registered cron jobs.

    Kept deliberately simple and defensive. A plugin's cron job is unattended code
    that runs with no user present, so:

    * each run is audited (``cron:<name>``) whether it succeeds or fails — an
      unattended job that fails silently is indistinguishable from one that never
      ran, and both are worth knowing;
    * one job's failure never stops the others;
    * the callable receives only the ``CallerContext`` of the *plugin itself*
      (anonymous, no session), because there is no user to attribute the run to and
      inventing one would let a cron job act with a real user's privileges.

    Due-time evaluation lives here rather than being delegated entirely to APScheduler
    because the jobs appear and disappear at runtime (plugins are loaded and unloaded
    through the API), which would otherwise require adding and removing scheduler
    entries on every plugin lifecycle event, with a window where a half-registered job
    fires or is silently dropped. Ticking one runner over the current job set has a
    single source of truth: the loaded plugins.
    """

    #: A process that was asleep for an hour must not "catch up" by running every
    #: missed execution back to back — that turns a restart into a burst of work
    #: (and, for anything that sends messages, a burst of spam). A missed run is
    #: skipped and the schedule continues from now.
    def __init__(
        self,
        loader: PluginLoader,
        *,
        audit: AuditLog | None = None,
        timezone: str | None = None,
    ) -> None:
        self.loader = loader
        self.audit = audit or get_audit_log()
        # Fixed timezone, not the process default: a cron expression an operator
        # wrote as "09:00" must mean 09:00 for them, regardless of what TZ the
        # container happens to inherit. Invisible drift of an unattended job is
        # particularly hard to notice.
        self._tz = ZoneInfo(timezone or settings.default_timezone)
        self._next_due: dict[tuple[str, str], float] = {}

    # ------------------------------------------------------------------ schedule
    def _next_after(self, expr: str, ts: float) -> float:
        """First scheduled time strictly after ``ts``, as a POSIX timestamp."""
        from croniter import croniter

        base = datetime.fromtimestamp(ts, self._tz)
        nxt = croniter(expr, base).get_next(datetime)
        # croniter returns a naive datetime when handed an aware one in some
        # versions; re-attach the timezone rather than letting local time leak in.
        if nxt.tzinfo is None:
            nxt = nxt.replace(tzinfo=self._tz)
        return nxt.timestamp()

    def schedule(self) -> list[dict[str, Any]]:
        """Current job set with the wall-clock time each one fires next.

        Exposed so the management API can answer "is my cron actually registered?"
        — a question that otherwise requires waiting for the job to (not) run.
        """
        out: list[dict[str, Any]] = []
        for (plugin, name), due in self._next_due.items():
            out.append(
                {
                    "plugin": plugin,
                    "name": name,
                    "next_run_at": due,
                    "next_run_iso": datetime.fromtimestamp(due, self._tz).isoformat(),
                }
            )
        return sorted(out, key=lambda j: j["next_run_at"])

    async def run_due(self, *, now: float | None = None) -> int:
        """Run the jobs whose scheduled time has passed. Returns how many ran.

        Called on a fixed tick by the application scheduler. Jobs that are not yet
        due are skipped; the first time a job is seen it is *scheduled* rather than
        executed, so loading a plugin does not immediately run every job it
        registered.
        """
        ts = time.time() if now is None else now
        ran = 0
        live: set[tuple[str, str]] = set()

        for loaded in list(self.loader.loaded.values()):
            for job in loaded.context.cron_jobs:
                key = (loaded.name, str(job["name"]))
                live.add(key)
                due = self._next_due.get(key)
                if due is None:
                    self._next_due[key] = self._next_after(str(job["expr"]), ts)
                    continue
                if ts < due:
                    continue
                # Reschedule *before* running: a job that raises, or a tick that
                # arrives late, must not leave the entry in the past and re-fire it
                # on the next tick.
                self._next_due[key] = self._next_after(str(job["expr"]), ts)
                ran += 1
                await self._run_job(loaded, job)

        # A plugin unloaded (or reloaded with different jobs) drops its schedule;
        # otherwise an unloaded job's timestamp lingers and would fire on reload.
        for key in [k for k in self._next_due if k not in live]:
            del self._next_due[key]
        return ran

    async def _run_job(self, loaded: LoadedPlugin, job: dict[str, Any]) -> None:
        started = time.perf_counter()
        caller = CallerContext(
            user_id="",
            display_name="",
            role="anonymous",
            session_key="",
            scene="cron",
        )
        ok = True
        err = ""
        try:
            # Cron has no user and no session: it binds an anonymous caller so
            # ``ctx.memory`` raises instead of reading whatever session happened to
            # run last.
            with bind_caller(caller):
                await asyncio.wait_for(
                    _maybe_await(job["handler"](caller)), timeout=_HANDLER_TIMEOUT
                )
        except TimeoutError:
            ok, err = False, "timeout"
        except Exception as exc:
            ok, err = False, type(exc).__name__
            logger.warning(
                "plugin cron failed plugin=%s job=%s err=%s",
                loaded.name,
                job["name"],
                type(exc).__name__,
            )
        self.audit.record(
            kind="plugin",
            action=f"cron:{job['name']}",
            outcome="allow" if ok else "block",
            detail=f"plugin={loaded.name} {(time.perf_counter() - started) * 1000:.0f}ms "
            f"{err}".strip(),
            plugin=loaded.name,
        )


class PluginManager:
    """Convenience façade tying loader + stages + tool registry together."""

    def __init__(self, loader: PluginLoader) -> None:
        self.loader = loader
        self.tools = PluginToolRegistry(loader)
        self.cron = PluginCronRunner(loader)
        self.sender = None
        """Optional ``async (session_key, text) -> None`` installed by the runtime."""

    def install_sender(self, sender) -> None:
        self.sender = sender
        for loaded in self.loader.loaded.values():
            loaded.context._init_runtime_hooks(sender=sender)
        self._sender = sender

    def install_isolation(self, *, supervisor, memory=None, kb=None) -> None:
        """Wire the process supervisor to a host-side authorization dispatcher.

        ``SurfaceRouter`` is bound as the supervisor's surface handler, which is what
        makes every callback from a worker pass through the host's capability check.
        The router needs the *guard and ledger of each specific plugin*, so it is
        constructed per plugin at load time rather than once here; this method only
        installs the factory and keeps the stores handy.

        Refusing to run without a handler is deliberate: a supervisor with no router
        would start workers that could not authorize anything, which is safe but
        useless — better to fail at wiring time than to discover it per call.
        """

        self.supervisor = supervisor
        self._surface_memory = memory
        self._surface_kb = kb
        self.loader.manager_ref = self

        supervisor.bind_surface_handler(self._dispatch_surface)

    async def _dispatch_surface(
        self, plugin: str, surface: str, args: dict[str, Any], caller
    ):
        """Route a worker callback to *that plugin's* router.

        ``plugin`` comes from the worker's own identity (which pipe the frame arrived
        on), and ``caller`` is what the host recorded for this invocation. Neither is
        taken from the request body, so a hostile plugin can neither impersonate
        another plugin nor name another caller — the two things it would need to read
        someone else's data.
        """
        router = getattr(self, "_surfaces", {}).get(plugin)
        if router is None:
            raise PermissionError("no surface router for this plugin")
        return await router.dispatch(surface, args, caller)

    def attach_surface_router(self, plugin: str, *, guard, ledger, storage=None) -> None:
        """Create the per-plugin router. Called by the loader right before a worker
        starts, so the guard and ledger are the ones that belong to this plugin."""
        from soapbot.plugins.surfaces import SurfaceRouter

        if not hasattr(self, "_surfaces"):
            self._surfaces: dict[str, Any] = {}
        self._surfaces[plugin] = SurfaceRouter(
            guard=guard,
            plugin=plugin,
            memory=getattr(self, "_surface_memory", None),
            kb=getattr(self, "_surface_kb", None),
            sender=getattr(self, "_sender", None),
            ledger=ledger,
            audit=self.loader.audit,
            storage=None,
        )
        # The sender may be installed after the first plugin loads; keep the router's
        # view current so a later ``install_sender`` is not silently ignored.
        self.supervisor._surface_handler = self._dispatch_surface

    def has_notice_hooks(self) -> bool:
        return any(
            p.context._notice_hooks for p in self.loader.loaded.values()
        )

    async def on_notice(self, *, caller: CallerContext, notice: dict[str, Any]) -> None:
        await dispatch_notice(self.loader, caller=caller, notice=notice)

    async def load(self, name: str, *, force: bool = False) -> LoadedPlugin:
        loaded = await self.loader.load(name, force=force)
        loaded.context._init_runtime_hooks(sender=self.sender)
        return loaded

    async def reload(self, name: str) -> LoadedPlugin:
        loaded = await self.loader.reload(name)
        loaded.context._init_runtime_hooks(sender=self.sender)
        return loaded

    async def unload(self, name: str) -> None:
        await self.loader.unload(name)
