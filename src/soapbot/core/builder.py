"""Assemble a complete bot runtime.

One place that knows how the pieces fit together, so both the FastAPI app and
the tests build the bot the same way. Adding a stage here is the only edit needed
to change pipeline behaviour globally.

Pipeline order (final, Wave 3):
    dedup -> whitelist -> wake -> strip_wake -> sanitize -> command
    -> persist -> persona -> recall -> knowledge -> model -> safety
    -> reply -> persist_reply -> memory_write
"""

from __future__ import annotations

import logging
from dataclasses import replace
from pathlib import Path

from soapbot.ai.compressor import CompressionConfig, ContextCompressor
from soapbot.ai.engine import AIEngine
from soapbot.ai.persona import PersonaStore
from soapbot.ai.stages import ModelStage, PersonaStage, SafetyStage
from soapbot.ai.vision import DescriptionCache
from soapbot.config import settings
from soapbot.core.bus import EventBus
from soapbot.core.pipeline import Pipeline
from soapbot.core.runtime import BotRuntime
from soapbot.core.stages import (
    AccessPolicy,
    DedupStage,
    ReplyStage,
    SanitizeStage,
    StripWakeWordStage,
    WakePolicy,
    WakeStage,
    WhitelistStage,
)
from soapbot.core.trace import TraceStore
from soapbot.memory.db import Database
from soapbot.memory.extractor import MemoryExtractor
from soapbot.memory.stages import (
    CommandStage,
    KnowledgeStage,
    MemoryWriteStage,
    PersistReplyStage,
    PersistStage,
    RecallStage,
)
from soapbot.memory.store import KnowledgeBase, MemoryStore
from soapbot.providers.router import ProviderRouter
from soapbot.security.audit import AuditLog, get_audit_log
from soapbot.security.principal import (
    AuthorityConfig,
    PrincipalResolver,
    normalize_id,
)
from soapbot.security.stages import (
    AuthorizationStage,
    GuardStage,
    InjectionScreenStage,
)

logger = logging.getLogger(__name__)


def build_persona_store(directory: Path | None = None) -> PersonaStore:
    store = PersonaStore()
    target = directory or (settings.config_dir / "personas")
    if target.exists():
        store.load_directory(target)
    else:
        logger.warning("persona directory not found: %s", target)
    return store


class EmbeddingBridge:
    """Adapts a ProviderRouter to the ``embed(list[str])`` shape memory needs."""

    def __init__(self, router: ProviderRouter) -> None:
        self.router = router

    async def embed(self, texts: list[str]) -> list[list[float]]:
        from soapbot.providers.base import CapabilitySlot

        if not self.router.has_capability(CapabilitySlot.EMBED):
            raise RuntimeError("no embedding provider configured")
        vectors = await self.router.embed(texts)
        if vectors and isinstance(vectors[0], float):
            return [vectors]  # type: ignore[list-item]
        return vectors  # type: ignore[return-value]


