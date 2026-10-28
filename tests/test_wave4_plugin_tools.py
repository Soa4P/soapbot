"""Plugin tools: model-driven invocation, host-side authorization, output hygiene.

Tools are the highest-risk plugin surface because the *model* decides when to call
them, and the model's decision is driven by text an attacker writes. A tool that
trusts the model to gate itself is one prompt injection away from being a public
API. These tests verify the host gates it instead.
"""

from __future__ import annotations

import shutil
from pathlib import Path

import pytest

from soapbot.examples import bundled_plugins_dir
from soapbot.plugins.dispatch import PluginToolRegistry
from soapbot.plugins.loader import PluginLoader
from soapbot.security.audit import AuditLog
from soapbot.security.principal import Principal, Role

#: Bundled examples, not ``data/plugins`` — see ``soapbot.examples``.
PLUGIN_SRC = bundled_plugins_dir()


@pytest.fixture
def loader(tmp_path: Path) -> PluginLoader:
    plugins_dir = tmp_path / "plugins"
    shutil.copytree(PLUGIN_SRC, plugins_dir)
    loader = PluginLoader(plugins_dir=plugins_dir, audit=AuditLog())
    for manifest in loader.discover().found:
        loader.approve_from_manifest(manifest)
    return loader


def principal(role: Role = Role.MEMBER, user_id: str = "20001") -> Principal:
    return Principal(user_id=user_id, role=role, authenticated=True)


async def test_tool_is_hidden_from_unauthorised_caller(loader: PluginLoader) -> None:
    """Tools the caller cannot use are not even listed.

    Listing-then-refusing still confirms the tool exists and invites the model to
    keep trying, which burns tokens and produces confusing replies.
    """
    await loader.load("echo")
    try:
        registry = PluginToolRegistry(loader)
        visible = registry.available_for(principal(Role.MEMBER))
        assert any(t["name"] == "echo_text" for t in visible)

        hidden = registry.available_for(principal(Role.ANONYMOUS))
        assert all(t["name"] != "echo_text" for t in hidden)
    finally:
        await loader.unload("echo")


async def test_tool_invocation_requires_permission(loader: PluginLoader) -> None:
    """An unauthenticated caller cannot invoke a tool even if the model asks."""
    await loader.load("echo")
    try:
        registry = PluginToolRegistry(loader)
        anon = Principal(user_id="", role=Role.MEMBER, authenticated=False)
        result = await registry.invoke(
            "echo_text", {"text": "hi"}, principal=anon, session_key="onebot11:group:1"
        )
        assert "权限" in result
    finally:
        await loader.unload("echo")


async def test_tool_executes_for_authorised_caller(loader: PluginLoader) -> None:
    await loader.load("echo")
    try:
        registry = PluginToolRegistry(loader)
        result = await registry.invoke(
            "echo_text",
            {"text": "测试内容"},
            principal=principal(),
            session_key="onebot11:group:123456",
        )
        assert result == "测试内容"
    finally:
        await loader.unload("echo")


async def test_unknown_tool_returns_error_not_exception(loader: PluginLoader) -> None:
    """The model can hallucinate tool names; that must not crash the turn."""
    await loader.load("echo")
    try:
        registry = PluginToolRegistry(loader)
        result = await registry.invoke(
            "does_not_exist", {}, principal=principal(), session_key="onebot11:group:1"
        )
        assert "没有这个工具" in result
    finally:
        await loader.unload("echo")


async def test_tool_result_is_scrubbed(loader: PluginLoader) -> None:
    """A tool echoing its own config must not publish the credential.

    The result goes into the model's context and may be rendered in a reply, so the
    host scrubs it regardless of what the plugin returned.
    """
    plugin_dir = loader.plugins_dir / "leaky_tool"
    plugin_dir.mkdir(parents=True)
    (plugin_dir / "plugin.yaml").write_text(
        "name: leaky_tool\nversion: '1.0.0'\nentry: main:P\ntrust: trusted\n"
        "capabilities:\n  - tool\n",
        encoding="utf-8",
    )
    (plugin_dir / "main.py").write_text(
        "from soapbot.plugins.base import Plugin\n"
        "class P(Plugin):\n"
        "    async def setup(self, ctx):\n"
        "        @ctx.tool('leak', description='leaks')\n"
        "        async def leak(caller, args):\n"
        "            return 'my key is sk-abcdefghijklmnop'\n",
        encoding="utf-8",
    )
    loader.approve_from_manifest(
        next(m for m in loader.discover().found if m.name == "leaky_tool")
    )
    await loader.load("leaky_tool")
    try:
        registry = PluginToolRegistry(loader)
        result = await registry.invoke(
            "leak", {}, principal=principal(), session_key="onebot11:group:1"
        )
        assert "sk-abcdefghijklmnop" not in result
        assert "REDACTED" in result
    finally:
        await loader.unload("leaky_tool")


async def test_tool_that_raises_does_not_leak_exception_text(loader: PluginLoader) -> None:
    """A traceback in a chat reply is an information disclosure."""
    plugin_dir = loader.plugins_dir / "broken_tool"
    plugin_dir.mkdir(parents=True)
    (plugin_dir / "plugin.yaml").write_text(
        "name: broken_tool\nversion: '1.0.0'\nentry: main:P\ntrust: trusted\n"
        "capabilities:\n  - tool\n",
        encoding="utf-8",
    )
    (plugin_dir / "main.py").write_text(
        "from soapbot.plugins.base import Plugin\n"
        "class P(Plugin):\n"
        "    async def setup(self, ctx):\n"
        "        @ctx.tool('boom', description='boom')\n"
        "        async def boom(caller, args):\n"
        "            raise RuntimeError('db password is hunter2')\n",
        encoding="utf-8",
    )
    loader.approve_from_manifest(
        next(m for m in loader.discover().found if m.name == "broken_tool")
    )
    await loader.load("broken_tool")
    try:
        registry = PluginToolRegistry(loader)
        result = await registry.invoke(
            "boom", {}, principal=principal(), session_key="onebot11:group:1"
        )
        assert "hunter2" not in result
        assert "RuntimeError" not in result
        assert "失败" in result
    finally:
        await loader.unload("broken_tool")


async def test_tool_denial_is_audited(loader: PluginLoader) -> None:
    audit = AuditLog()
    loader.audit = audit
    await loader.load("echo")
    try:
        registry = PluginToolRegistry(loader, audit=audit)
        anon = Principal(user_id="", role=Role.MEMBER, authenticated=False)
        await registry.invoke(
            "echo_text", {"text": "x"}, principal=anon, session_key="onebot11:group:1"
        )
        assert any(
            e["action"] == "tool:echo_text" and e["outcome"] == "deny"
            for e in audit.recent()
        )
    finally:
        await loader.unload("echo")
