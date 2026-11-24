"""P2 lifecycle hardening, driven through real isolated workers.

Three findings from the audit, all of the same shape — a host decision that was
recorded but never *made effective*:

* **S-PLUG-05** — ``revoke`` withdrew the approval record while the running worker
  kept the frozen ``CapabilityGrant`` it took at load time. The gesture an operator
  reaches for while a plugin is misbehaving therefore did nothing until a restart.
* **S-PLUG-03** — the ready frame is plugin-authored and was unbounded. One plugin
  could register thousands of hooks and make every inbound message walk all of them.
* **S-PLUG-07** — the child installed a ``soapbot`` stub in ``sys.modules``, but
  nothing stopped a plugin from deleting the stub and importing the *real* host
  package off the interpreter's path.

Each is pinned from the outside: load a real worker, then observe the process.
"""

from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

import pytest

from soapbot.plugins.loader import MAX_PLUGIN_HOOKS, PluginLoader, PluginLoadError
from soapbot.plugins.supervisor import PluginSupervisor
from soapbot.security.audit import AuditLog

MANIFEST = """\
name: {name}
version: 1.0.0
entry: main:{cls}
description: "生命周期加固回归用"
capabilities:
  - command
  - message
min_host_version: "0.1.0"
"""

#: Registers ``hook_count`` message hooks and one probe command.
MAIN_HOOKS = '''\
from soapbot.plugins.base import Plugin

class {cls}(Plugin):
    def setup(self, ctx):
        for index in range({hook_count}):
            def _hook(caller, text, _index=index):
                return None
            _hook.__name__ = "hook_%d" % index
            ctx.on_message(_hook)

        @ctx.command("{cmd}", description="probe", usage="/{cmd}")
        def probe(caller, args):
            return {{"hooks": {hook_count}}}
'''

#: Reproduces the S-PLUG-07 attack: drop the stub, then import the host package.
MAIN_HOST_IMPORT = '''\
import sys

from soapbot.plugins.base import Plugin


def _host_import_outcome():
    """Delete the stub and see whether the real ``soapbot`` is reachable."""
    for name in [n for n in sys.modules if n == "soapbot" or n.startswith("soapbot.")]:
        sys.modules.pop(name, None)
    try:
        import soapbot  # noqa: F401
        import soapbot.core  # noqa: F401
    except ImportError:
        return "blocked"
    return "host-imported"


class {cls}(Plugin):
    def setup(self, ctx):
        outcome = _host_import_outcome()

        @ctx.command("{cmd}", description="probe", usage="/{cmd}")
        def probe(caller, args):
            return {{"outcome": outcome}}
'''


@pytest.fixture
def plugins_dir(tmp_path: Path) -> Path:
    (tmp_path / "plugins").mkdir()
    return tmp_path / "plugins"


def _loader(plugins_dir: Path) -> PluginLoader:
    loader = PluginLoader(
        plugins_dir=plugins_dir,
        audit=AuditLog(),
        supervisor=PluginSupervisor(),
        allow_untrusted=True,
    )
    from soapbot.plugins.dispatch import PluginManager

    PluginManager(loader).install_isolation(supervisor=loader.supervisor)
    return loader


def _write_plugin(
    plugins_dir: Path, name: str, cls: str, main: str, *, cmd: str = "probe"
) -> None:
    directory = plugins_dir / name
    directory.mkdir()
    (directory / "plugin.yaml").write_text(
        MANIFEST.format(name=name, cls=cls), encoding="utf-8"
    )
    (directory / "main.py").write_text(
        main.format(cls=cls, cmd=cmd, hook_count=MAX_PLUGIN_HOOKS + 1),
        encoding="utf-8",
    )


def _caller():
    from soapbot.plugins.context import CallerContext

    return CallerContext(
        user_id="u1",
        display_name="Op",
        role="admin",
        session_key="qq:group:7",
        scene="group",
        group_id="7",
    )


# ---------------------------------------------------------------- S-PLUG-05 revoke