def build_pipeline(
    *,
    personas: PersonaStore,
    engine: AIEngine | None = None,
    access: AccessPolicy | None = None,
    wake: WakePolicy | None = None,
    memory: MemoryStore | None = None,
    kb: KnowledgeBase | None = None,
    extractor: MemoryExtractor | None = None,
    resolver: PrincipalResolver | None = None,
    audit: AuditLog | None = None,
    plugin_manager=None,
    budget=None,
    bilibili=None,
    tools=None,
    router=None,
) -> Pipeline:
    """Build the pipeline. Stage order is load-bearing.

    The security ordering is the part that matters most:

        dedup -> guard -> whitelist -> wake -> strip -> sanitize
              -> injection_screen -> authorization -> command -> persist ...

    ``guard`` runs before the whitelist because it establishes *who* is speaking;
    the whitelist can only judge *where* they are speaking once identity is known.
    ``command`` and ``persist`` run after both, so an unauthorised user never
    reaches a handler that reads the database.
    """
    policy = access or AccessPolicy()
    default_wake = wake or WakePolicy(wake_words=_collect_wake_words(personas))
    audit_log = audit or get_audit_log()
    principal_resolver = resolver or PrincipalResolver()
    pipeline = Pipeline()

    # --- identity first: nothing downstream may run for an unknown peer ---
    pipeline.add(DedupStage())
    pipeline.add(GuardStage(principal_resolver, audit=audit_log))

    # --- reachability gates ---
    pipeline.add(WhitelistStage(policy))
    pipeline.add(WakeStage(default_wake))
    pipeline.add(StripWakeWordStage(wake_words=default_wake.wake_words))
    pipeline.add(SanitizeStage())

    # --- content screening, before anything is stored or sent to a model ---
    pipeline.add(InjectionScreenStage(audit_log))
    pipeline.add(AuthorizationStage(audit_log))

    # --- commands run before anything expensive ---
    if memory is not None:
        pipeline.add(
            CommandStage(
                memory,
                kb,
                audit=audit_log,
                budget=budget,
                bilibili=bilibili,
                # The moderation commands compare the target's rank against the
                # caller's. That comparison has to use the same authority lists the
                # principal was resolved from, or "who outranks whom" would have
                # two different answers inside one request.
                authority=principal_resolver.authority,
            )
        )

    # --- plugin commands, strictly after core commands ---
    # Ordering matters: core commands are authoritative and must never be
    # shadowed by a plugin, so plugin dispatch runs second. Plugin command names
    # are also rejected at registration if they collide with a core command.
    if plugin_manager is not None:
        from soapbot.plugins.dispatch import (
            PluginCommandStage,
            PluginMessageHookStage,
        )

        pipeline.add(PluginCommandStage(plugin_manager.loader, audit=audit_log))
        pipeline.add(PluginMessageHookStage(plugin_manager.loader, audit=audit_log))

    # --- persistence of the inbound turn ---
    if memory is not None:
        pipeline.add(PersistStage(memory))

    # --- context assembly ---
    pipeline.add(PersonaStage(personas))
    if memory is not None:
        pipeline.add(RecallStage(memory))
    if kb is not None:
        pipeline.add(KnowledgeStage(kb))

    # --- voice: both directions are opt-in and both degrade to text -------------
    voice_router = router or getattr(engine, "router", None)
    transcriber = None
    if settings.voice_enabled and voice_router is not None:
        from soapbot.voice.stt import ProviderTranscriber

        transcriber = ProviderTranscriber(
            voice_router,
            max_bytes=settings.voice_max_bytes,
            language=settings.voice_language,
        )

    tts = None
    if settings.voice_tts_enabled:
        from soapbot.voice.tts import EdgeTts

        # Constructed eagerly, and deliberately not probed here: whether edge-tts is
        # importable is discovered on the first synthesis, where the fallback to text
        # already lives. Importing it at start-up would turn a missing optional
        # dependency into a failed boot.
        tts = EdgeTts(settings.voice_tts_voice)

    # --- generation ---
    if engine is not None:
        pipeline.add(
            ModelStage(
                engine,
                tools=tools,
                streaming=settings.stream_reply,
                chunk_chars=settings.stream_chunk_chars,
                first_packet_deadline=settings.stream_first_packet_deadline,
                send_interval=settings.stream_send_interval,
                transcriber=transcriber,
            )
        )
        pipeline.add(SafetyStage())

    # --- delivery and post-processing ---
    pipeline.add(ReplyStage(tts=tts))
    if memory is not None:
        pipeline.add(PersistReplyStage(memory))
        if extractor is not None:
            pipeline.add(MemoryWriteStage(memory, extractor, audit=audit_log))
    return pipeline


def _collect_wake_words(personas: PersonaStore) -> list[str]:
    words = {"soapbot"}
    for p in personas.all():
        words.update(w for w in p.wake_words if w)
    return sorted(words)


def build_authority(settings_obj=None) -> AuthorityConfig:
    """Build authority lists from configuration only.

    Kept as a function (not inlined) so tests can construct authority directly and
    so it is obvious that **no chat input can reach this code path**. An authority
    list that can be appended to from a message is a privilege-escalation bug by
    construction.
    """
    cfg = settings_obj or settings
    owners = {normalize_id(x) for x in (cfg.owner_ids or []) if x}
    admins = {normalize_id(x) for x in (cfg.admin_ids or []) if x}
    members = {normalize_id(x) for x in (cfg.member_ids or []) if x}
    if not owners and cfg.first_run_owner:
        owners = {normalize_id(cfg.first_run_owner)}
    return AuthorityConfig(
        owners=owners,
        admins=admins,
        members=members,
        trust_protocol_roles=bool(getattr(cfg, "trust_protocol_roles", False)),
    )


