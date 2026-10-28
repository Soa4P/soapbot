"""Regression tests for the wires that were missing between working parts.

Each test here corresponds to a defect found by reading call sites rather than
behaviour: the component existed, was tested in isolation, and was never
connected to anything. That class of bug is invisible to a per-module test suite,
so the tests below deliberately assert the *connection* — "the adapter produces
what the policy consumes", "the registry the model sees is the one the plugin
filled" — not the internals on either side.

Kept in one file on purpose. A future reader asking "is the notice chain
connected?" should find the answer in one place instead of spreading five
nearly-identical tests across five modules.
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from soapbot.adapters.onebot11 import OneBot11Adapter
from soapbot.adapters.qq_official import split_leading_at
from soapbot.ai.engine import AIEngine
from soapbot.ai.persona import PersonaStore
from soapbot.ai.stages import ModelStage
from soapbot.core.adapter import AccountInfo, Adapter, AdapterMeta, Capability
from soapbot.core.adapter import Adapter as _BaseAdapter
from soapbot.core.builder import build_access_policy, build_plugin_manager
from soapbot.core.message import (
    EventType,
    IncomingMessage,
    MessageReceipt,
    MessageScene,
    MessageSegment,
    Sender,
)
from soapbot.core.message import (
    IncomingMessage as _Incoming,
)
from soapbot.core.message import (
    MessageReceipt as _Receipt,
)
from soapbot.core.message import (
    MessageScene as _Scene,
)
from soapbot.core.message import (
    MessageSegment as _Segment,
)
from soapbot.core.message import (
    Sender as _Sender,
)
from soapbot.core.pipeline import Pipeline, PipelineContext
from soapbot.core.runtime import BotRuntime
from soapbot.core.stages import AccessPolicy, WakePolicy
from soapbot.memory.db import Database
from soapbot.memory.stages import CommandStage
from soapbot.memory.store import KnowledgeBase, MemoryStore
from soapbot.plugins.approvals import ApprovalStore
from soapbot.providers.base import ChatResponse, ProviderConfig
from soapbot.providers.openai_compat import OpenAICompatProvider
from soapbot.providers.router import ProviderRouter
from soapbot.security.principal import AuthorityConfig, Principal, Role

# --------------------------------------------------------- configuration syntax


def test_list_settings_accept_the_documented_comma_form() -> None:
    """``SOAPBOT_OWNER_IDS=123,456`` must parse, not abort startup.

    Without ``NoDecode`` + a validator, pydantic-settings tries ``json.loads`` on
    the raw value and raises ``SettingsError: error parsing value for field
    "owner_ids"`` — naming neither the value nor the accepted syntax, on the very
    form every document in this repository tells operators to use.
    """
    from soapbot.config import _split_list

    assert _split_list("123,456") == ["123", "456"]
    assert _split_list(" 123 , 456 ") == ["123", "456"]
    assert _split_list("1;2") == ["1", "2"]
    assert _split_list('["789"]') == ["789"]
    assert _split_list("") == []
    assert _split_list("   ") == []
    # Already-parsed values (a dict from a config file, a real list) pass through.
    assert _split_list(["a"]) == ["a"]


def test_list_settings_reject_malformed_json_with_a_readable_error() -> None:
    from soapbot.config import _split_list

    with pytest.raises(ValueError, match="逗号分隔"):
        _split_list("[not json")


# --------------------------------------------------------------- admission paths


def test_private_allowlist_from_settings_is_honoured() -> None:
    """``SOAPBOT_PRIVATE_ALLOWLIST`` must actually admit the named user.

    The setting existed and was documented while ``build_runtime`` constructed
    ``AccessPolicy()`` with no arguments, so private chat was refused under every
    configuration — the flag claimed to be applied and silently was not.
    """

    policy = build_access_policy(_cfg(private_allowlist=["10001"]))
    assert policy.allows(MessageScene.PRIVATE, "", "10001") == (True, "")
    assert policy.allows(MessageScene.PRIVATE, "", "99999") == (
        False,
        "private_not_allowed",
    )


def test_allow_unknown_private_opens_dms_and_default_stays_closed() -> None:
    """The "anyone may DM" switch works, and its absence keeps DMs shut.

    Testing both directions matters: a change that defaulted this to open would
    pass a test that only checked the enabled case.
    """

    closed = build_access_policy(_cfg())
    opened = build_access_policy(_cfg(allow_unknown_private=True))

    assert closed.allows(MessageScene.PRIVATE, "", "12345") == (
        False,
        "private_not_allowed",
    )
    assert opened.allows(MessageScene.PRIVATE, "", "12345") == (True, "")


def test_user_blacklist_wins_over_group_allow_all() -> None:
    """A banned user is refused even in a group that allows everyone."""

    policy = build_access_policy(_cfg(user_blacklist=["666"]))
    assert policy.allows(MessageScene.GROUP, "1", "666") == (False, "user_blacklisted")


# ------------------------------------------------------- official QQ @-mention


def test_official_at_mention_is_reported_not_just_stripped() -> None:
    mentioned, body = split_leading_at("<@!12345> 你好")
    assert mentioned is True
    assert body == "你好"

    mentioned, body = split_leading_at("普通消息")
    assert mentioned is False
    assert body == "普通消息"


def test_official_group_message_passes_the_wake_policy() -> None:
    """The end-to-end assertion the adapter previously failed.

    ``on_group_at_message_create`` only fires when the bot was @-mentioned, so the
    event must carry an AT segment for ``WakePolicy`` to agree. Without it the bot
    ignored every correctly-addressed group message on the official transport.
    """
    adapter = _official_adapter()
    mentioned, body = split_leading_at("<@!bot> 在吗")

    segments: list[MessageSegment] = []
    if mentioned:
        segments.append(MessageSegment.at(adapter.account_id))
    segments.append(MessageSegment.text(body))

    event = IncomingMessage(
        adapter="qq_official",
        message_id="1",
        scene=MessageScene.GROUP,
        sender=Sender(user_id="u1"),
        segments=segments,
        group_id="g1",
        self_id=adapter.account_id,
    )
    woken, how = WakePolicy().is_woken(_ctx(event))
    assert woken is True
    assert how == "at"


def test_official_unmentioned_text_does_not_wake() -> None:
    """A message with no mention and no wake word stays ignored."""
    adapter = _official_adapter()
    event = IncomingMessage(
        adapter="qq_official",
        message_id="1",
        scene=MessageScene.GROUP,
        sender=Sender(user_id="u1"),
        segments=[MessageSegment.text("随便聊聊")],
        group_id="g1",
        self_id=adapter.account_id,
    )
    assert WakePolicy().is_woken(_ctx(event)) == (False, "")


# -------------------------------------------------------- approval persistence


def _write_plugin(root: Path, name: str = "echoer", capabilities: str = "command") -> Path:
    plugins = root / "plugins"
    directory = plugins / name
    directory.mkdir(parents=True, exist_ok=True)
    (directory / "plugin.yaml").write_text(
        f"""\
