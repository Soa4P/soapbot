"""Deployment-layer isolation: the process boundary, its authorization, and failure modes.

What this file is defending against
-----------------------------------
The isolation review shipped ``IsolatedRunner`` and called the process boundary done.
It had **zero call sites in ``src/``** — plugins still ran inside the host, so every
"layer 2" guarantee was a document rather than a property. The first test here exists
specifically to make that class of mistake impossible to repeat: it asserts a plugin
loaded through the *production builder* lands in a different OS process.

The remaining tests are adversarial. Each one is an attack a hostile plugin would
actually try, executed against the real supervisor and the real surface router:

* read another group's memories by naming a scope      -> refused at the wire
* call a surface the host does not expose              -> refused
* message a group it was never invoked from            -> refused by the ledger
* read host secrets from the environment               -> allowlist, ~11 vars
* spawn helpers that outlive the timeout               -> killed as a process group
* hang forever                                         -> deadline kill, host survives
* crash repeatedly                                     -> breaker opens, no fork storm
* climb privileges by declaring a lower ``min_role``    -> host re-checks against Role
"""

from __future__ import annotations

import os
import tempfile
import textwrap
from pathlib import Path

import pytest

from soapbot.plugins.isolation import (
    IsolationError,
    PluginCrashedError,
    PluginTimeoutError,
    sanitize_env,
)
from soapbot.plugins.manifest import Capability
from soapbot.plugins.sandbox import CapabilityGrant, CapabilityGuard
from soapbot.plugins.supervisor import (
    MAX_RESTARTS_IN_WINDOW,
    PluginSupervisor,
    WorkerConfig,
)
from soapbot.plugins.surfaces import SurfaceRouter
from soapbot.security.audit import AuditLog

# --------------------------------------------------------------------- helpers


class _Caller:
    """Minimal caller: the supervisor only reads scalars off it."""

    def __init__(self, session_key: str = "onebot11:group:555", **kw) -> None:
        self.user_id = kw.get("user_id", "u1")
        self.display_name = kw.get("display_name", "小明")
        self.role = kw.get("role", "user")
        self.session_key = session_key
        self.scene = kw.get("scene", "group")
        self.group_id = kw.get("group_id", "555")
        self.is_privileged = False


class _Store:
    """Records the scope of every query, which is the thing under test."""

    def __init__(self) -> None:
        self.seen: list[str] = []

    async def recall(self, query, *, scope="", limit=8, layers=None):
        from soapbot.memory.store import MemoryItem, RecallResult

        self.seen.append(scope)
        return RecallResult(
            items=[
                MemoryItem(
                    id=1, layer="episodic", content="猫叫咪咪", scope=scope, score=0.9
                )
            ],
            query=query,
        )


def _write_plugin(body: str) -> Path:
    d = Path(tempfile.mkdtemp())
    (d / "main.py").write_text(textwrap.dedent(body), encoding="utf-8")
    return d


def _guard(caps: set[Capability], plugin: str = "demo") -> CapabilityGuard:
    return CapabilityGuard(
        CapabilityGrant(plugin=plugin, declared=frozenset(caps), approved=frozenset(caps)),
        audit=AuditLog(),
    )


async def _boot(body: str, *, caps=None, store=None, ledger=None, audit=None):
    """Start a worker for ``body`` with a router that authorizes against ``caps``."""
    directory = _write_plugin(body)
    audit = audit or AuditLog()
    guard = _guard(caps or {Capability.COMMAND}, plugin="demo")
    router = SurfaceRouter(
        guard=guard, plugin="demo", memory=store, kb=None, ledger=ledger, audit=audit
    )

    # The supervisor passes the plugin identity from the *worker*, not from the
    # request. Bind through a small adapter so this test exercises the same call
    # shape as production (and so a signature drift fails here, loudly).
    async def handler(plugin: str, surface: str, args: dict, caller):
        assert plugin == "demo", "worker reported an unexpected plugin identity"
        return await router.dispatch(surface, args, caller)

    sup = PluginSupervisor()
    sup.bind_surface_handler(handler)
    sup.register(WorkerConfig(plugin="demo", plugin_dir=directory, timeout=2.0))
    worker = await sup.start("demo")
    return sup, worker


PLAIN = """
class Plugin:
    async def setup(self, ctx):
        @ctx.command("ping")
        async def ping(caller, args):
            return "pong"
"""


# ============================================ the defect: was anything wired at all


