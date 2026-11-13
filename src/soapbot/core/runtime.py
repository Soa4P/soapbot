"""Bot runtime: wires adapters to the pipeline.

Responsibilities:
- hold adapters and route their events through the per-session lock
- provide a single place where Wave 2+ AI stages are installed
- expose metrics for the WebUI dashboard

Keeping this separate from ``app.py`` means the bot can be driven headlessly by
tests without booting FastAPI.
"""

from __future__ import annotations

import contextlib
import logging
import time
from typing import Any

from soapbot.config import settings
from soapbot.core.adapter import Adapter
from soapbot.core.bus import EventBus
from soapbot.core.message import EventType, IncomingMessage
from soapbot.core.pipeline import Pipeline, PipelineContext
from soapbot.core.session import SessionLockManager, SessionStore

logger = logging.getLogger(__name__)


class BotRuntime:
    def __init__(
        self,
        *,
        pipeline: Pipeline | None = None,
        bus: EventBus | None = None,
        plugins=None,
        budget=None,
        memory=None,
        kb=None,
        personas=None,
        providers=None,
        bilibili=None,
        traces=None,
        mcp=None,
        passive=None,
        scene=None,
        layers=None,
        skills=None,
        locale: str = "",
        session_mapper=None,
    ) -> None:
        self.adapters: dict[str, Adapter] = {}
        self.pipeline = pipeline or Pipeline()
        self.bus = bus or EventBus()
        self.plugins = plugins
        """Optional :class:`soapbot.plugins.dispatch.PluginManager`."""

        self.approval_notifier: Any = None
        """Optional :class:`soapbot.notifications.dispatcher.ApprovalNotifier`.

        Installed by the app lifespan, not by ``build_runtime``: hand-assembled
        runtimes in tests must not acquire a global bus subscription as a side
        effect of construction.
        """

        self.budget = budget
        """Optional :class:`soapbot.budget.store.BudgetStore`.

        Held here, not only inside the command handler, because the periodic sweep
        needs it: reservations for unanswered requests must expire even while nobody
        is talking, and only the runtime outlives a single message.
        """

        # The stores the pipeline was built around, exposed for the read-only
        # management API. They are the *same objects* the stages use — a second
        # instance pointed at the same database would work but would drift (separate
        # in-process caches, separate embedders) and would make "what the UI shows"
        # subtly different from "what the bot does".
        self.memory = memory
        self.kb = kb
        self.personas = personas
        self.providers = providers
        self.traces = traces
        """Optional :class:`soapbot.core.trace.TraceStore`.

        ``None`` when a runtime was assembled by hand (some tests build a bare
        ``Pipeline``); the trace endpoints answer 503 in that case rather than
        fabricating an empty history that reads as "nothing has happened".
        """

        self.mcp = mcp
        """Optional :class:`soapbot.mcp.client.McpManager`.

        Held by the runtime rather than by the tool registry alone because MCP servers
        are child processes: their lifetime has to follow the bot's, otherwise a
        restart leaves orphans holding ports and file handles.
        """

        self.bilibili = bilibili
        """Optional :class:`soapbot.bilibili.client.BilibiliClient`.

        Held so shutdown can close its connection pool, and so the management API can
        report tier and call statistics without reaching into the command object.
        """

        self.passive = passive
        """Optional :class:`soapbot.core.observer.PassiveObserver`.

        Kept so the panel can show how many messages were read without being answered.
        A passive mode with no counter is indistinguishable from one that never ran.
        """

        self.layers = layers
        """Optional :class:`soapbot.memory.layers.MemoryLayers`.

        Exposed so the panel can read L1-L4 and the timeline from the same object the
        pipeline writes to. A second reader would eventually disagree about what is
        current.
        """

        self.scene = scene
        """Optional :class:`soapbot.memory.scene.SceneMemory`.

        Exposed for the same reason as ``memory``: the panel reads the *same* object the
        pipeline writes, so "what the card says" and "what the bot was told" cannot
        diverge. ``None`` when a runtime was assembled by hand, and the scene endpoints
        answer 503 rather than rendering an empty card that reads as "nothing learned yet".
        """

        self.skills = skills
        """Optional :class:`soapbot.memory.skills.SkillForge`.

        Held here because skills are files on the data volume, not rows: the panel lists,
        generates and deletes them, and none of that can go through ``memory``. This
        attribute existing is the difference between a feature and a module nobody calls —
        ``SkillForge`` was fully implemented and never constructed, so no skill could ever
        be produced by a running bot.
        """

        self.locale = locale or settings.default_locale
        """Language for replies this runtime produces.

        Resolved once at assembly and copied onto each ``PipelineContext``. Passed in
        rather than read from ``settings`` per message so a test can run a runtime in
        English without mutating global state.
        """

        if plugins is not None:
            # Plugins never receive an adapter. They can only ask the runtime to
            # deliver a message, and the runtime applies the adapter's own limits
            # (rate, length, capability) exactly as it does for core replies.
            plugins.install_sender(self._send_via_adapter)
            plugins.install_media_sender(self._send_media_via_adapter)
            if self.bilibili is not None:
                # 字幕面（bilibili.subtitle）需要宿主 L2 client：wbi 签名与 hdslb
                # 抓取留在宿主，插件只发 bvid、只拿文本。
                plugins.install_bilibili_client(self.bilibili)
        self.locks = SessionLockManager()
        self.sessions = SessionStore()
        self.session_mapper = session_mapper
        """Optional session mapper (unified chat).

        Called in :meth:`dispatch` *before* the session lock, because a successful
        mapping changes the lock key: a bound QQ private event joins the account's
        ``web:private:account-<id>`` session instead of its derived platform key.
        Hand-assembled test runtimes leave it ``None`` and keep the derived key.
        """
        self._unsubscribers: list[Any] = []
        self._running = False
        self.metrics: dict[str, Any] = {
            "inbound": 0,
            "handled": 0,
            "halted": 0,
            "failed": 0,
            # Counted separately from ``halted`` because it is not a decision the pipeline
            # made — it is input that was never a message. Folding it into ``halted`` would
            # make a group of people sending stickers look like a wall of permission
            # denials, and the operator would go looking for an authorization bug.
            "dropped_blank": 0,
            # Messages that arrived over-long and were shortened. Surfaced because a bot
            # that silently answers the first 8000 characters of a 40 000-character paste
            # looks like it ignored the rest, and the operator needs to be able to see
            # that this is what happened rather than guess.
            "truncated": 0,
            "started_at": 0.0,
        }

    # ------------------------------------------------------------------ adapters
    async def add_adapter(self, adapter: Adapter) -> None:
        self.adapters[adapter.meta.name] = adapter
        unsub = adapter.on_event(self._on_event)
        self._unsubscribers.append(unsub)

    async def start(self) -> None:
        self._running = True
        self.metrics["started_at"] = time.time()
        if self.mcp is not None:
            try:
                await self.mcp.ensure_tools()
            except Exception as exc:
                # A broken MCP server must not stop the bot: the chat works without
                # external tools, and a process that refuses to start because an
                # optional integration is down is worse than one that starts degraded.
                logger.error("mcp tool discovery failed: %s", exc)
        for adapter in self.adapters.values():
            try:
                await adapter.start()
                logger.info("adapter started: %s", adapter.meta.name)
            except Exception as exc:
                logger.error("adapter start failed: %s -> %s", adapter.meta.name, exc)
                adapter.health.last_error = str(exc)

    async def drain(self, *, timeout: float = 5.0) -> None:
        """Let in-flight work finish before anything it writes to is closed.

        Called by the app *before* ``stop()``, and the order is the whole point:
        handlers still running are mid-reply, mid-archive, and possibly mid-`send()`.
        Closing adapters and the database first turns that work into writes against
        dead resources — and because those failures land inside cancelled tasks, the
        operator sees a clean shutdown while the last replies were lost.

        Adapters go first, then the observer: a handler is what produces the archive
        payloads, so draining them in the other order would leave archives created
        after the observer was already drained.
        """
        for adapter in self.adapters.values():
            try:
                await adapter.drain_handlers(timeout=timeout)
            except Exception as exc:  # pragma: no cover - shutdown must not raise
                logger.warning("adapter drain failed %s: %s", adapter.meta.name, exc)
        if self.passive is not None:
            try:
                await self.passive.drain(timeout=timeout)
            except Exception as exc:  # pragma: no cover
                logger.warning("passive observer drain failed: %s", exc)

    async def stop(self) -> None:
        self._running = False
        if self.mcp is not None:
            with contextlib.suppress(Exception):
                await self.mcp.close()
        for adapter in self.adapters.values():
            try:
                await adapter.stop()
            except Exception as exc:  # pragma: no cover
                logger.warning("adapter stop failed %s: %s", adapter.meta.name, exc)
        for unsub in self._unsubscribers:
            with contextlib.suppress(Exception):
                unsub()
        self._unsubscribers.clear()

    # ------------------------------------------------------------------ dispatch
    async def _on_event(self, event: IncomingMessage) -> None:
        self.metrics["inbound"] += 1
        adapter = self.adapters.get(event.adapter)
        if adapter is None:
            logger.warning("event from unknown adapter %s", event.adapter)
            return

        if event.event_type is EventType.NOTICE:
            await self._on_notice(event)
            return

        # Dropped here rather than in a stage: a blank message has no identity worth
        # resolving, no scope worth checking, and no content worth screening. Running it
        # through the pipeline would spend a principal resolution and a whitelist lookup
        # to reach the conclusion that there is nothing to answer — and worse, a group
        # full of stickers would inflate ``halted`` until the panel's denial counter
        # looked like an attack.
        if event.is_blank:
            self.metrics["dropped_blank"] += 1
            logger.debug(
                "dropped blank message trace=%s adapter=%s", event.trace_id, event.adapter
            )
            return

        if event.truncated:
            self.metrics["truncated"] += 1
            logger.info(
                "inbound message truncated trace=%s adapter=%s chars=%d",
                event.trace_id,
                event.adapter,
                len(event.text),
            )

        # A crashed message used to leave no trace at all: it returned before
        # publishing, so the panel's "failed" bar could never move and the one
        # trace an operator most needs to see — the one that blew up — was the
        # only one missing. ``dispatch`` records it before returning.
        await self.dispatch(event)

    async def dispatch(self, event: IncomingMessage) -> PipelineContext | None:
        """Run one message through the pipeline and its observers. Returns the context.

        Split out of ``_on_event`` so a caller that already has an event — a test, the
        CLI's dry-run, the panel's "try this message" box — gets the same path the
        adapter does, including the bus publish. Calling ``pipeline.run`` directly
        skips the publish, and every observer (traces, passive mode) silently does
        nothing: exactly the failure mode where a feature looks wired and never runs.
        """
        adapter = self.adapters.get(event.adapter)
        if adapter is None:
            logger.warning("event from unknown adapter %s", event.adapter)
            return None
        if self.session_mapper is not None and not event.session_key_override:
            # Unified chat: a bound QQ private message joins the account's web session.
            # Must run before the lock — the key it produces *is* the lock key.
            mapped = await self.session_mapper(event)
            if mapped:
                event.session_key_override = mapped
        async with self.locks.get(event.session_key):
            ctx = PipelineContext(event=event, adapter=adapter, locale=self.locale)
            try:
                await self.pipeline.run(ctx)
            except Exception:
                self.metrics["failed"] += 1
                logger.exception("pipeline crashed trace=%s", event.trace_id)
                if self.traces is not None:
                    self.traces.note_failure(ctx)
                return ctx
            if ctx.halted:
                self.metrics["halted"] += 1
            else:
                self.metrics["handled"] += 1
            await self.bus.publish("message.processed", ctx)
            return ctx

    async def _on_notice(self, event: IncomingMessage) -> None:
        """Fan a platform notice out to plugin hooks.

        Notices deliberately do **not** go through the pipeline. The pipeline exists
        to decide whether a message may produce a reply — it resolves a principal,
        checks wake words and spends a model call. A notice has none of those
        questions: it is an observation ("someone was muted"), and running it
        through admission would mean a muted-user event could be refused for "not
        being addressed to the bot", which is meaningless.

        What a notice *does* need is the same identity discipline, so the caller is
        built from the event's own session key rather than from a principal the
        guard stage never resolved. A plugin therefore cannot use a notice to read
        or act on another session.

        Errors are swallowed with a log line: a broken observer must not take down
        the adapter's reader loop, which is waiting on nothing in particular and
        would simply stop receiving notices if this raised.
        """
        if self.plugins is None:
            return
        check = getattr(self.plugins, "has_notice_hooks", None)
        if check is None or not check():
            # Nothing to tell. Checked before building the caller so the common
            # case (no plugin subscribes to notices) costs one attribute lookup.
            return

        notice = dict((event.raw or {}).get("notice") or {})
        if not notice:  # pragma: no cover - adapters always fill this
            notice = {"type": "unknown", "group_id": event.group_id}

        from soapbot.plugins.context import CallerContext

        caller = CallerContext(
            user_id=event.sender.user_id,
            display_name=event.sender.display_name,
            # Anonymous on purpose: the host has not authenticated this peer in the
            # admission sense, and a notice arrives before any role resolution. A
            # plugin that needs privilege must ask the host to compare against a
            # role it resolved itself, not accept one from here.
            role="anonymous",
            session_key=event.session_key,
            scene=str(event.scene),
            group_id=event.group_id,
        )
        try:
            await self.plugins.on_notice(caller=caller, notice=notice)
        except Exception as exc:
            logger.warning(
                "notice dispatch failed adapter=%s type=%s err=%s",
                event.adapter,
                notice.get("type"),
                type(exc).__name__,
            )

    async def _send_via_adapter(self, session_key: str, text: str) -> None:
        """Delivery path for plugin-initiated sends.

        The plugin supplies a session key, not an adapter and not a target id. That
        split is the control: the runtime decides which adapter and which target,
        re-validates the key shape, and applies the same ``OutgoingMessage``
        construction core replies use — so a plugin cannot hand-craft a payload or
        address a session by a guessable group number.
        """
        from soapbot.core.message import MessageScene, MessageSegment, OutgoingMessage

        parts = session_key.split(":")
        if len(parts) != 3:
            raise ValueError("session_key must be adapter:scene:target")
        adapter_name, scene, target = parts
        adapter = self.adapters.get(adapter_name)
        if adapter is None:
            raise RuntimeError(f"no adapter {adapter_name!r} available for plugin send")

        out = OutgoingMessage(
            scene=MessageScene.GROUP if scene == "group" else MessageScene.PRIVATE,
            segments=[MessageSegment.text(text)],
            group_id=target if scene == "group" else "",
            user_id=target if scene != "group" else "",
        )
        receipt = await adapter.send(out)
        if not receipt.ok:
            logger.warning(
                "plugin send failed adapter=%s target=%s err=%s",
                adapter_name,
                target,
                receipt.error,
            )

    async def _send_media_via_adapter(
        self, session_key: str, image_b64: str, caption: str = ""
    ) -> None:
        """Delivery path for plugin-initiated image sends.

        Mirrors :meth:`_send_via_adapter`: the plugin supplies a session key, the
        runtime re-validates it and builds the ``OutgoingMessage`` — one IMAGE
        segment (base64; the adapter uploads or degrades per its capability set)
        followed by an optional caption segment. The decoded-size cap lives in the
        capability surface, before bytes ever reach an adapter.
        """
        import base64
        import binascii

        from soapbot.core.message import MessageScene, MessageSegment, OutgoingMessage

        parts = session_key.split(":")
        if len(parts) != 3:
            raise ValueError("session_key must be adapter:scene:target")
        adapter_name, scene, target = parts
        adapter = self.adapters.get(adapter_name)
        if adapter is None:
            raise RuntimeError(f"no adapter {adapter_name!r} available for plugin send")
        try:
            base64.b64decode(image_b64, validate=True)
        except (binascii.Error, ValueError) as exc:
            raise ValueError("image payload is not valid base64") from exc

        segments = [MessageSegment.image(b64=image_b64)]
        if caption.strip():
            segments.append(MessageSegment.text(caption))
        out = OutgoingMessage(
            scene=MessageScene.GROUP if scene == "group" else MessageScene.PRIVATE,
            segments=segments,
            group_id=target if scene == "group" else "",
            user_id=target if scene != "group" else "",
        )
        receipt = await adapter.send(out)
        if not receipt.ok:
            logger.warning(
                "plugin media send failed adapter=%s target=%s err=%s",
                adapter_name,
                target,
                receipt.error,
            )

    def status(self) -> dict[str, Any]:
        return {
            "running": self._running,
            "adapters": {
                name: {
                    "online": a.health.online,
                    "last_error": a.health.last_error,
                    "connected_at": a.health.connected_at,
                    "last_seen_at": a.health.last_seen_at,
                    "silent_for": (
                        round(time.time() - a.health.last_seen_at, 1)
                        if a.health.last_seen_at
                        else None
                    ),
                    "reconnect_attempts": a.health.reconnect_attempts,
                    "health_level": (
                        "danger"
                        if not a.health.online
                        else "warning"
                        if a.health.last_error or (
                            a.health.last_seen_at
                            and time.time() - a.health.last_seen_at > 300
                        )
                        else "healthy"
                    ),
                    "health_reason": (
                        (a.health.last_error or "no liveness evidence")
                        if not a.health.online
                        else "recent transport activity"
                    ),
                    "capabilities": sorted(str(c) for c in a.capabilities),
                    # Dispatch backpressure, per adapter. A cap whose drops are
                    # invisible is a cap nobody can tell apart from a quiet group,
                    # and the operator's only symptom would be unanswered messages.
                    "dispatch": a.backpressure_status(),
                }
                for name, a in self.adapters.items()
            },
            "metrics": dict(self.metrics),
        }