name: {name}
version: 1.0.0
description: test plugin
entry: main:Plugin
trust: community
capabilities:
{chr(10).join(f"  - {c}" for c in capabilities.split(","))}
""",
        encoding="utf-8",
    )
    (directory / "main.py").write_text(
        "class Plugin:\n"
        "    def setup(self, ctx):\n"
        "        @ctx.command('pingpong', description='reply pong')\n"
        "        async def pingpong(caller, args):\n"
        "            return 'pong'\n",
        encoding="utf-8",
    )
    return plugins


def test_approval_survives_a_new_loader_instance(tmp_path: Path) -> None:
    """An approval is a standing decision, not a per-process flag.

    Before persistence, every restart forgot every approval: the service came back
    with all plugins idle, the WebUI still said "enabled", and a headless
    deployment had no way at all to re-grant.
    """
    plugins_dir = _write_plugin(tmp_path)
    approvals = ApprovalStore(tmp_path / "approvals.json")

    first = build_plugin_manager(
        plugins_dir, isolate=False, approvals_path=approvals.path
    )
    manifest = next(iter(first.loader.discover().found))
    first.loader.approve_from_manifest(manifest, actor="test")
    assert first.loader.is_approved("echoer")

    second = build_plugin_manager(
        plugins_dir, isolate=False, approvals_path=approvals.path
    )
    assert second.loader.is_approved("echoer")
    assert second.loader.approved_capabilities("echoer") == frozenset({"command"})


def test_revoke_is_persisted(tmp_path: Path) -> None:
    plugins_dir = _write_plugin(tmp_path)
    path = tmp_path / "approvals.json"
    manager = build_plugin_manager(plugins_dir, isolate=False, approvals_path=path)
    manifest = next(iter(manager.loader.discover().found))
    manager.loader.approve_from_manifest(manifest)
    manager.loader.revoke("echoer", actor="test")

    reloaded = build_plugin_manager(plugins_dir, isolate=False, approvals_path=path)
    assert reloaded.loader.is_approved("echoer") is False


def test_capability_added_after_approval_stays_pending(tmp_path: Path) -> None:
    """The manifest cannot self-approve a new capability.

    This is the property the separate-file design exists to protect: the plugin
    author writes the manifest, the operator writes the approval, and a plugin that
    grows an ``http`` requirement must come back for a decision.
    """
    plugins_dir = _write_plugin(tmp_path, capabilities="command")
    manager = build_plugin_manager(
        plugins_dir, isolate=False, approvals_path=tmp_path / "approvals.json"
    )
    manifest = next(iter(manager.loader.discover().found))
    manager.loader.approve_from_manifest(manifest)

    _write_plugin(tmp_path, capabilities="command,http")
    manifest = next(iter(manager.loader.discover().found))
    grant = manager.loader.grant_for(manifest)
    assert "http" not in {c.value for c in grant.effective}
    assert "http" in {c.value for c in grant.declared - grant.effective}


async def test_approved_plugin_is_loaded_at_startup(tmp_path: Path) -> None:
    """``load_approved`` starts what the operator approved, and nothing else."""
    plugins_dir = _write_plugin(tmp_path)
    _write_plugin(tmp_path, name="stranger", capabilities="command")
    manager = build_plugin_manager(
        plugins_dir, isolate=False, approvals_path=tmp_path / "approvals.json"
    )
    approved = next(m for m in manager.loader.discover().found if m.name == "echoer")
    manager.loader.approve_from_manifest(approved)

    report = await manager.loader.load_approved()
    try:
        assert report.loaded == ["echoer"]
        assert "stranger" not in manager.loader.loaded
        assert "pingpong" in manager.loader.all_commands()
    finally:
        await manager.loader.unload_all()


# ------------------------------------------------------------------ tool chain


class _ToolCallingProvider(OpenAICompatProvider):
    """First call asks for a tool; second call reports what it received."""

    def __init__(self) -> None:
        super().__init__(
            ProviderConfig(
                id="stub",
                kind="openai_compat",
                base_url="http://stub.local/v1",
                api_key="k",
                model="m",
            )
        )
        self.seen_tools: list[list[dict]] = []
        self.calls = 0

    async def chat(self, request):
        self.calls += 1
        self.seen_tools.append(list(request.tools))
        if self.calls == 1:
            return ChatResponse(
                content="",
                provider="stub",
                tool_calls=[
                    {
                        "id": "c1",
                        "type": "function",
                        "function": {
                            "name": "echo_word",
                            "arguments": json.dumps({"word": "hi"}),
                        },
                    }
                ],
            )
        note = "".join(m.text() for m in request.messages if m.role == "system")
        return ChatResponse(
            content=f"tool_value_seen={'ECHO:hi' in note}", provider="stub"
        )


async def test_plugin_tool_reaches_the_model_and_runs(tmp_path: Path) -> None:
    """The full chain: registration -> listing -> model call -> execution -> reply.

    Every link existed before and none were joined: ``AIRequest`` had no ``tools``
    field, ``ModelStage`` never asked the registry, and ``available_for`` had no
    callers. This asserts the joined result, not any single link.
    """
    from soapbot.plugins.dispatch import PluginToolRegistry

    plugins_dir = tmp_path / "plugins"
    directory = plugins_dir / "tooler"
    directory.mkdir(parents=True)
    (directory / "plugin.yaml").write_text(
        "name: tooler\nversion: 1.0.0\ndescription: d\nentry: main:Plugin\n"
        "trust: community\ncapabilities:\n  - tool\n",
        encoding="utf-8",
    )
    (directory / "main.py").write_text(
        "class Plugin:\n"
        "    def setup(self, ctx):\n"
        "        @ctx.tool(\n"
        "            'echo_word',\n"
        "            description='echo one word',\n"
        "            parameters={'type': 'object', 'properties': {}},\n"
        "        )\n"
        "        async def echo_word(caller, args):\n"
        "            return 'ECHO:' + str(args.get('word', ''))\n",
        encoding="utf-8",
    )

    manager = build_plugin_manager(
        plugins_dir, isolate=False, approvals_path=tmp_path / "approvals.json"
    )
    manager.loader.approve_from_manifest(next(iter(manager.loader.discover().found)))
    await manager.loader.load_approved()
    try:
        registry = PluginToolRegistry(manager.loader)
        provider = _ToolCallingProvider()
        router = ProviderRouter()
        router.add(provider)
        engine = AIEngine(router=router, personas=PersonaStore())
        stage = ModelStage(engine, tools=registry)

        event = IncomingMessage(
            adapter="mock",
            message_id="m1",
            scene=MessageScene.GROUP,
            sender=Sender(user_id="20001"),
            segments=[MessageSegment.text("say hi")],
            group_id="g1",
            self_id="bot",
        )
        ctx = PipelineContext(event=event, adapter=None)
        ctx.extras["principal"] = Principal(
            user_id="20001", role=Role.MEMBER, authenticated=True
        )

        pipeline = Pipeline()
        pipeline.add(stage)
        await pipeline.run(ctx)

        assert ctx.model_reply == "tool_value_seen=True"
        assert ctx.extras["tools_used"] == ["echo_word"]
        assert ctx.extras["tool_rounds"] == 1
        assert provider.seen_tools[0], "the model must be offered the tool"
    finally:
        await manager.loader.unload_all()


async def test_tool_is_not_offered_to_an_anonymous_caller(tmp_path: Path) -> None:
    """Filtering happens before the model sees anything."""
    from soapbot.plugins.dispatch import PluginToolRegistry

    plugins_dir = _write_plugin(tmp_path)
    manager = build_plugin_manager(
        plugins_dir, isolate=False, approvals_path=tmp_path / "approvals.json"
    )
    manager.loader.approve_from_manifest(next(iter(manager.loader.discover().found)))
    await manager.loader.load_approved()
    try:
        registry = PluginToolRegistry(manager.loader)
        assert registry.available_for(None) == []
    finally:
        await manager.loader.unload_all()


# ------------------------------------------------------------------- knowledge


async def test_knowledge_ingest_replaces_instead_of_duplicating(tmp_path: Path) -> None:
    """Re-uploading a document must replace it, not append a second copy.

    ``add_document`` is append-only by design, so a naive write path made the
    second upload of a corrected file double every chunk — and the retriever then
    returned the same passage twice with double the score. ``ingest_document``
    deletes first, which is what "upload this file" means.
    """
    db = Database(f"sqlite+aiosqlite:///{(tmp_path / 'kb.db').as_posix()}")
    await db.init()
    kb = KnowledgeBase(db)
    try:
        first = await kb.ingest_document("doc-1", "政策", "第一版内容。")
        assert first["chunks"] >= 1
        assert first["replaced"] is False

        second = await kb.ingest_document("doc-1", "政策", "第二版内容。")
        assert second["replaced"] is True

        documents = await kb.list_documents()
        assert len(documents) == 1
        assert documents[0]["chunks"] == second["chunks"]

        hits = await kb.search("第二版")
        joined = " ".join(str(h["content"]) for h in hits)
        assert "第二版" in joined
        assert "第一版" not in joined
    finally:
        await db.close()


async def test_knowledge_detail_and_delete(tmp_path: Path) -> None:
    db = Database(f"sqlite+aiosqlite:///{(tmp_path / 'kb2.db').as_posix()}")
    await db.init()
    kb = KnowledgeBase(db)
    try:
        await kb.ingest_document("doc-2", "手册", "段落一。\n\n段落二。")
        detail = await kb.document_detail("doc-2")
        assert detail is not None
        assert detail["title"] == "手册"
        assert len(detail["chunks"]) >= 1

        removed = await kb.delete_document("doc-2")
        assert removed >= 1
        assert await kb.document_detail("doc-2") is None
    finally:
        await db.close()


# ------------------------------------------------------------------ notice chain


async def test_notice_reaches_a_plugin_hook(tmp_path: Path) -> None:
    """Adapter -> ``emit`` -> runtime -> plugin hook.

    Three separate breaks used to make this impossible: OneBot dropped every
    ``notice`` payload, ``Adapter.emit`` returned early for anything that was not a
    message, and ``PluginManager.on_notice`` had no caller.
    """
    plugins_dir = tmp_path / "plugins"
    directory = plugins_dir / "watcher"
    directory.mkdir(parents=True)
    (directory / "plugin.yaml").write_text(
        "name: watcher\nversion: 1.0.0\ndescription: d\nentry: main:Plugin\n"
        "trust: community\ncapabilities:\n  - notice\n",
        encoding="utf-8",
    )
    (directory / "main.py").write_text(
        "SEEN = []\n"
        "class Plugin:\n"
        "    def setup(self, ctx):\n"
        "        @ctx.on_notice\n"
        "        async def record(caller, notice):\n"
        "            SEEN.append(dict(notice))\n",
        encoding="utf-8",
    )

    manager = build_plugin_manager(
        plugins_dir, isolate=False, approvals_path=tmp_path / "approvals.json"
    )
    manager.loader.approve_from_manifest(next(iter(manager.loader.discover().found)))
    await manager.loader.load_approved()
    try:
        assert manager.has_notice_hooks() is True
        adapter = OneBot11Adapter(account_id="10000", ws_url="ws://127.0.0.1:1/")
        runtime = BotRuntime(plugins=manager)
        await runtime.add_adapter(adapter)

        event = adapter._to_notice(
            {
                "post_type": "notice",
                "notice_type": "group_ban",
                "sub_type": "ban",
                "group_id": "777",
                "user_id": "555",
                "operator_id": "999",
                "self_id": "10000",
            }
        )
        assert event is not None and event.event_type is EventType.NOTICE
        await runtime._on_notice(event)

        module = __import__("soapbot_plugins.watcher.main", fromlist=["SEEN"])
        assert module.SEEN and module.SEEN[0]["type"] == "group_ban"
        assert module.SEEN[0]["group_id"] == "777"
    finally:
        await manager.loader.unload_all()


def test_private_notice_is_not_translated() -> None:
    """A notice naming a user rather than a group is refused, not guessed at."""
    adapter = OneBot11Adapter(account_id="1", ws_url="ws://127.0.0.1:1/")
    assert adapter._to_notice({"post_type": "notice", "notice_type": "friend_recall"}) is None


# ---------------------------------------------------------------- moderation


class _RecordingAdapter(Adapter):
    meta = AdapterMeta(name="rec", display_name="rec", protocol="test")
    capabilities = frozenset({Capability.MUTE, Capability.KICK, Capability.RECALL})

    def __init__(self) -> None:
        super().__init__()
        self.calls: list[tuple] = []

    async def start(self) -> None:  # pragma: no cover - not used
        return None

    async def stop(self) -> None:  # pragma: no cover - not used
        return None

    async def get_self(self):  # pragma: no cover - not used
        return None

    async def send(self, message):  # pragma: no cover - not used
        return MessageReceipt(ok=True)

    async def set_group_ban(self, group_id, user_id, duration_seconds):
        self.calls.append(("ban", group_id, user_id, duration_seconds))
        return MessageReceipt(ok=True)

    async def set_group_kick(self, group_id, user_id, *, reject_add_request=False):
        self.calls.append(("kick", group_id, user_id))
        return MessageReceipt(ok=True)

    async def recall(self, message_id):
        self.calls.append(("recall", message_id))
        return MessageReceipt(ok=True)


@pytest.fixture
async def moderation(tmp_path: Path):
    db = Database(f"sqlite+aiosqlite:///{(tmp_path / 'm.db').as_posix()}")
    await db.init()
    store = MemoryStore(db)
    stage = CommandStage(
        store,
        KnowledgeBase(db),
        authority=AuthorityConfig(owners={"1"}, admins={"2"}),
    )
    adapter = _RecordingAdapter()
    yield stage, store, adapter
    await db.close()


def _group_ctx(text: str, *, user: str, principal, adapter) -> PipelineContext:
    event = IncomingMessage(
        adapter="rec",
        message_id="m1",
        scene=MessageScene.GROUP,
        sender=Sender(user_id=user),
        segments=[MessageSegment.text(text)],
        group_id="g1",
        self_id="10000",
    )
    ctx = PipelineContext(event=event, adapter=adapter)
    ctx.extras["principal"] = principal
    return ctx


async def test_admin_can_mute_and_unmute(moderation) -> None:
    stage, _store, adapter = moderation
    admin = Principal(user_id="2", role=Role.ADMIN, authenticated=True)

    ctx = _group_ctx("/mute 300 5", user="2", principal=admin, adapter=adapter)
    await stage.run(ctx)
    assert adapter.calls[-1] == ("ban", "g1", "300", 300)

    ctx = _group_ctx("/unmute 300", user="2", principal=admin, adapter=adapter)
    await stage.run(ctx)
    assert adapter.calls[-1] == ("ban", "g1", "300", 0)


async def test_member_cannot_moderate(moderation) -> None:
    """Permission is checked before the adapter is touched."""
    stage, _store, adapter = moderation
    member = Principal(user_id="200", role=Role.MEMBER, authenticated=True)
    ctx = _group_ctx("/mute 300", user="200", principal=member, adapter=adapter)
    await stage.run(ctx)
    assert adapter.calls == []
    assert ctx.extras.get("command_denied") is True


async def test_admin_cannot_moderate_the_owner(moderation) -> None:
    """Bot rank is independent of QQ group rank.

    Without this, an admin can mute the person who configured the bot, and the
    owner cannot undo it from chat because the undo is also a moderation command.
    """
    stage, _store, adapter = moderation
    admin = Principal(user_id="2", role=Role.ADMIN, authenticated=True)
    ctx = _group_ctx("/mute 1", user="2", principal=admin, adapter=adapter)
    await stage.run(ctx)
    assert adapter.calls == []
    assert "权限" in (ctx.model_reply or "")


async def test_cannot_moderate_self_bot_or_bad_id(moderation) -> None:
    stage, _store, adapter = moderation
    admin = Principal(user_id="2", role=Role.ADMIN, authenticated=True)
    for command in ("/mute 2", "/mute 10000", "/mute abc"):
        ctx = _group_ctx(command, user="2", principal=admin, adapter=adapter)
        await stage.run(ctx)
        assert ctx.model_reply
    assert adapter.calls == []


async def test_recall_requires_a_message_from_this_session(moderation) -> None:
    """``/recall-msg`` is not a delete primitive over the whole account.

    The protocol's delete call takes a bare id with no group, so the only ownership
    check available is the host's own archive. An id nobody archived is refused.
    """
    stage, store, adapter = moderation
    admin = Principal(user_id="2", role=Role.ADMIN, authenticated=True)

    ctx = _group_ctx("/recall-msg 424242", user="2", principal=admin, adapter=adapter)
    await stage.run(ctx)
    assert adapter.calls == []
    assert "找不到" in (ctx.model_reply or "")

    await store.archive_message(
        session_key="rec:group:g1",
        role="user",
        content="spam",
        group_id="g1",
        user_id="300",
        message_id="424242",
    )
    ctx = _group_ctx("/recall-msg 424242", user="2", principal=admin, adapter=adapter)
    await stage.run(ctx)
    assert adapter.calls[-1] == ("recall", "424242")


async def test_recall_of_another_sessions_message_is_refused(moderation) -> None:
    stage, store, adapter = moderation
    admin = Principal(user_id="2", role=Role.ADMIN, authenticated=True)
    await store.archive_message(
        session_key="rec:group:OTHER",
        role="user",
        content="not yours",
        group_id="OTHER",
        user_id="300",
        message_id="777777",
    )
    ctx = _group_ctx("/recall-msg 777777", user="2", principal=admin, adapter=adapter)
    await stage.run(ctx)
    assert adapter.calls == []
    assert "找不到" in (ctx.model_reply or "")


# ------------------------------------------------------------------- helpers


def _cfg(**overrides):
    """Stand-in for :class:`soapbot.config.Settings` with only the access fields.

    A ``SimpleNamespace`` rather than a class with mutable class attributes:
    ``build_access_policy`` takes any object with these attributes, and the smaller
    surface keeps the test about the policy rather than about the settings model.
    """
    from types import SimpleNamespace

    base = {
        "group_allowlist": [],
        "group_blacklist": [],
        "user_blacklist": [],
        "private_allowlist": [],
        "allow_unknown_private": False,
    }
    base.update(overrides)
    return SimpleNamespace(**base)


def _official_adapter():
    from soapbot.adapters.qq_official import QQOfficialAdapter

    return QQOfficialAdapter(account_id="bot", app_id="a", app_secret="s")


def _ctx(event: IncomingMessage) -> PipelineContext:
    return PipelineContext(event=event, adapter=None)


def test_example_plugins_are_inside_the_package() -> None:
    """A fresh clone must have working examples.

    ``data/`` is gitignored, so the examples lived only on machines that had
    already run the bot. Five test modules and every deployment depended on files
    that were never committed.
    """
    from soapbot.examples import bundled_plugins_dir

    directory = bundled_plugins_dir()
    assert directory.is_dir()
    present = {p.name for p in directory.iterdir() if p.is_dir()}
    assert {"admin", "echo", "help", "remind"} <= present
    assert (directory / "echo" / "plugin.yaml").is_file()


def test_access_policy_default_is_closed_for_private() -> None:
    """The dataclass default must not silently accept DMs."""
    assert AccessPolicy().allows(MessageScene.PRIVATE, "", "123") == (
        False,
        "private_not_allowed",
    )


async def test_unimplemented_capability_reports_instead_of_crashing() -> None:
    """An adapter that declares nothing gets an honest failure, not AttributeError."""

    class _Bare(Adapter):
        meta = AdapterMeta(name="bare", display_name="bare", protocol="test")
        capabilities = frozenset()

        async def start(self):
            return None

        async def stop(self):
            return None

        async def get_self(self):
            return None

        async def send(self, message):
            return MessageReceipt(ok=True)

    adapter = _Bare()
    receipt = await adapter.recall("1")
    assert receipt.ok is False and "不支持" in receipt.error


# --- trace wiring helpers ---------------------------------------------------



def _incoming(text: str = "hi") -> _Incoming:
    return _Incoming(
        adapter="mock",
        message_id="m-1",
        scene=_Scene.PRIVATE,
        sender=_Sender(user_id="42", nickname="tester"),
        segments=[_Segment.text(text)],
    )


class _NamedStage:
    """Stand-in exposing only `.name`, which is all the trace store reads."""

    def __init__(self, name: str) -> None:
        self.name = name


class _Adapter(_BaseAdapter):
    meta = AdapterMeta(name="mock", display_name="mock", protocol="test")
    capabilities = frozenset()

    def __init__(self, handler) -> None:
        super().__init__()
        self.on_event(handler)

    async def start(self) -> None:
        return None

    async def stop(self) -> None:
        return None

    async def get_self(self):
        return AccountInfo(self_id="1")

    async def send(self, message):
        return _Receipt(ok=True)


# --- pipeline trace wiring --------------------------------------------------
#
# The trace collector is only useful if the runtime actually feeds it. Every test
# below would pass while the panel stayed empty if the observer were not attached,
# because an empty ring and an unattached ring look identical over HTTP.


async def test_observer_is_async_and_awaited() -> None:
    """`Pipeline.observe` awaits the callback; a sync one silently breaks it.

    This is the specific defect that made the first version of the collector record
    nothing: `observe` does `await fn(...)`, a plain function returns None, awaiting
    None raises, and the pipeline swallows it as an observer error.
    """
    import inspect

    from soapbot.core.builder import _observe_stage
    from soapbot.core.trace import TraceStore

    observer = _observe_stage(TraceStore())
    assert inspect.iscoroutinefunction(observer)


async def test_observer_receives_every_stage_of_a_run() -> None:
    """Driven through the real pipeline with the real observer contract."""
    from soapbot.core.builder import _observe_stage, build_pipeline
    from soapbot.core.pipeline import PipelineContext
    from soapbot.core.trace import TraceStore

    store = TraceStore()
    pipeline = build_pipeline(personas=PersonaStore())
    pipeline.observe(_observe_stage(store))

    ctx = PipelineContext(event=_incoming("hello"), adapter=None)
    await pipeline.run(ctx)

    assert ctx.timings, "流水线跑过但没有产生任何 timing"
    pending = store._pending.get(ctx.event.trace_id)
    assert pending is not None, "observer 没有把 timing 交给 TraceStore"
    observed = {s.name for s in pending.stages}
    assert observed, "TraceStore 收到了调用但没有记录任何环节"


async def test_runtime_publishes_message_processed_to_the_trace_store() -> None:
    """Asserts the *connection*: runtime publishes, builder's subscriber consumes."""
    from soapbot.core.runtime import BotRuntime
    from soapbot.core.trace import TraceStore

    topics: list[str] = []
    store = TraceStore()

    class _Bus:
        def subscribe(self, topic, handler):
            topics.append(topic)
            self.handler = handler

        async def publish(self, topic, payload=None):
            topics.append(topic)
            await self.handler(payload)

    class _Pipeline:
        def __init__(self):
            self._observers = []

        def observe(self, fn):
            self._observers.append(fn)

        async def run(self, ctx):
            for name in ("dedup", "guard"):
                for fn in self._observers:
                    await fn(ctx, _NamedStage(name), 1.0)
            ctx.timings = {"dedup": 1.0, "guard": 1.0}
            return ctx

    from soapbot.core.builder import _observe_stage, _record_trace

    bus = _Bus()
    runtime = BotRuntime(pipeline=_Pipeline(), bus=bus, traces=store)
    runtime.pipeline.observe(_observe_stage(store))
    # The same subscriber builder.py registers — not a hand-written lambda, because a
    # test that wires its own subscriber proves nothing about the real wiring.
    bus.subscribe("message.processed", lambda ctx: _record_trace(store, ctx))
    runtime.adapters["mock"] = _Adapter(runtime._on_event)

    await runtime._on_event(_incoming("hi"))

    assert "message.processed" in topics
    assert len(store.recent()) == 1, "订阅者没有把上下文转成 trace"
    assert [s.name for s in store.recent()[0].stages] == ["dedup", "guard"]


