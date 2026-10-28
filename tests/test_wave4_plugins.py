"""Wave 4 acceptance: plugins work end-to-end through the real pipeline.

Gate A5 from the plan:

    A sample plugin adds a command and a tool using only the public ``ctx`` API,
    hot reload takes effect, and disabling unloads it completely.

These tests drive the real ``BotRuntime`` with the mock OneBot server, so they
also prove the plugin path inherits the security stages (guard, allow-list,
injection screen, authorization) rather than bypassing them.
"""

from __future__ import annotations

import asyncio
import shutil
from pathlib import Path

import pytest

from soapbot.adapters.mock_onebot import MockOneBot11Server
from soapbot.adapters.onebot11 import OneBot11Adapter
from soapbot.ai.persona import Persona, PersonaStore
from soapbot.core.builder import build_runtime
from soapbot.examples import bundled_plugins_dir
from soapbot.memory.db import Database, reset_database
from soapbot.memory.extractor import MemoryExtractor
from soapbot.memory.store import MemoryStore
from soapbot.security.principal import AuthorityConfig

#: The example plugins ship inside the package, not in ``data/``.
#: ``data/`` is gitignored, so pointing here made the whole suite depend on files
#: that a fresh clone does not have: five modules failed with FileNotFoundError in
#: CI while passing on the author's machine.
PLUGIN_SRC = bundled_plugins_dir()


@pytest.fixture
async def db(tmp_path):
    await reset_database()
    database = Database(f"sqlite+aiosqlite:///{(tmp_path / 'p.db').as_posix()}")
    await database.init()
    yield database
    await database.close()
    await reset_database()


@pytest.fixture
def plugins_dir(tmp_path) -> Path:
    """A private copy of the sample plugins, so tests never mutate the repo."""
    target = tmp_path / "plugins"
    shutil.copytree(PLUGIN_SRC, target)
    return target


def personas() -> PersonaStore:
    store = PersonaStore()
    store.add(
        Persona(
            id="t",
            name="t",
            system_prompt="你是测试助手。",
            max_reply_chars=400,
            wake_words=["soapbot"],
        )
    )
    store.set_default("t")
    return store


async def spin_up(
    provider_router, *, memory=None, plugins_dir=None, authority=None, access=None
):
    """Boot a real bot with plugins installed through the production wiring."""
    server = MockOneBot11Server()
    await server.start()

    runtime = build_runtime(
        router=provider_router,
        personas=personas(),
        memory=memory,
        access=access,
        authority=authority,
        extractor=MemoryExtractor(),
        plugins_dir=plugins_dir,
    )

    manager = runtime.plugins
    if manager is not None:
        for manifest in manager.loader.discover().found:
            manager.loader.approve_from_manifest(manifest)
            await manager.load(manifest.name)

    adapter = OneBot11Adapter(account_id="10000", mode="forward", ws_url=server.url)
    await runtime.add_adapter(adapter)
    await runtime.start()
    await server.wait_connected()
    return server, runtime, manager


async def send_cmd(server, text: str, user_id: str = "20001") -> None:
    await server.push_group_message(
        segments=[
            {"type": "at", "data": {"qq": "10000"}},
            {"type": "text", "data": {"text": f" {text}"}},
        ],
        user_id=user_id,
    )


async def wait_send(server, rounds: int = 200) -> None:
    for _ in range(rounds):
        if server.sent_messages():
            return
        await asyncio.sleep(0.02)


# --------------------------------------------------------------- command works


async def test_plugin_command_works_end_to_end(
    mock_llm_router, provider_router, mock_llm, db, plugins_dir
) -> None:
    """A5: the echo plugin adds /echo using only the public API."""
    memory = MemoryStore(db, embedder=None)
    server, runtime, manager = await spin_up(
        provider_router, memory=memory, plugins_dir=plugins_dir
    )
    mock_llm.reset()
    try:
        await send_cmd(server, "/echo 你好世界")
        await wait_send(server)

        assert server.last_sent_text().strip() == "你好世界"
        # Commands must not spend a model call.
        assert mock_llm.calls == []
        assert manager is not None
    finally:
        await runtime.stop()
        await server.stop()


async def test_plugin_admin_command_denied_for_member(
    mock_llm_router, provider_router, mock_llm, db, plugins_dir
) -> None:
    """A plugin command declaring min_role=ADMIN is refused for a member.

    This is the escalation case: the *plugin* says "admins only", but the host is
    the one that decides. If the host trusted the plugin's claim and the plugin
    were hostile, the claim would be ``min_role=MEMBER`` and the gate would vanish.
    """
    memory = MemoryStore(db, embedder=None)
    server, runtime, manager = await spin_up(provider_router, memory=memory, plugins_dir=plugins_dir)
    mock_llm.reset()
    try:
        await send_cmd(server, "/purge-demo")
        await wait_send(server)

        text = server.last_sent_text()
        assert "管理员命令已执行" not in text
        assert "权限" in text
        assert mock_llm.calls == []
    finally:
        await runtime.stop()
        await server.stop()