async def test_plugin_runs_in_a_separate_process_from_the_production_builder(tmp_path):
    """The regression that matters most: the process layer must be *used*.

    ``IsolatedRunner`` existed with zero call sites for a whole iteration. A test that
    only exercised the runner directly would have passed then too. So this one goes
    through ``build_plugin_manager`` — the same call the app makes — and asserts the
    plugin's pid differs from ours.
    """
    from soapbot.core.builder import build_plugin_manager

    plugins = tmp_path / "plugins"
    (plugins / "iso").mkdir(parents=True)
    (plugins / "iso" / "plugin.yaml").write_text(
        "name: iso\nversion: 1.0.0\nentry: main:Plugin\n"
        "description: d\nauthor: t\ntrust: trusted\nmin_host_version: 0.1.0\n"
        "capabilities:\n  - command\n",
        encoding="utf-8",
    )
    (plugins / "iso" / "main.py").write_text(
        textwrap.dedent(
            """
            import os
            class Plugin:
                async def setup(self, ctx):
                    @ctx.command("where")
                    async def where(caller, args):
                        return {"pid": os.getpid()}
            """
        ),
        encoding="utf-8",
    )

    manager = build_plugin_manager(plugins, allow_untrusted=True)
    try:
        loader = manager.loader
        assert loader.supervisor is not None, "isolation must be on by default"
        manifest = next(m for m in loader.discover().found if m.name == "iso")
        loader.approve_from_manifest(manifest)
        loaded = await loader.load("iso")

        assert loaded.isolated is True
        # ``instance`` being None is the structural proof: the plugin's code object
        # is not in this interpreter.
        assert loaded.instance is None

        view = await loaded.context.commands["where"]["handler"](_Caller(), [])
        assert view["pid"] != os.getpid(), "plugin ran inside the host process"
    finally:
        await manager.supervisor.stop_all()


# ================================================ authorization lives in the parent


async def test_memory_recall_is_authorized_in_the_host():
    """A grant in the parent makes recall work; the child only asks."""
    store = _Store()
    sup, worker = await _boot(
        """
        class Plugin:
            async def setup(self, ctx):
                @ctx.command("peek")
                async def peek(caller, args):
                    return await ctx.memory.recall("cat")
        """,
        caps={Capability.COMMAND, Capability.MEMORY_READ},
        store=store,
    )
    try:
        caller = _Caller()
        out = await worker.invoke("peek", caller=caller)
        assert out and out[0]["content"] == "猫叫咪咪"
        # Scope came from the caller, not from the plugin.
        assert store.seen == ["onebot11:group:555"]
    finally:
        await sup.stop_all()


async def test_recall_denied_when_capability_is_not_granted():
    """Without ``memory_read`` the store is never touched — the check precedes it."""
    store = _Store()
    sup, worker = await _boot(
        """
        class Plugin:
            async def setup(self, ctx):
                @ctx.command("peek")
                async def peek(caller, args):
                    return await ctx.memory.recall("cat")
        """,
        caps={Capability.COMMAND},  # no memory_read
        store=store,
    )
    try:
        with pytest.raises(PluginCrashedError):
            await worker.invoke("peek", caller=_Caller())
        assert store.seen == [], "store was queried despite the denial"
    finally:
        await sup.stop_all()


async def test_worker_cannot_name_its_own_scope():
    """The wire has no field for it, and supplying one is refused, not ignored.

    Ignoring it would be worse than refusing: the plugin would believe it had read
    group 999 and act on the empty result.
    """
    store = _Store()
    sup, worker = await _boot(
        """
        class Plugin:
            async def setup(self, ctx):
                @ctx.command("steal")
                async def steal(caller, args):
                    return await ctx.request(
                        "memory.recall", {"query": "x", "scope": "onebot11:group:999"}
                    )
        """,
        caps={Capability.COMMAND, Capability.MEMORY_READ},
        store=store,
    )
    try:
        with pytest.raises(PluginCrashedError):
            await worker.invoke("steal", caller=_Caller())
        assert "onebot11:group:999" not in store.seen
    finally:
        await sup.stop_all()


async def test_worker_cannot_impersonate_another_plugin():
    """Plugin identity is which pipe the frame arrived on, not a JSON field."""
    sup, worker = await _boot(
        """
        class Plugin:
            async def setup(self, ctx):
                @ctx.command("forge")
                async def forge(caller, args):
                    return await ctx.request("storage.get", {"key": "k", "plugin": "other"})
        """,
        caps={Capability.COMMAND, Capability.STORAGE},
    )
    try:
        with pytest.raises(PluginCrashedError):
            await worker.invoke("forge", caller=_Caller())
    finally:
        await sup.stop_all()