def build_access_policy(settings_obj=None) -> AccessPolicy:
    """Build the admission policy from configuration.

    Kept separate from :func:`build_runtime` and from the ``AccessPolicy`` default
    on purpose. The dataclass default is "closed" for private chat and "open" for
    groups; this function is where the operator's lists get applied. Without it,
    ``SOAPBOT_PRIVATE_ALLOWLIST`` and friends were inert: the settings existed,
    documentation referenced them, and ``AccessPolicy()`` was constructed with no
    arguments, so private messages were refused under *every* configuration.

    ``allow_unknown_private`` maps onto ``allow_all_private`` rather than being
    folded into the allow-list. The two express different intents — "this person
    may DM me" versus "anyone may DM me" — and collapsing them would mean an
    operator who later emptied the allow-list silently reopened private chat.
    """
    cfg = settings_obj or settings
    return AccessPolicy(
        group_allowlist={normalize_id(g) for g in (cfg.group_allowlist or []) if g},
        group_blacklist={normalize_id(g) for g in (cfg.group_blacklist or []) if g},
        user_blacklist={normalize_id(u) for u in (cfg.user_blacklist or []) if u},
        private_allowlist={normalize_id(u) for u in (cfg.private_allowlist or []) if u},
        allow_all_private=bool(cfg.allow_unknown_private),
    )


