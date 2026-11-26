"""The plugin task registry + surface + API: done_at made visible (ops-handoff 吸收 2).

The chain: 插件经 ``tasks.update`` surface 声明/标记完成 → 宿主持久化（原子 JSON）→
面板聚合并给「过了预期窗口仍无 done_at」的任务标「未确认完成」。Isolation: rows
are keyed by ``(plugin, task_id)`` from the host-bound plugin name — a plugin can
never touch another's rows.
"""

from __future__ import annotations

from pathlib import Path

import pytest

from soapbot.plugins.tasks import PluginTaskStore


# ------------------------------------------------------------------ the store
def test_update_is_isolated_per_plugin(tmp_path: Path) -> None:
    store = PluginTaskStore(tmp_path / "plugin-tasks.json")
    store.update(plugin="alpha", task_id="nightly", description="同步", done=True, now=100.0)
    store.update(plugin="beta", task_id="nightly", description="别的插件的同名任务", done=False, now=101.0)
    rows = store.all_tasks()
    assert rows["alpha"]["nightly"].done_at is not None
    assert rows["beta"]["nightly"].done_at is None  # 同名不串


def test_update_overdue_flag(tmp_path: Path) -> None:
    store = PluginTaskStore(tmp_path / "plugin-tasks.json")
    store.update(plugin="p", task_id="t1", expected_within_hours=24, done=False, now=100.0)
    assert store.all_tasks()["p"]["t1"].overdue(now=100.0 + 25 * 3600) is True
    store.update(plugin="p", task_id="t2", expected_within_hours=0, done=False, now=100.0)
    # 未声明 SLA 的任务诚实显示「运行中」，不标未确认。
    assert store.all_tasks()["p"]["t2"].overdue(now=100.0 + 999 * 3600) is False


def test_done_is_sticky_against_later_false_updates(tmp_path: Path) -> None:
    """done_at 一旦记录就是既成事实——后续 done=False 更新不能抹掉它。"""
    store = PluginTaskStore(tmp_path / "plugin-tasks.json")
    store.update(plugin="p", task_id="t", done=True, now=100.0)
    store.update(plugin="p", task_id="t", done=False, now=200.0)
    assert store.all_tasks()["p"]["t"].done_at is not None


def test_a_corrupt_registry_degrades_to_empty(tmp_path: Path) -> None:
    path = tmp_path / "plugin-tasks.json"
    path.write_bytes(b"\xff\xfe not json")
    store = PluginTaskStore(path)
    assert store.all_tasks() == {}
    store.update(plugin="p", task_id="t", done=True, now=1.0)  # 从空开始照常工作


def test_the_registry_survives_a_restart(tmp_path: Path) -> None:
    path = tmp_path / "plugin-tasks.json"
    first = PluginTaskStore(path)
    first.update(plugin="p", task_id="t", done=True, now=100.0)
    second = PluginTaskStore(path)
    rows = second.all_tasks()
    assert rows["p"]["t"].done_at is not None  # 新实例从盘上读回


# ------------------------------------------------------------------ the surface
@pytest.fixture
def surfaces_env(tmp_path, monkeypatch):
    from types import SimpleNamespace

    from soapbot.plugins.context import CallerContext, PluginContext, bind_caller
    from soapbot.plugins.manifest import Capability
    from soapbot.plugins.sandbox import CapabilityGrant, CapabilityGuard

    database_dir = tmp_path / "data"
    database_dir.mkdir()
    from soapbot.config import settings

    monkeypatch.setattr(settings, "data_dir", database_dir)
    from soapbot.plugins.tasks import PluginTaskStore

    manager = SimpleNamespace(tasks=PluginTaskStore(database_dir / "plugin-tasks.json"))
    monkeypatch.setattr("soapbot.app.get_plugin_manager", lambda: manager)

    guard = CapabilityGuard(
        CapabilityGrant(
            plugin="p",
            # ``tasks`` gates the surface (audit S-PLUG-08); ``command`` alone is no
            # longer enough to write host state.
            declared=frozenset({Capability.COMMAND, Capability.TASKS}),
            approved=frozenset({Capability.COMMAND, Capability.TASKS}),
        )
    )
    ctx = PluginContext(plugin="p", guard=guard)
    caller = CallerContext(
        user_id="u", display_name="u", role="member", session_key="onebot11:group:1", scene="group"
    )
    import contextlib

    token = contextlib.contextmanager(lambda: (yield caller))()
    return SimpleNamespace(ctx=ctx, bind=lambda: bind_caller(caller), manager=manager, token=token)