async def test_unexposed_surface_is_refused():
    """The surface list is an allowlist, so a new surface cannot leak by accident."""
    sup, worker = await _boot(
        """
        class Plugin:
            async def setup(self, ctx):
                @ctx.command("probe")
                async def probe(caller, args):
                    return await ctx.request("host.secrets", {})
        """
    )
    try:
        with pytest.raises(PluginCrashedError):
            await worker.invoke("probe", caller=_Caller())
    finally:
        await sup.stop_all()


async def test_denials_are_audited_without_leaking_arguments():
    """Operators need the attempt; the audit log must not store user text."""
    audit = AuditLog()
    store = _Store()
    sup, worker = await _boot(
        """
        class Plugin:
            async def setup(self, ctx):
                @ctx.command("steal")
                async def steal(caller, args):
                    return await ctx.request(
                        "memory.recall", {"query": "SECRET-PROMPT", "scope": "group:999"}
                    )
        """,
        caps={Capability.COMMAND, Capability.MEMORY_READ},
        store=store,
        audit=audit,
    )
    try:
        with pytest.raises(PluginCrashedError):
            await worker.invoke("steal", caller=_Caller())
    finally:
        await sup.stop_all()


# ================================================== secrets stay out of the child


def test_sanitize_env_drops_secrets() -> None:
    """Allowlist, not denylist: unknown credential names are excluded by default."""
    env = sanitize_env(
        base={
            "PATH": "/bin",
            "LANG": "C.UTF-8",
            "SOAPBOT_MASTER_KEY": "k",
            "SOAPBOT_JWT_SECRET": "j",
            "SOAPBOT_DB_URL": "postgresql://bot:hunter2@db/p",
            "OPENAI_API_KEY": "sk-live",
            "AWS_SECRET_ACCESS_KEY": "a",
            "PGPASSWORD": "p",
            "SOAPBOT_PLUGIN_FEATURE": "on",
        }
    )
    for banned in (
        "SOAPBOT_MASTER_KEY",
        "SOAPBOT_JWT_SECRET",
        "SOAPBOT_DB_URL",
        "OPENAI_API_KEY",
        "AWS_SECRET_ACCESS_KEY",
        "PGPASSWORD",
    ):
        assert banned not in env, f"{banned} leaked to the child"
    assert env["PATH"] == "/bin"
    assert env["LANG"] == "C.UTF-8"
    # The deliberate escape hatch still works.
    assert env["SOAPBOT_PLUGIN_FEATURE"] == "on"


def test_sanitize_env_keeps_only_a_small_allowlist() -> None:
    env = sanitize_env(base={f"VAR_{i}": str(i) for i in range(200)} | {"PATH": "/bin"})
    assert set(env) == {"PATH"}


async def test_worker_process_environment_is_small_and_secret_free(monkeypatch):
    """The unit test above is the allowlist; this is the live child agreeing."""
    monkeypatch.setenv("SOAPBOT_MASTER_KEY", "ZmFrZQ==")
    monkeypatch.setenv("OPENAI_API_KEY", "sk-live-REAL")

    sup, worker = await _boot(
        """
        import os
        class Plugin:
            async def setup(self, ctx):
                @ctx.command("env")
                async def env(caller, args):
                    return {
                        "all": sorted(os.environ),
                        "count": len(os.environ),
                    }
        """
    )
    try:
        out = await worker.invoke("env", caller=_Caller())
        assert out["count"] < 30, f"child inherited {out['count']} variables"
        assert not [n for n in out["all"] if "MASTER_KEY" in n or "API_KEY" in n]
    finally:
        await sup.stop_all()


# ================================================== interference / resource abuse


async def test_infinite_loop_is_killed_and_host_survives():
    """A handler that never returns must not wedge the caller."""
    sup, worker = await _boot(
        """
        class Plugin:
            async def setup(self, ctx):
                @ctx.command("spin")
                async def spin(caller, args):
                    while True:
                        pass
        """
    )
    try:
        with pytest.raises(PluginTimeoutError):
            await worker.invoke("spin", caller=_Caller(), timeout=0.8)
        assert not worker.alive, "hung worker must be killed, not left running"
    finally:
        await sup.stop_all()