def build_runtime(
    *,
    router: ProviderRouter | None = None,
    personas: PersonaStore | None = None,
    access: AccessPolicy | None = None,
    wake: WakePolicy | None = None,
    compressor: ContextCompressor | None = None,
    memory: MemoryStore | None = None,
    kb: KnowledgeBase | None = None,
    extractor: MemoryExtractor | None = None,
    enable_memory_extraction: bool = True,
    authority: AuthorityConfig | None = None,
    audit: AuditLog | None = None,
    allow_unknown_private: bool = False,
    plugins_dir: Path | None = None,
    allow_untrusted_plugins: bool = False,
    budget=None,
    enable_budget: bool = False,
    enable_bilibili: bool = False,
    bilibili_tier: str = "",
) -> BotRuntime:
    persona_store = personas or build_persona_store()
    provider_router = router or ProviderRouter()
    audit_log = audit or get_audit_log()
    resolver = PrincipalResolver(authority or build_authority())

    # ``allow_unknown_private`` is folded into the policy *here* rather than kept as
    # a separate parameter threaded down to the stage. One object owns the whole
    # admission decision, so there is no way for "the flag says open" and "the
    # policy says closed" to both be true.
    if access is None:
        access = build_access_policy()
    elif allow_unknown_private and not access.allow_all_private:
        access = replace(access, allow_all_private=True)

    engine: AIEngine | None = None
    if provider_router.list_providers():
        history_provider = None
        if memory is not None:

            async def history_provider(session_key: str):  # type: ignore[misc]
                return await memory.history(session_key, limit=40)

        engine = AIEngine(
            router=provider_router,
            personas=persona_store,
            compressor=compressor
            or ContextCompressor(
                CompressionConfig(max_prompt_tokens=6000, reserve_for_reply=1200)
            ),
            descriptions=DescriptionCache(),
            history_provider=history_provider,
        )
    else:
        logger.warning("no providers configured; model stage disabled")

    if extractor is None and enable_memory_extraction:
        # Heuristic-only by default. Model-based extraction is opt-in because it
        # costs a call per qualifying message; group chats are chatty.
        extractor = MemoryExtractor(enable_model=False, summarizer=None)

    plugin_manager = None
    if plugins_dir is not None:
        # Pass the stores through so ``ctx.memory`` / ``ctx.kb`` work out of the box.
        # Wiring them here (rather than asking the operator to) is what makes the
        # capabilities usable: a plugin that declares ``memory_read`` and is approved
        # for it must actually be able to recall, otherwise the approval is theatre.
        # Capability is still enforced per call, so passing the store grants nothing
        # on its own.
        plugin_manager = build_plugin_manager(
            plugins_dir,
            allow_untrusted=allow_untrusted_plugins,
            audit=audit_log,
            memory=memory,
            kb=kb,
        )

    # The ledger is opt-in. Enabled by default it would put an unrequested
    # ``/budget`` command in every deployment's help text, and a budget nobody
    # configured is a control that reads as available but governs nothing.
    budget_commands = None
    if budget is not None or enable_budget:
        from soapbot.budget.policy import BudgetPolicy
        from soapbot.budget.store import BudgetStore

        if budget is None:
            from soapbot.config import settings as cfg

            if memory is None:
                # A budget without the shared database would be a ledger nobody
                # can query twice; refuse rather than silently building an
                # in-memory store that loses every approval on restart.
                raise RuntimeError(
                    "启用额度管理需要 memory 存储；请在 build_runtime 中传入 memory"
                )
            budget = BudgetStore(
                memory.db,
                BudgetPolicy(
                    currency=cfg.budget_currency,
                    period=cfg.budget_period,
                    period_cap_minor=cfg.budget_period_cap_minor,
                    per_request_cap_minor=cfg.budget_per_request_cap_minor,
                    request_ttl_seconds=cfg.budget_request_ttl_seconds,
                ),
                audit=audit_log,
            )
        from soapbot.budget.commands import BudgetCommands

        budget_commands = BudgetCommands(budget, audit=audit_log)

    bilibili_client = None
    bilibili_commands = None
    if enable_bilibili:
        from soapbot.bilibili.client import BilibiliClient
        from soapbot.bilibili.commands import BilibiliCommands
        from soapbot.bilibili.watcher import VideoWatcher
        from soapbot.config import settings as cfg

        bilibili_client = BilibiliClient(
            tier=bilibili_tier or cfg.bilibili_tier,
            timeout=cfg.bilibili_timeout_seconds,
            min_interval=cfg.bilibili_min_interval_seconds,
            per_minute=cfg.bilibili_rate_per_minute,
            router=provider_router,
        )
        bilibili_commands = BilibiliCommands(
            VideoWatcher(
                bilibili_client,
                router=provider_router,
                max_comments=cfg.bilibili_max_comments,
            ),
            audit=audit_log,
        )

    # One registry, shared by the model stage. Built here (not inside the stage) so
    # the management API can report the same tool table the model is offered —
    # two registries over one loader would drift only in what they hide.
    tool_registry = None
    if plugin_manager is not None:
        from soapbot.plugins.dispatch import PluginToolRegistry

        tool_registry = PluginToolRegistry(plugin_manager.loader)

    # MCP servers are configured, not discovered: nothing is started unless
    # config/mcp.yaml names it, and a rejected configuration degrades to "no external
    # tools" with an error in the log rather than stopping the bot.
    mcp_manager = None
    mcp_servers = []
    try:
        from soapbot.mcp.config import load_config as load_mcp_config

        mcp_servers = load_mcp_config(settings.config_dir / "mcp.yaml")
    except Exception as exc:
        logger.error("mcp configuration rejected, continuing without it: %s", exc)

    if mcp_servers:
        from soapbot.mcp.client import McpManager

        mcp_manager = McpManager(mcp_servers, role_rank=_mcp_role_rank)
        if tool_registry is not None:
            tool_registry.register_source(mcp_manager)

    pipeline = build_pipeline(
        personas=persona_store,
        engine=engine,
        access=access,
        wake=wake,
        memory=memory,
        kb=kb,
        extractor=extractor,
        resolver=resolver,
        audit=audit_log,
        plugin_manager=plugin_manager,
        budget=budget_commands,
        router=router,
        bilibili=bilibili_commands,
        tools=tool_registry,
    )
    # The trace collector is wired here, in the one place that assembles the runtime,
    # rather than in `app.py`. `Pipeline.observe` is the only hook that sees per-stage
    # timings, and it must be attached before the first message is processed — doing it
    # from the app would leave the collector silent for any runtime built by a test or
    # by a script, which is exactly the runtime nobody watches.
    bus = EventBus()
    traces = TraceStore()
    pipeline.observe(_observe_stage(traces))
    bus.subscribe("message.processed", lambda ctx: _record_trace(traces, ctx))

    return BotRuntime(
        pipeline=pipeline,
        bus=bus,
        plugins=plugin_manager,
        budget=budget,
        memory=memory,
        kb=kb,
        personas=persona_store,
        providers=provider_router,
        bilibili=bilibili_client,
        traces=traces,
        mcp=mcp_manager,
    )


def _mcp_role_rank(value: str) -> int:
    """Rank a configured role name; an unknown name ranks lowest.

    Failing closed is the point: a typo in ``min_role`` must grant *less* access than
    intended, and an exception raised here would instead surface as a confusing tool
    error on every call.
    """
    from soapbot.security.principal import Role

    try:
        return Role(value).rank
    except ValueError:
        return Role.ANONYMOUS.rank