async def test_plugin_admin_command_allowed_for_admin(
    mock_llm_router, provider_router, mock_llm, db, plugins_dir
) -> None:
    """Control: the same command succeeds for a configured admin."""
    memory = MemoryStore(db, embedder=None)
    server, runtime, manager = await spin_up(
        provider_router,
        memory=memory,
        plugins_dir=plugins_dir,
        authority=AuthorityConfig(admins={"20001"}),
    )
    try:
        await send_cmd(server, "/purge-demo")
        await wait_send(server)
        assert "管理员命令已执行" in server.last_sent_text()
    finally:
        await runtime.stop()
        await server.stop()


# --------------------------------------------------------------- hot reload


async def test_hot_reload_picks_up_new_command(
    mock_llm_router, provider_router, mock_llm, db, plugins_dir
) -> None:
    """A5: editing a plugin file and reloading makes the new command available."""
    memory = MemoryStore(db, embedder=None)
    server, runtime, manager = await spin_up(provider_router, memory=memory, plugins_dir=plugins_dir)
    try:
        assert manager is not None
        assert "hello" not in manager.loader.all_commands()

        plugin_main = plugins_dir / "echo" / "main.py"
        source = plugin_main.read_text(encoding="utf-8")
        # Anchor on the tool decorator, which appears exactly once and is at the
        # same indentation as the command decorators.
        marker = "        @ctx.tool("
        assert marker in source, "test anchor missing; update the sample plugin"
        new_command = (
            '        @ctx.command("hello")\n'
            "        async def hello(caller, args):\n"
            '            return "hi"\n\n'
        )
        plugin_main.write_text(
            source.replace(marker, new_command + marker, 1), encoding="utf-8"
        )

        await manager.reload("echo")
        assert "hello" in manager.loader.all_commands()

        await send_cmd(server, "/hello")
        await wait_send(server)
        assert server.last_sent_text().strip() == "hi"
    finally:
        await runtime.stop()
        await server.stop()


async def test_unload_removes_commands_completely(
    mock_llm_router, provider_router, mock_llm, db, plugins_dir
) -> None:
    """A5: after disabling, the command no longer exists and modules are purged."""
    import sys

    memory = MemoryStore(db, embedder=None)
    server, runtime, manager = await spin_up(provider_router, memory=memory, plugins_dir=plugins_dir)
    try:
        assert manager is not None
        assert "echo" in manager.loader.all_commands()

        await manager.unload("echo")
        assert "echo" not in manager.loader.all_commands()
        assert "echo" not in manager.loader.loaded
        assert not [n for n in sys.modules if n.startswith("soapbot_plugins.echo")]

        # The command now falls through to the model rather than being handled.
        mock_llm.reset()
        mock_llm.push("普通回复")
        await send_cmd(server, "/echo 任意内容")
        await asyncio.sleep(0.35)
        assert server.last_sent_text().strip() != "任意内容"
    finally:
        await runtime.stop()
        await server.stop()


async def test_failed_reload_leaves_plugin_unloaded(
    mock_llm_router, provider_router, mock_llm, db, plugins_dir
) -> None:
    """A broken update must not leave the old code silently running.

    Rationale: if reload failed but the previous version stayed active, the
    operator would see "updated" in the UI while the old behaviour persisted —
    including any vulnerability they were trying to patch.
    """
    from soapbot.plugins.loader import PluginLoadError

    memory = MemoryStore(db, embedder=None)
    server, runtime, manager = await spin_up(provider_router, memory=memory, plugins_dir=plugins_dir)
    try:
        assert manager is not None
        (plugins_dir / "echo" / "main.py").write_text(
            "raise RuntimeError('boom at import time')\n", encoding="utf-8"
        )
        with pytest.raises(PluginLoadError):
            await manager.reload("echo")

        assert "echo" not in manager.loader.loaded
        assert "echo" not in manager.loader.all_commands()
    finally:
        await runtime.stop()
        await server.stop()


# ------------------------------------------------------- security inheritance


async def test_plugin_command_respects_group_allowlist(
    mock_llm_router, provider_router, mock_llm, db, plugins_dir
) -> None:
    """A plugin command must not be reachable from a blocked group."""
    from soapbot.core.stages import AccessPolicy

    memory = MemoryStore(db, embedder=None)
    server, runtime, manager = await spin_up(
        provider_router,
        memory=memory,
        plugins_dir=plugins_dir,
        access=AccessPolicy(group_allowlist={"123456"}),
    )
    mock_llm.reset()

    try:
        await server.push_group_message(
            segments=[
                {"type": "at", "data": {"qq": "10000"}},
                {"type": "text", "data": {"text": " /echo 泄露测试"}},
            ],
            group_id="999999",
        )
        await asyncio.sleep(0.35)

        assert server.sent_messages() == [], "plugin command ran in a blocked group"
        assert mock_llm.calls == []
    finally:
        await runtime.stop()
        await server.stop()


async def test_plugin_does_not_bypass_core_command(
    mock_llm_router, provider_router, mock_llm, db, plugins_dir
) -> None:
    """Plugins cannot override a core command name (e.g. /forget).

    A silent override of ``/forget`` would be a security regression dressed as a
    feature, so the name is reserved at registration time.
    """
    from soapbot.plugins.sandbox import validate_command_name

    for core in ("forget", "kb", "recall", "timeline", "help", "ping"):
        with pytest.raises(ValueError):
            validate_command_name(core)