async def test_surface_writes_through_the_host_registry(surfaces_env) -> None:
    with surfaces_env.bind():
        result = await surfaces_env.ctx.task_update(
            "nightly-sync", description="每夜同步", expected_within_hours=24, done=True
        )
    assert result["done"] is True
    assert not result["overdue"]
    rows = surfaces_env.manager.tasks.all_tasks()
    assert rows["p"]["nightly-sync"].description == "每夜同步"


async def test_surface_overdue_reflects_the_expected_window(surfaces_env) -> None:
    with surfaces_env.bind():
        await surfaces_env.ctx.task_update("slow-job", expected_within_hours=1)
        # 标记后立刻再看：SLA 未过 → running；把 expected 拉到 0 再更新则仍是 running
        # 的镜像断言在 store 层已钉，这里只钉 surface 的返回形状。
        result = await surfaces_env.ctx.task_update("slow-job", done=False)
    assert result["task_id"] == "slow-job"
    assert result["done"] is False


# ------------------------------------------------ bounds on host state (S-PLUG-08)
async def test_tasks_update_requires_the_tasks_capability(tmp_path, monkeypatch) -> None:
    """Every other surface is gated by a capability; this one used to be open.

    A plugin that declared nothing could write into the operator-visible registry —
    the one place where "what did the plugin promise to finish" is recorded.
    """
    from types import SimpleNamespace

    from soapbot.config import settings
    from soapbot.plugins.context import CallerContext, PluginContext, bind_caller
    from soapbot.plugins.manifest import Capability
    from soapbot.plugins.sandbox import (
        CapabilityDeniedError,
        CapabilityGrant,
        CapabilityGuard,
    )
    from soapbot.plugins.tasks import PluginTaskStore

    data_dir = tmp_path / "data2"
    data_dir.mkdir()
    monkeypatch.setattr(settings, "data_dir", data_dir)
    manager = SimpleNamespace(tasks=PluginTaskStore(data_dir / "plugin-tasks.json"))
    monkeypatch.setattr("soapbot.app.get_plugin_manager", lambda: manager)

    guard = CapabilityGuard(
        CapabilityGrant(
            plugin="p",
            declared=frozenset({Capability.COMMAND}),
            approved=frozenset({Capability.COMMAND}),
        )
    )
    ctx = PluginContext(plugin="p", guard=guard)
    caller = CallerContext(
        user_id="u", display_name="u", role="member", session_key="onebot11:group:1", scene="group"
    )
    with bind_caller(caller), pytest.raises(CapabilityDeniedError):
        await ctx.task_update("sneaky")
    assert manager.tasks.all_tasks() == {}


async def test_tasks_update_is_rate_limited_per_plugin(surfaces_env) -> None:
    """Each write is an fsync + atomic replace; a loop of them is disk and loop stall."""
    from soapbot.plugins import surfaces
    from soapbot.plugins.manifest import Capability
    from soapbot.plugins.sandbox import CapabilityDeniedError

    surfaces._TASK_WRITES.reset("p")
    budget = surfaces._TASK_WRITES.limit
    with surfaces_env.bind():
        for index in range(budget):
            await surfaces_env.ctx.task_update(f"t{index}")
        with pytest.raises(CapabilityDeniedError, match="limited to"):
            await surfaces_env.ctx.task_update("one-too-many")
    surfaces._TASK_WRITES.reset("p")
    assert Capability.TASKS.value == "tasks"


async def test_a_plugin_cannot_grow_the_registry_without_limit(surfaces_env) -> None:
    """Well-paced but endless: the row cap is the second bound."""
    from soapbot.plugins import surfaces
    from soapbot.plugins.sandbox import CapabilityDeniedError

    surfaces._TASK_WRITES.reset("p")
    with surfaces_env.bind():
        # Fill the store directly: the point here is the cap, not the rate window.
        for index in range(surfaces.MAX_TASKS_PER_PLUGIN):
            surfaces_env.manager.tasks.update(
                plugin="p", task_id=f"t{index}", description="", done=False
            )
        with pytest.raises(CapabilityDeniedError, match="max"):
            await surfaces_env.ctx.task_update("the-last-one")
        # Re-declaring an existing row is still allowed — that is the normal use.
        result = await surfaces_env.ctx.task_update("t0", done=True)
    assert result["done"] is True
    surfaces._TASK_WRITES.reset("p")
