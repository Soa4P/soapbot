"""Isolated-worker invoke contract, driven end-to-end through a real worker.

``test_isolated_cron_hooks.py`` pins the *registration* half (ready frame names,
host-side invoke wrappers). This file pins the *invocation* half — what actually
happens when the host calls a handler through the pipe — because that half shipped
broken once and loading smoke can never catch it (setup() runs without any invoke):

* every handler kind resolves in the child (commands/tools in ``_commands``, cron
  ticks in ``_cron_fns``, hooks in ``_hook_fns`` — resolving commands only made
  hook and cron invokes fail with "no such handler");
* ``caller`` is rebuilt as an attribute-access object with ``session_key`` —
  the payload used to arrive as a bare dict without the session binding, so any
  ``caller.session_key`` raised AttributeError and no session-scoped command
  could work;
* a message hook's second parameter is the message *text* (str), matching the
  in-process dispatch contract — not a one-element list of dicts.
"""

from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

import pytest

from soapbot.plugins.loader import PluginLoader
from soapbot.plugins.supervisor import PluginSupervisor
from soapbot.security.audit import AuditLog

MANIFEST = """\
name: {name}
version: 1.0.0
entry: main:{cls}
description: "隔离 invoke 契约回归用"
capabilities:
  - command
  - cron
  - message
  - send
  - storage
min_host_version: "0.1.0"
"""

MAIN = '''\
from soapbot.plugins.base import Plugin
from soapbot.plugins.context import CallerContext

class {cls}(Plugin):
    def setup(self, ctx):
        @ctx.command("{cmd}", description="who", usage="/{cmd}")
        def who(caller, args):
            return {{"session": caller.session_key, "user": caller.user_id,
                     "name": caller.display_name, "privileged": caller.is_privileged,
                     "arg0": args[0] if args else ""}}
        @ctx.on_message
        async def on_msg(caller, text):
            return {{"text_type": type(text).__name__, "text": text,
                     "session": caller.session_key}}
        @ctx.cron("30 9 * * *", name="{cmd}-tick")
        async def tick(caller):
            return {{"tick": True, "session": caller.session_key}}
        @ctx.cron("30 9 * * *", name="{cmd}-display")
        async def differently_named(caller):
            return {{"alt": True}}
        @ctx.command("{cmd}-nostorage", description="s", usage="/x")
        async def nostorage(caller, args):
            value = ctx.storage.get("k")
            if hasattr(value, "__await__"):
                value = await value
            return {{"got": value}}
        @ctx.command("{cmd}-sendprobe", description="s", usage="/x")
        async def sendprobe(caller, args):
            try:
                await ctx.send("hi", session_key=caller.session_key)
                return "sent"
            except TypeError:
                return "TypeError"
            except PermissionError:
                return "PermissionError"
'''

CMD = "who-smoke"