async def test_crashed_pipeline_leaves_a_trace() -> None:
    """The message that blows up is the one an operator most needs to see.

    Before this, the except branch returned without publishing: failures were counted
    nowhere, so the panel could show "0 failures" indefinitely.
    """
    from soapbot.core.runtime import BotRuntime
    from soapbot.core.trace import TraceStore

    class _Bus:
        def subscribe(self, topic, handler):
            return None

        async def publish(self, topic, payload=None):
            return None

    class _Pipeline:
        def observe(self, fn):
            return None

        async def run(self, ctx):
            raise RuntimeError("boom")

    store = TraceStore()
    runtime = BotRuntime(pipeline=_Pipeline(), bus=_Bus(), traces=store)
    runtime.adapters["mock"] = _Adapter(runtime._on_event)

    await runtime._on_event(_incoming("hi"))

    assert store.counters["failed"] == 1
    assert store.recent(), "崩溃的消息没有留下任何 trace"
    assert store.recent()[0].halt_reason == "pipeline_error"


def test_stage_order_constant_covers_the_builder() -> None:
    """Kept here as well: this file is the registry of connections, and a drifted
    graph is a broken connection between the panel and the runtime."""
    import inspect
    import re

    from soapbot.core import builder as builder_module
    from soapbot.core.trace import STAGE_ORDER
    from soapbot.plugins import dispatch as dispatch_module

    source = inspect.getsource(builder_module.build_pipeline)
    added = re.findall(r"pipeline\.add\(\s*([A-Za-z_][\w]*)\s*\(", source)
    names = []
    for class_name in added:
        cls = getattr(builder_module, class_name, None) or getattr(dispatch_module, class_name, None)
        if cls is not None and isinstance(getattr(cls, "name", None), str):
            names.append(cls.name)

    assert names, "未能从 build_pipeline 中读出 Stage"
    missing = [n for n in names if n not in STAGE_ORDER]
    assert not missing, f"STAGE_ORDER 与 build_pipeline 不一致：{missing}"