async def _record_trace(traces: TraceStore, ctx: object) -> None:
    """Bus handler. Async because the bus contract is async, not because it awaits.

    Kept as a module function so the subscription is one line and the failure mode is
    obvious: if this raises, the trace is lost but the message has already been
    delivered — the bus logs and continues.
    """
    traces.on_processed(ctx)


def _observe_stage(traces: TraceStore):
    """Adapt the synchronous collector to the async observer contract.

    ``Pipeline.observe`` takes ``Callable[[ctx, stage, float], Awaitable[None]]`` and
    awaits the result. Passing a plain function returns ``None``, and awaiting ``None``
    raises — which the pipeline swallows as an observer error, so **every** timing is
    silently dropped while the endpoint keeps answering 200 with an empty list. That
    failure is invisible from the UI, which is why the adapter is a named function with
    a test rather than an inline lambda.
    """

    async def observe(ctx: object, stage: object, elapsed_ms: float) -> None:
        traces.observe_stage(ctx, stage, elapsed_ms)

    return observe


def build_plugin_manager(
    plugins_dir: Path,
    *,
    allow_untrusted: bool = False,
    audit: AuditLog | None = None,
    host_version: str = "",
    memory=None,
    kb=None,
    isolate: bool = True,
    approvals_path: Path | None = None,
):
    """Construct a plugin manager rooted at ``plugins_dir``.

    Loads nothing by itself. Discovery and approval are separate, explicit steps
    (see :class:`soapbot.plugins.loader.PluginLoader`): a bot that auto-loaded
    whatever it found would execute any code an attacker could write to
    ``data/plugins``.

    ``isolate`` defaults to **True**: plugins run in their own process. The default
    matters more than the capability here. The isolation review shipped a subprocess
    runner that turned out to have zero call sites, so the "process layer" was a
    library nobody used and the guarantee existed only in a document. A default of
    ``False`` would recreate that situation by accident — every deployment would
    have to opt in, and the ones that forgot would look identical to the ones that
    didn't.

    Set ``isolate=False`` only for embedded use or a platform where spawning a
    subprocess is impossible; ``soapbot doctor`` reports which mode is active.
    """
    from soapbot import __version__ as _version
    from soapbot.plugins.dispatch import PluginManager
    from soapbot.plugins.loader import PluginLoader
    from soapbot.plugins.supervisor import PluginSupervisor
    from soapbot.security.crypto import get_secret_box

    try:
        crypto = get_secret_box()
    except Exception as exc:  # key file unreadable: plugin secrets stay unencrypted
        logger.warning("secret box unavailable (%s); plugin storage is plaintext", exc)
        crypto = None

    from soapbot.plugins.approvals import ApprovalStore, default_path

    supervisor = PluginSupervisor() if isolate else None
    loader = PluginLoader(
        plugins_dir=plugins_dir,
        audit=audit or get_audit_log(),
        host_version=host_version or _version,
        allow_untrusted=allow_untrusted,
        crypto=crypto,
        memory=memory,
        kb=kb,
        supervisor=supervisor,
        # Persist approvals so a restart does not silently revoke every plugin.
        # Placed beside the database under ``data_dir`` rather than inside
        # ``plugins_dir`` — that directory is replaced on upgrade, and an
        # approval record that travels with the plugin is not an approval.
        approvals=ApprovalStore(approvals_path or default_path(settings.data_dir)),
    )
    manager = PluginManager(loader)
    if supervisor is not None:
        manager.install_isolation(
            supervisor=supervisor, memory=memory, kb=kb
        )
    return manager


def build_memory_stack(
    db: Database, router: ProviderRouter | None = None
) -> tuple[MemoryStore, KnowledgeBase]:
    bridge = EmbeddingBridge(router) if router is not None else None
    store = MemoryStore(db, embedder=bridge)
    kb = KnowledgeBase(db, embedder=bridge)
    return store, kb


def load_dotenv_if_present() -> None:
    env = Path(__file__).resolve().parents[3] / ".env"
    if not env.exists():
        return
    import os

    for line in env.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, _, value = line.partition("=")
        os.environ.setdefault(key.strip(), value.strip())
    logger.info("loaded .env from %s", env)


__all__ = [
    "EmbeddingBridge",
    "build_memory_stack",
    "build_persona_store",
    "build_pipeline",
    "build_runtime",
    "load_dotenv_if_present",
    "settings",
]