@pytest.fixture
def host_env(tmp_path):
    (tmp_path / "plugins").mkdir()
    main_dir = tmp_path / "plugins" / "invoke-contract"
    main_dir.mkdir()
    (main_dir / "plugin.yaml").write_text(
        MANIFEST.format(name="invoke-contract", cls="InvokeContract"), encoding="utf-8",
    )
    (main_dir / "main.py").write_text(
        MAIN.format(cls="InvokeContract", cmd=CMD), encoding="utf-8",
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


def _caller(session_key: str = "qq:group:42"):
    from soapbot.plugins.context import CallerContext

    return CallerContext(
        user_id="u1", display_name="Invoker", role="member",
        session_key=session_key, scene="group", group_id="42",
    )


async def test_command_sees_rebuilt_caller_with_session_binding(host_env) -> None:
    """命令内 caller.session_key/user_id 可用（载荷重建为属性对象）。"""
    manifest = next(m for m in host_env.discover().found)
    host_env.approve_from_manifest(manifest)
    loaded = await host_env.load(manifest.name, force=True)
    try:
        out = await loaded.worker.invoke(CMD, caller=_caller(), args=["hi"])
        assert out["session"] == "qq:group:42"
        assert out["user"] == "u1"
        assert out["name"] == "Invoker"
        assert out["privileged"] is False
        assert out["arg0"] == "hi"
    finally:
        await host_env.supervisor.stop_all()


async def test_message_hook_receives_text_str_like_in_process(host_env) -> None:
    """钩子第二参是消息文本字符串——与进程内 dispatch 的 hook(caller, text) 契约一致。"""
    manifest = next(m for m in host_env.discover().found)
    host_env.approve_from_manifest(manifest)
    loaded = await host_env.load(manifest.name, force=True)
    try:
        # 与 loader._message_hook 相同的帧形状：args=[{"text", "session_key"}]
        out = await loaded.worker.invoke(
            "on_msg", caller=_caller(),
            args=[{"text": "hello", "session_key": "qq:group:42"}],
        )
        assert out["text_type"] == "str"
        assert out["text"] == "hello"
        assert out["session"] == "qq:group:42"
    finally:
        await host_env.supervisor.stop_all()


async def test_host_side_hook_wrapper_matches_dispatch_contract(host_env) -> None:
    """宿主侧 invoke 包装器按 dispatch 的 hook(caller, text) 形状被调用。

    包装器曾写成读 ``ctx_event.extras``——dispatch 以 (caller, text) 调它时
    TypeError，每条消息都炸（被 stage 的 except 吞成 warning）。"""
    manifest = next(m for m in host_env.discover().found)
    host_env.approve_from_manifest(manifest)
    loaded = await host_env.load(manifest.name, force=True)
    try:
        hooks = loaded.context._message_hooks
        assert hooks, "isolated plugin must register a host-side hook wrapper"
        out = await hooks[0](_caller(), "hello from stage")
        assert out["text_type"] == "str"
        assert out["text"] == "hello from stage"
        assert out["session"] == "qq:group:42"
    finally:
        await host_env.supervisor.stop_all()


async def test_cron_handler_resolves_and_runs(host_env) -> None:
    """cron handler（经 ctx.cron 注册、ready 帧只报名字）能被 invoke 解析并执行。

    宿主 tick wrapper 回调的是 ``entry["handler"]``（函数名），而 job 可以声明
    与函数名不同的 display ``name``——两个键都必须解析到同一个 handler。"""
    manifest = next(m for m in host_env.discover().found)
    host_env.approve_from_manifest(manifest)
    loaded = await host_env.load(manifest.name, force=True)
    try:
        out = await loaded.worker.invoke(
            "tick", caller=_caller(session_key=""), args=[],
        )
        assert out["tick"] is True
        # cron 调用者没有会话范围（宿主钉死）——空 session_key 原样可见，不是崩溃
        assert out["session"] == ""
        # display name 与函数名不同：display 名同样可解析（同一 handler）
        alt = await loaded.worker.invoke(
            f"{CMD}-display", caller=_caller(session_key=""), args=[],
        )
        assert alt == {"alt": True}
    finally:
        await host_env.supervisor.stop_all()


async def test_empty_caller_payload_is_safe(host_env) -> None:
    """空 caller 载荷（cron 场景）不炸：所有字段缺省为空串/False。"""
    manifest = next(m for m in host_env.discover().found)
    host_env.approve_from_manifest(manifest)
    loaded = await host_env.load(manifest.name, force=True)
    try:
        out = await loaded.worker.invoke(CMD, caller=None, args=[])
        assert out["session"] == ""
        assert out["user"] == ""
        assert out["privileged"] is False
    finally:
        await host_env.supervisor.stop_all()


async def test_async_storage_roundtrip_in_worker(host_env) -> None:
    """隔离 worker 的 storage 是 async——双模式助手（isawaitable 则 await）取值正常。"""
    manifest = next(m for m in host_env.discover().found)
    host_env.approve_from_manifest(manifest)
    loaded = await host_env.load(manifest.name, force=True)
    try:
        out = await loaded.worker.invoke(f"{CMD}-nostorage", caller=_caller(), args=[])
        assert out == {"got": None}  # 未写过 k：default None 原样返回
    finally:
        await host_env.supervisor.stop_all()


async def test_send_facade_matches_in_process_signature(host_env) -> None:
    """ctx.send(text, session_key=…) 关键词形状与进程内一致——签名错会 TypeError，
    签名对而 ledger 未观察到该会话则是 PermissionError（测试 ledger 为空，必拒）。"""
    manifest = next(m for m in host_env.discover().found)
    host_env.approve_from_manifest(manifest)
    loaded = await host_env.load(manifest.name, force=True)
    try:
        out = await loaded.worker.invoke(f"{CMD}-sendprobe", caller=_caller(), args=[])
        assert out == "PermissionError"
    finally:
        await host_env.supervisor.stop_all()