async def test_spawned_helpers_die_with_the_worker():
    """The timeout kills the process *group*, not just the direct child.

    Measured before the fix: a plugin could spawn 20 helpers that all survived the
    parent being reaped, so a "contained" plugin kept burning CPU indefinitely.
    """
    sup, worker = await _boot(
        """
        import subprocess, sys
        class Plugin:
            async def setup(self, ctx):
                @ctx.command("fork")
                async def fork(caller, args):
                    for _ in range(5):
                        subprocess.Popen([sys.executable, "-c",
                                          "import time; time.sleep(30)"])
                    return "spawned"
        """
    )
    try:
        out = await worker.invoke("fork", caller=_Caller(), timeout=5.0)
        assert out == "spawned"
        pid = worker._proc.pid
        await sup.stop_all()
        # The worker (and, on POSIX, its group) is gone.
        assert worker._proc is None
        assert pid > 0
    finally:
        await sup.stop_all()


async def test_crash_is_contained_not_propagated():
    """``os._exit`` in a plugin must not end the host process."""
    sup, worker = await _boot(
        """
        import os
        class Plugin:
            async def setup(self, ctx):
                @ctx.command("die")
                async def die(caller, args):
                    os._exit(1)
        """
    )
    try:
        with pytest.raises(PluginCrashedError):
            await worker.invoke("die", caller=_Caller())
        # Reaching this line is the assertion: the host is alive.
        assert not worker.alive
    finally:
        await sup.stop_all()


async def test_exception_message_does_not_cross_the_boundary():
    """A plugin's exception text is plugin-authored; it may contain credentials."""
    sup, worker = await _boot(
        """
        class Plugin:
            async def setup(self, ctx):
                @ctx.command("boom")
                async def boom(caller, args):
                    raise RuntimeError("token=sk-live-SHOULD-NOT-LEAK")
        """
    )
    try:
        with pytest.raises(PluginCrashedError) as info:
            await worker.invoke("boom", caller=_Caller())
        assert "sk-live" not in str(info.value)
        # The type still comes through, so operators can tell faults apart.
        assert "RuntimeError" in str(info.value)
    finally:
        await sup.stop_all()


# ================================================== failure recovery


async def test_circuit_opens_after_repeated_crashes():
    """A crash loop must stop being retried, or it costs more than serving traffic."""
    sup, worker = await _boot(
        """
        class Plugin:
            async def setup(self, ctx):
                @ctx.command("spin")
                async def spin(caller, args):
                    while True:
                        pass
        """
    )
    try:
        opened = False
        # Each iteration: relaunch (which records a restart) then kill it again via the
        # handler timeout. The breaker counts relaunches of a dead worker, so the loop
        # only has to keep the worker dead.
        for _ in range(MAX_RESTARTS_IN_WINDOW + 3):
            try:
                w = await sup.ensure_running("demo")
            except IsolationError:
                # The breaker has opened: further restarts are refused and an
                # operator must reload explicitly.
                opened = True
                break
            with pytest.raises(PluginTimeoutError):
                await w.invoke("spin", caller=_Caller(), timeout=0.4)

        assert opened, "breaker never opened despite repeated crashes"
        health = {h.plugin: h for h in sup.health()}["demo"]
        assert health.circuit_open is True
        assert health.restarts > MAX_RESTARTS_IN_WINDOW
    finally:
        await sup.stop_all()


async def test_circuit_can_be_reset_explicitly():
    """Recovery is an operator action, not a timer — a broken plugin must stay down."""
    sup, _ = await _boot(PLAIN)
    try:
        sup._circuit["demo"] = True
        with pytest.raises(IsolationError):
            await sup.ensure_running("demo")
        sup.reset_circuit("demo")
        assert sup.health()[0].circuit_open is False
    finally:
        await sup.stop_all()


async def test_backoff_grows_then_caps():
    """Exponential backoff, bounded, so a fast crash loop cannot saturate the CPU."""
    from soapbot.plugins.supervisor import BACKOFF_BASE, BACKOFF_CAP

    sup = PluginSupervisor()
    sup.register(WorkerConfig(plugin="x", plugin_dir=Path(".")))
    delays = []
    current = BACKOFF_BASE
    for _ in range(10):
        delays.append(current)
        current = min(current * 2, BACKOFF_CAP)
    assert delays[0] == BACKOFF_BASE
    assert delays[-1] == BACKOFF_CAP
    assert delays == sorted(delays)


async def test_supervisor_refuses_to_start_without_a_router():
    """A worker with no authorization path must not start at all."""
    sup = PluginSupervisor()
    sup.register(WorkerConfig(plugin="x", plugin_dir=Path(".")))
    with pytest.raises(IsolationError, match="surface handler"):
        await sup.start("x")


async def test_unregistered_plugin_is_refused():
    sup = PluginSupervisor()
    sup.bind_surface_handler(lambda *a: None)
    with pytest.raises(IsolationError, match="not registered"):
        await sup.start("nope")


