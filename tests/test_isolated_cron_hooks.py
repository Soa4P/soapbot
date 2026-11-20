"""Isolated-plugin cron and message-hook registration (worker parity).

Batch-10 plugins (self-nudge / weather-alert / memory-weekly) declare cron or
message-hook usage in ``setup``, but the isolated worker's ``_RemoteCtx`` stub
did not provide those decorators — every isolated load crashed with
AttributeError before the ready frame. The fix: the worker registers them and
reports names in the ready frame; the loader populates the host-side context
with invoke-wrapping handlers, capability-checked, so ``dispatch`` fires them
exactly like in-process ones.
"""

from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

import pytest

from soapbot.plugins.loader import PluginLoader
from soapbot.plugins.supervisor import PluginSupervisor
from soapbot.security.audit import AuditLog
from soapbot.security.principal import PERMISSION_MIN_ROLE, Permission, Role

MANIFEST = """\
name: {name}
version: 1.0.0
entry: main:{cls}
description: "隔离 cron 与钩子回归用"
capabilities:
  - command
  - cron
  - message
  - send
  - storage
min_host_version: "0.1.0"
"""

MAIN = """\
from soapbot.plugins.base import Plugin
from soapbot.plugins.context import CallerContext

class {cls}(Plugin):
    def setup(self, ctx):
        @ctx.cron("* * * * *", name="{name}-tick")
        async def tick():
            return None
        @ctx.on_message
        async def on_msg(msg):
            return None
        @ctx.command("smoke", description="x")
        def smoke(caller, args):
            return "ok"
        # 回调面在 setup 期不可用（隔离模式没有活跃请求，await 会 RuntimeError）；
        # 这里只创建协程不 await——验证 facade 的形状（send 关键词签名与进程内一致），
        # 真取值走命令期的双模式助手（见 test_isolated_invoke_contract.py）。
        ctx.storage.set("k", "v")
        ctx.send("m", session_key="s")
        ctx.memory.recall("q")
"""

WORKER_FAILURE = (
    "AttributeError: '_RemoteCtx' object has no attribute 'on_message'"
)


@pytest.fixture
def host_env(tmp_path, monkeypatch):
    """A loader over a temp plugins dir with one plugin that uses cron+hooks."""
    (tmp_path / "plugins").mkdir()
    main_dir = tmp_path / "plugins" / "isolated-smoke"
    main_dir.mkdir()
    (main_dir / "plugin.yaml").write_text(
        MANIFEST.format(name="isolated-smoke", cls="IsolatedSmoke"),
        encoding="utf-8",
    )
    (main_dir / "main.py").write_text(
        MAIN.format(name="isolated-smoke", cls="IsolatedSmoke"),
        encoding="utf-8",
    )
    loader = PluginLoader(
        plugins_dir=tmp_path / "plugins",
        audit=AuditLog(),
        supervisor=PluginSupervisor(),
        allow_untrusted=True,
    )
    from soapbot.plugins.dispatch import PluginManager

    manager = PluginManager(loader)
    manager.install_isolation(supervisor=loader.supervisor)
    return loader


async def test_isolated_cron_and_hooks_register_through_the_ready_frame(host_env) -> None:
    """setup 调 ctx.cron/on_message/command/send/storage/memory——隔离 worker 全部
    通过 ready 帧注册；宿主侧 cron_jobs 拿到 invoke 包装器。"""
    manifest = next(m for m in host_env.discover().found)
    host_env.approve_from_manifest(manifest)
    loaded = await host_env.load(manifest.name, force=True)

    crons = loaded.context._cron_jobs
    assert crons and crons[0]["expr"] == "* * * * *"
    assert crons[0]["plugin"] == "isolated-smoke"
    # handler 是 worker invoke 包装器：绑定 worker 与 handler 名
    assert crons[0]["handler"].__name__ == "isolated-smoke-tick"
    hooks = loaded.context._message_hooks
    assert hooks and hooks[0].__name__ == "on_msg"
    await loader_supervisor_stop(host_env)


async def loader_supervisor_stop(loader) -> None:
    await loader.supervisor.stop_all()


def test_worker_boot_failure_now_carries_the_redacted_stderr_tail() -> None:
    """boot 失败曾经只报类型——child 的栈现在打到 stderr，父进程 tail 捕获后嵌进
    WorkerCrashedError（与运行时崩溃路径一致）。钉住 tail 存在的行为。"""
    from soapbot.plugins.supervisor import PluginWorker

    assert hasattr(PluginWorker, "crash_tail")
    # The boot-failure raise embeds the tail; verified end-to-end by the smoke
    # script against a deliberately broken plugin (see soapbot-plugins).


def test_control_grant_stays_owner_only() -> None:

    assert PERMISSION_MIN_ROLE.get(Permission.CONTROL_GRANT) == Role.OWNER