async def test_revoke_stops_a_running_plugin(plugins_dir: Path) -> None:
    """The whole point of revoking mid-incident: the powers stop now, not at restart.

    ``CapabilityGuard`` is built from a grant frozen at load time, so withdrawing the
    approval record alone left the worker free to keep calling ``send``/``memory``
    with the old grant until the process was reloaded.
    """
    loader = _loader(plugins_dir)
    _write_plugin(
        plugins_dir,
        "revoke-probe",
        "RevokeProbe",
        MAIN_HOOKS.replace("{hook_count}", "1"),
        cmd="rv-probe",
    )
    manifest = next(m for m in loader.discover().found)
    loader.approve_from_manifest(manifest)
    loaded = await loader.load(manifest.name, force=True)
    worker = loaded.worker
    assert worker is not None and worker.alive

    loader.revoke(manifest.name, actor="operator")
    for _ in range(200):
        if not loader._pending_unloads:
            break
        import asyncio

        await asyncio.sleep(0.01)

    assert manifest.name not in loader._loaded, "the plugin is still registered as loaded"
    assert loader.supervisor.worker(manifest.name) is None, "the worker process survived"
    assert not worker.alive, "the worker process is still running"
    assert manifest.name not in loader._approved, "revocation did not withdraw approval"

    revokes = [
        record
        for record in loader.audit.recent(limit=500)
        if record.get("action") == "revoke" and record.get("plugin") == manifest.name
    ]
    assert revokes, "revocation was not audited"
    assert "unloaded" in revokes[-1].get("detail", ""), (
        "the audit line cannot distinguish 'revoked and stopped' from 'revoked, still running'"
    )


def test_revoke_outside_an_event_loop_still_withdraws_the_approval() -> None:
    """A CLI/script revoke has no running loop to schedule an unload on.

    It must not crash or pretend it stopped a process; it withdraws the approval (so
    the plugin cannot come back) and says so in the log.
    """
    loader = PluginLoader(plugins_dir=Path("."), audit=AuditLog())
    loader._approved["p"] = object()  # type: ignore[assignment]
    loader._loaded["p"] = object()  # type: ignore[assignment]

    loader.revoke("p", actor="cli")

    assert "p" not in loader._approved
    assert "p" in loader._loaded, "no loop means no unload was possible"
    assert not loader._pending_unloads


# ---------------------------------------------------------- S-PLUG-03 ready caps


async def test_a_hook_flood_is_refused_and_the_process_stopped(plugins_dir: Path) -> None:
    """The ready frame is plugin-authored, so its size is an attack surface.

    Every inbound message walks every registered hook, and the per-hook timeout bounds
    one call rather than the sum. One plugin declaring tens of thousands of hooks
    therefore stalls the pipeline for *all* sessions; the fix is to refuse the frame.
    """
    loader = _loader(plugins_dir)
    _write_plugin(plugins_dir, "hook-flood", "HookFlood", MAIN_HOOKS, cmd="flood-probe")
    manifest = next(m for m in loader.discover().found)
    loader.approve_from_manifest(manifest)

    with pytest.raises(PluginLoadError, match="hooks"):
        await loader.load(manifest.name, force=True)

    assert loader.supervisor.worker(manifest.name) is None, (
        "a refused plugin left its process running"
    )
    assert manifest.name not in loader._loaded
    blocks = [
        record
        for record in loader.audit.recent(limit=500)
        if record.get("action") == "load" and record.get("outcome") == "block"
    ]
    assert any("cap" in record.get("detail", "") for record in blocks), (
        "the refusal was not audited with the reason"
    )


async def test_a_normal_plugin_still_loads_under_the_caps(plugins_dir: Path) -> None:
    """A cap that rejects real plugins would be worse than the bug."""
    loader = _loader(plugins_dir)
    _write_plugin(
        plugins_dir,
        "normal",
        "NormalPlugin",
        MAIN_HOOKS.replace("{hook_count}", "2"),
        cmd="normal-probe",
    )
    manifest = next(m for m in loader.discover().found)
    loader.approve_from_manifest(manifest)
    loaded = await loader.load(manifest.name, force=True)
    try:
        assert len(loaded.worker.hooks) == 2
    finally:
        await loader.unload(manifest.name)


# ------------------------------------------------------- S-PLUG-07 host package


async def test_plugin_process_cannot_import_the_host_package(plugins_dir: Path) -> None:
    """Deleting the stub must not expose the real package.

    ``_install_stubs`` puts a ``soapbot`` stub in ``sys.modules``; ``sys.modules`` is
    consulted before any finder, so the stub masking the host looked like a boundary.
    It was not: ``del sys.modules["soapbot"]`` followed by ``import soapbot`` found the
    real package on the interpreter's path and gave the plugin the host's own modules
    — memory store, audit log, config with every credential.
    """
    loader = _loader(plugins_dir)
    _write_plugin(
        plugins_dir, "host-import", "HostImport", MAIN_HOST_IMPORT, cmd="host-probe"
    )
    manifest = next(m for m in loader.discover().found)
    loader.approve_from_manifest(manifest)
    loaded = await loader.load(manifest.name, force=True)
    try:
        out = await loaded.worker.invoke("host-probe", caller=_caller(), args=[])
        assert out["outcome"] == "blocked", (
            "the plugin process reached the real host package"
        )
    finally:
        await loader.unload(manifest.name)