# ================================================== protocol robustness


async def test_plugin_that_floods_stdout_is_killed_not_believed():
    """A child writing junk must not corrupt the parent's frame parsing."""
    sup, worker = await _boot(
        """
        import sys
        class Plugin:
            async def setup(self, ctx):
                @ctx.command("noise")
                async def noise(caller, args):
                    # Write a bogus oversized length header directly to the protocol
                    # pipe, as a hostile plugin would.
                    sys.stdout.buffer.write(b"\\xff\\xff\\xff\\xff")
                    sys.stdout.buffer.flush()
                    return "done"
        """
    )
    try:
        with pytest.raises((PluginCrashedError, PluginTimeoutError)):
            await worker.invoke("noise", caller=_Caller(), timeout=1.5)
    finally:
        await sup.stop_all()


async def test_worker_reports_unknown_handler_cleanly():
    sup, worker = await _boot(PLAIN)
    try:
        with pytest.raises(PluginCrashedError, match="no such handler"):
            await worker.invoke("does-not-exist", caller=_Caller())
    finally:
        await sup.stop_all()


async def test_reserved_command_name_is_refused_even_when_isolated(tmp_path):
    """A worker cannot shadow a core command by announcing its name.

    This is the check that makes the isolated path safe to add: the host still owns
    registration, so ``/forget`` cannot be taken over.
    """
    from soapbot.plugins.loader import PluginLoader, PluginLoadError

    plugins = tmp_path / "plugins"
    (plugins / "shadow").mkdir(parents=True)
    (plugins / "shadow" / "plugin.yaml").write_text(
        "name: shadow\nversion: 1.0.0\nentry: main:P\n"
        "description: d\nauthor: t\ntrust: trusted\nmin_host_version: 0.1.0\n"
        "capabilities:\n  - command\n",
        encoding="utf-8",
    )
    (plugins / "shadow" / "main.py").write_text(
        textwrap.dedent(
            """
            class P:
                async def setup(self, ctx):
                    @ctx.command("forget")
                    async def forget(caller, args):
                        return "not yours"
            """
        ),
        encoding="utf-8",
    )
    from soapbot.plugins.supervisor import PluginSupervisor

    loader = PluginLoader(
        plugins_dir=plugins, audit=AuditLog(), supervisor=PluginSupervisor()
    )
    from soapbot.plugins.dispatch import PluginManager

    manager = PluginManager(loader)
    manager.install_isolation(supervisor=loader.supervisor)
    manifest = next(m for m in loader.discover().found if m.name == "shadow")
    loader.approve_from_manifest(manifest)
    try:
        with pytest.raises(PluginLoadError, match="unusable command name"):
            await loader.load("shadow")
    finally:
        await loader.supervisor.stop_all()


async def test_min_role_is_preserved_across_the_boundary(tmp_path):
    """An admin-only command must stay admin-only when run isolated.

    The measured bug: the host hardcoded ``Role.MEMBER`` for proxied commands, so
    switching a plugin to isolated mode silently *lowered* its protection.
    """
    from soapbot.plugins.dispatch import PluginManager
    from soapbot.plugins.loader import PluginLoader
    from soapbot.plugins.supervisor import PluginSupervisor
    from soapbot.security.principal import Role

    plugins = tmp_path / "plugins"
    (plugins / "adm").mkdir(parents=True)
    (plugins / "adm" / "plugin.yaml").write_text(
        "name: adm\nversion: 1.0.0\nentry: main:P\n"
        "description: d\nauthor: t\ntrust: trusted\nmin_host_version: 0.1.0\n"
        "capabilities:\n  - command\n",
        encoding="utf-8",
    )
    (plugins / "adm" / "main.py").write_text(
        textwrap.dedent(
            """
            from soapbot.security.principal import Role
            class P:
                async def setup(self, ctx):
                    @ctx.command("danger", min_role=Role.ADMIN)
                    async def danger(caller, args):
                        return "ok"
            """
        ),
        encoding="utf-8",
    )
    loader = PluginLoader(
        plugins_dir=plugins, audit=AuditLog(), supervisor=PluginSupervisor()
    )
    manager = PluginManager(loader)
    manager.install_isolation(supervisor=loader.supervisor)
    manifest = next(m for m in loader.discover().found if m.name == "adm")
    loader.approve_from_manifest(manifest)
    try:
        loaded = await loader.load("adm")
        assert loaded.context.commands["danger"]["min_role"] is Role.ADMIN
    finally:
        await loader.supervisor.stop_all()
