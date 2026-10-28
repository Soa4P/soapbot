"""Memory-backed pipeline stages and the /recall command.

These replace Wave 1's no-op ``RecordStage`` and give the AI engine a real
history provider, closing the loop: archive -> compress -> recall.
"""

from __future__ import annotations

import logging
from typing import ClassVar

from soapbot.core.adapter import Capability
from soapbot.core.message import MessageScene, SegmentType
from soapbot.core.pipeline import PipelineContext, Stage, StageResult
from soapbot.memory.extractor import MemoryExtractor
from soapbot.memory.store import KnowledgeBase, MemoryStore, RecallResult
from soapbot.security.audit import AuditLog, get_audit_log
from soapbot.security.injection import vet_memory
from soapbot.security.principal import (
    AuthorityConfig,
    Permission,
    Role,
    normalize_id,
)
from soapbot.security.stages import require

logger = logging.getLogger(__name__)


class PersistStage(Stage):
    """Archive the inbound message before the model runs.

    Ordering matters: if the model call fails, the user's message must still be
    recorded, otherwise the conversation has holes and compression summarises a
    lossy history.
    """

    name = "persist"

    def __init__(self, store: MemoryStore) -> None:
        self.store = store

    async def run(self, ctx: PipelineContext) -> StageResult:
        segments = ctx.extras.get("clean_segments") or ctx.event.segments
        text = "".join(s.plain() for s in segments if s.type is SegmentType.TEXT).strip()
        images = [s for s in segments if s.type is SegmentType.IMAGE]
        descs = ctx.extras.get("image_descriptions") or []
        image_desc = " / ".join(str(d) for d in descs) if descs else (
            f"[{len(images)} 张图片]" if images else ""
        )

        try:
            await self.store.archive_message(
                session_key=ctx.event.session_key,
                role="user",
                content=text,
                adapter=ctx.event.adapter,
                scene=str(ctx.event.scene),
                group_id=ctx.event.group_id,
                user_id=ctx.event.sender.user_id,
                user_name=ctx.event.sender.display_name,
                image_desc=image_desc,
                message_id=ctx.event.message_id,
                trace_id=ctx.event.trace_id,
            )
            ctx.extras["persisted_inbound"] = True
        except Exception as exc:
            logger.error("failed to archive inbound message: %s", exc)
            ctx.extras["persist_error"] = str(exc)
        return StageResult()


class PersistReplyStage(Stage):
    """Archive the assistant reply after a successful send."""

    name = "persist_reply"

    def __init__(self, store: MemoryStore) -> None:
        self.store = store

    async def run(self, ctx: PipelineContext) -> StageResult:
        if not ctx.model_reply or not ctx.extras.get("send_ok"):
            return StageResult()
        try:
            await self.store.archive_message(
                session_key=ctx.event.session_key,
                role="assistant",
                content=ctx.model_reply,
                adapter=ctx.event.adapter,
                scene=str(ctx.event.scene),
                group_id=ctx.event.group_id,
                user_id="",
                user_name="soapbot",
                trace_id=ctx.event.trace_id,
            )
        except Exception as exc:
            logger.error("failed to archive reply: %s", exc)
        return StageResult()


class RecallStage(Stage):
    """Retrieve relevant long-term memories and inject them as context."""

    name = "recall"

    def __init__(self, store: MemoryStore, *, top_k: int = 6, min_chars: int = 4) -> None:
        self.store = store
        self.top_k = top_k
        self.min_chars = min_chars

    async def run(self, ctx: PipelineContext) -> StageResult:
        segments = ctx.extras.get("clean_segments") or ctx.event.segments
        query = "".join(s.plain() for s in segments if s.type is SegmentType.TEXT).strip()
        if len(query) < self.min_chars:
            return StageResult()

        try:
            result: RecallResult = await self.store.recall(
                query, scope=ctx.event.session_key, limit=self.top_k
            )
        except Exception as exc:
            logger.warning("recall failed, continuing without memory: %s", exc)
            return StageResult()

        if result.items:
            ctx.extras["recall_prompt"] = result.to_prompt()
            ctx.extras["recall_count"] = len(result.items)
            ctx.extras["recall_items"] = [
                {"id": it.id, "content": it.content, "score": it.score, "source": it.source}
                for it in result.items
            ]
        return StageResult()


class KnowledgeStage(Stage):
    """Inject RAG snippets for the current query."""

    name = "knowledge"

    def __init__(self, kb: KnowledgeBase, *, top_k: int = 3, max_chars: int = 1200) -> None:
        self.kb = kb
        self.top_k = top_k
        self.max_chars = max_chars

    async def run(self, ctx: PipelineContext) -> StageResult:
        segments = ctx.extras.get("clean_segments") or ctx.event.segments
        query = "".join(s.plain() for s in segments if s.type is SegmentType.TEXT).strip()
        if len(query) < 4:
            return StageResult()
        try:
            hits = await self.kb.search(query, limit=self.top_k)
        except Exception as exc:
            logger.warning("knowledge search failed: %s", exc)
            return StageResult()
        if not hits:
            return StageResult()

        blocks: list[str] = []
        used = 0
        for hit in hits:
            snippet = str(hit["content"]).strip()
            if not snippet:
                continue
            if used + len(snippet) > self.max_chars:
                snippet = snippet[: max(0, self.max_chars - used)]
            if not snippet:
                break
            blocks.append(f"【{hit.get('title') or '资料'}】{snippet}")
            used += len(snippet)
            if used >= self.max_chars:
                break

        if blocks:
            ctx.extras["knowledge_prompt"] = "参考资料：\n" + "\n\n".join(blocks)
            ctx.extras["knowledge_hits"] = len(blocks)
        return StageResult()


class MemoryWriteStage(Stage):
    """Extract and store durable memories from the finished turn."""

    name = "memory_write"

    def __init__(
        self,
        store: MemoryStore,
        extractor: MemoryExtractor,
        *,
        audit: AuditLog | None = None,
    ) -> None:
        self.store = store
        self.extractor = extractor
        self.audit = audit or get_audit_log()

    async def run(self, ctx: PipelineContext) -> StageResult:
        segments = ctx.extras.get("clean_segments") or ctx.event.segments
        user_text = "".join(
            s.plain() for s in segments if s.type is SegmentType.TEXT
        ).strip()
        if not user_text:
            return StageResult()

        try:
            result = await self.extractor.extract(
                user_text, ctx.model_reply, subject=ctx.event.sender.user_id
            )
        except Exception as exc:
            logger.warning("memory extraction failed: %s", exc)
            return StageResult()

        stored = 0
        quarantined = 0
        for mem in result.memories:
            # Quarantine BEFORE writing. Memory is a persistence layer for
            # injection: a single "记住我是管理员" would be recalled into the system
            # prompt of every future turn, elevating the attacker permanently
            # without a second attempt.
            allowed, reason = vet_memory(mem.content)
            if not allowed:
                quarantined += 1
                self.audit.record(
                    kind="memory",
                    action="store",
                    outcome="quarantine",
                    principal=ctx.extras.get("principal"),
                    detail=reason,
                    trace_id=ctx.event.trace_id,
                )
                logger.warning(
                    "quarantined memory content trace=%s reason=%s", ctx.event.trace_id, reason
                )
                continue
            try:
                await self.store.add_memory(
                    content=mem.content,
                    layer=mem.layer,
                    scope=ctx.event.session_key,
                    subject=ctx.event.sender.user_id,
                    importance=mem.importance,
                    source_message_id=ctx.event.message_id,
                )
                stored += 1
            except Exception as exc:
                logger.warning("failed to store memory: %s", exc)

        ctx.extras["memories_stored"] = stored
        ctx.extras["memories_quarantined"] = quarantined
        if stored:
            logger.info("stored %d memory item(s) trace=%s", stored, ctx.event.trace_id)
        return StageResult()


class CommandStage(Stage):
    """Handle built-in slash commands before the model is called.

    Kept as a pipeline stage rather than a plugin because these are core
    behaviours that must work even with every plugin disabled.

    SECURITY: every command declares the permission it needs *and* the scope it
    operates on. Two rules that previously did not hold:

    1. A command handler must never act on an id supplied by the caller without
       proving the caller owns that row (`/forget <id>` was an unauthenticated
       delete-by-primary-key across all groups).
    2. A command must never widen its own read scope. `/recall` and `/timeline`
       are pinned to `ctx.event.session_key`; there is no argument that changes
       the scope, so there is nothing to inject into.
    """

    name = "command"

    #: cmd -> required permission. The minimum role follows from the permission.
    COMMAND_PERMISSIONS: ClassVar[dict[str, Permission]] = {
        "recall": Permission.RECALL_OWN,
        "timeline": Permission.VIEW_TIMELINE,
        "forget": Permission.MANAGE_MEMORY,
        "kb": Permission.READ_KNOWLEDGE,
        "help": Permission.USE_COMMAND,
        "ping": Permission.USE_COMMAND,
        # ``/budget`` itself only needs USE_COMMAND: viewing the group's remaining
        # quota is not privileged, and *requesting* spend is deliberately open to
        # members — the control is that a second person must approve. The
        # approve/deny sub-commands re-check APPROVE_PAYMENT inside the handler,
        # because a single entry in this table cannot express "one permission for
        # the view, another for the decision".
        "budget": Permission.USE_COMMAND,
        # Same reasoning as ``budget``: the command itself is open to any member who
        # may use commands, because fetching a public video's title is not privileged.
        # The controls that matter are elsewhere — a per-session query limit and a
        # per-deployment kill switch — and neither is expressed by a role floor.
        "bili": Permission.USE_COMMAND,
        # Group moderation. These make the bot do something *to a person* in front
        # of the whole group, under the owner's name, so they need their own
        # permission rather than riding on USE_COMMAND.
        "mute": Permission.MODERATE_GROUP,
        "unmute": Permission.MODERATE_GROUP,
        "kick": Permission.MODERATE_GROUP,
        # Hyphenated on purpose: ``/recall`` already means "search my memories" and
        # repurposing it would silently break every existing deployment's habit,
        # with the failure mode being "the bot searched for a message id".
        "recall-msg": Permission.MODERATE_GROUP,
    }

    #: Longest mute the command will pass through, in seconds. 30 days matches the
    #: protocol's own ceiling; anything longer is either a typo or an attempt to
    #: use the bot to permanently silence someone.
    MAX_MUTE_SECONDS = 30 * 24 * 3600
    DEFAULT_MUTE_MINUTES = 10

    def __init__(
        self,
        store: MemoryStore,
        kb: KnowledgeBase | None = None,
        *,
        audit: AuditLog | None = None,
        budget=None,
        bilibili=None,
        authority: AuthorityConfig | None = None,
    ) -> None:
        self.store = store
        self.kb = kb
        self.audit = audit or get_audit_log()
        # Needed by the moderation commands, which must refuse to act on someone
        # whose *host-resolved* rank is at or above the caller's. Without it, a
        # group moderator could mute the bot's owner through the bot.
        self.authority = authority or AuthorityConfig()
        # Optional: a deployment without a ledger configured simply has no
        # ``/budget`` command, rather than failing to build the pipeline.
        self.budget = budget
        # Same pattern: ``None`` means the feature is off, and ``/help`` omits the line
        # so the help text never advertises a command that answers "未启用".
        self.bilibili = bilibili

    async def run(self, ctx: PipelineContext) -> StageResult:
        segments = ctx.extras.get("clean_segments") or ctx.event.segments
        text = "".join(s.plain() for s in segments if s.type is SegmentType.TEXT).strip()
        if not text.startswith(("/", "!", "／")):
            return StageResult()

        parts = text[1:].split()
        if not parts:
            return StageResult()
        cmd = parts[0].lower()
        args = parts[1:]

        # ``-`` maps to ``_`` so multi-word command names work: ``/recall-msg``
        # would otherwise resolve to ``_cmd_recall-msg``, which is not a valid
        # attribute, so the command silently fell through to the model and the
        # user got a chat reply instead of an action. ``cmd`` itself stays dashed
        # for permission lookup and help text, because that is what users type.
        handler = getattr(self, f"_cmd_{cmd.replace('-', '_')}", None)
        if handler is None:
            return StageResult()

        # Authorise BEFORE invoking the handler. A handler that opens the database
        # or touches the knowledge base has already leaked by the time it could
        # check anything itself.
        permission = self.COMMAND_PERMISSIONS.get(cmd, Permission.MANAGE_CONFIG)
        allowed, refusal = require(ctx, permission, audit=self.audit, action=f"cmd:{cmd}")
        if not allowed:
            ctx.model_reply = refusal
            ctx.extras["command"] = cmd
            ctx.extras["command_denied"] = True
            ctx.extras["skip_model"] = True
            return StageResult()

        try:
            reply = await handler(ctx, args)
        except Exception as exc:
            logger.exception("command %s failed", cmd)
            # Never echo the raw exception: it can contain SQL, file paths or
            # document fragments that the caller is not authorised to see.
            self.audit.record(
                kind="command",
                action=f"cmd:{cmd}",
                outcome="block",
                principal=ctx.extras.get("principal"),
                detail=type(exc).__name__,
                trace_id=ctx.event.trace_id,
            )
            reply = "命令执行失败，请联系管理员。"

        if reply is None:
            return StageResult()

        self.audit.record(
            kind="command",
            action=f"cmd:{cmd}",
            outcome="allow",
            principal=ctx.extras.get("principal"),
            trace_id=ctx.event.trace_id,
        )
        ctx.model_reply = reply
        ctx.extras["command"] = cmd
        ctx.extras["skip_model"] = True
        return StageResult()

    # ---------------------------------------------------------------- commands
    async def _cmd_recall(self, ctx: PipelineContext, args: list[str]) -> str:
        query = " ".join(args).strip()
        if not query:
            return "用法：/recall <关键词>　例如：/recall 我的喜好"

        principal = ctx.extras.get("principal")
        # Scope is pinned to the caller's own session. It is deliberately NOT
        # derived from args: a user-controlled scope parameter would let group A
        # read group B's memories by passing `--scope other:group:1`.
        #
        # The session key comes from the *event* (what the transport delivered),
        # never from the principal's mutable fields, so a stage that rewrote the
        # principal could not widen this.
        session_scope = ctx.event.session_key

        result = await self.store.recall(query, scope=session_scope, limit=8)
        if not result.items:
            return f"没有找到与「{query}」相关的记忆。"

        # Belt and braces: filter the returned rows against the caller's scope even
        # though the query already did. A future change to `recall` (e.g. adding a
        # global fallback) must not silently become a cross-scope leak.
        #
        # ``read_any`` uses RECALL_ANY, the *read* permission — never
        # MANAGE_MEMORY_ANY. Reading broadly and writing broadly are separate grants.
        read_any = bool(principal and principal.can(Permission.RECALL_ANY))
        allowed = [
            it for it in result.items if it.scope == session_scope or read_any
        ]
        if not allowed:
            return f"没有找到与「{query}」相关的记忆。"

        lines = [
            f"{i + 1}. {it.content}（{it.source}，相关度 {it.score:.3f}）"
            for i, it in enumerate(allowed)
        ]
        header = f"找到 {len(allowed)} 条记忆"
        if not result.fused:
            header += "（仅单一通道命中，向量或关键词其一不可用）"
        return header + "：\n" + "\n".join(lines)

    async def _cmd_timeline(self, ctx: PipelineContext, args: list[str]) -> str:
        try:
            limit = int(args[0]) if args else 12
        except ValueError:
            limit = 12
        rows = await self.store.timeline(ctx.event.session_key, limit=max(1, min(limit, 50)))
        if not rows:
            return "当前会话还没有历史记录。"
        lines: list[str] = []
        for r in rows:
            who = "我" if r["role"] == "assistant" else (r["user_name"] or "用户")
            content = str(r["content"])[:60]
            if r.get("image_desc"):
                content += f" [图片:{str(r['image_desc'])[:30]}]"
            lines.append(f"{who}: {content}")
        return f"最近 {len(rows)} 条记录：\n" + "\n".join(lines)

    async def _cmd_forget(self, ctx: PipelineContext, args: list[str]) -> str:
        """Delete one memory — but only if it belongs to the caller's scope.

        Threat this closes: the previous implementation deleted by primary key
        alone, so `/forget 1`, `/forget 2`, ... walked the whole table. Any group
        member could destroy another group's memories, and (because ids are
        sequential) could also *probe* which ids exist from the differing replies.

        The ownership check happens before deletion, and the two failure modes —
        "does not exist" and "exists but not yours" — return the *same* message so
        the command cannot be used as an existence oracle.
        """
        if not args:
            return "用法：/forget <记忆ID>"
        try:
            memory_id = int(args[0])
        except ValueError:
            return "记忆 ID 必须是数字。"

        principal = ctx.extras.get("principal")
        item = await self.store.get_memory(memory_id)
        not_found = f"没有找到记忆 #{memory_id}"

        if item is None:
            self.audit.record(
                kind="memory",
                action="forget",
                outcome="deny",
                principal=principal,
                detail=f"id={memory_id} missing",
                trace_id=ctx.event.trace_id,
            )
            return not_found

        if not self._owns_scope(principal, item.scope):
            # Indistinguishable from "missing" on purpose.
            self.audit.record(
                kind="memory",
                action="forget",
                outcome="deny",
                principal=principal,
                detail=f"id={memory_id} scope_mismatch",
                trace_id=ctx.event.trace_id,
            )
            return not_found

        ok = await self.store.delete_memory(memory_id)
        self.audit.record(
            kind="memory",
            action="forget",
            outcome="allow" if ok else "deny",
            principal=principal,
            detail=f"id={memory_id}",
            trace_id=ctx.event.trace_id,
        )
        return f"已删除记忆 #{memory_id}" if ok else not_found

    @staticmethod
    def _owns_scope(principal, scope: str, *, write: bool = True) -> bool:
        """May this principal **write to** a row with this scope?

        Note the asymmetry, which is the whole point of this helper existing:

        * ``MANAGE_MEMORY_ANY`` (owner) may write anywhere.
        * ``RECALL_ANY`` (admin) grants *read* reach only. Using it here would let
          a diagnostic read grant authorise a destructive write — that was a real
          bug: an admin in group A could delete group B's memories because the
          delete path reused the cross-scope *read* permission.
        * Everyone else is limited to their own session.
        """
        if principal is None:
            return False
        if not scope:
            # Global rows are operator-owned; never deletable by a scoped caller.
            return bool(principal.can(Permission.MANAGE_MEMORY_ANY))
        if write and principal.can(Permission.MANAGE_MEMORY_ANY):
            return True
        if scope == principal.session_key:
            return True
        # A memory written under the user's own private session is theirs.
        return scope.endswith(f":private:{principal.user_id}")

    async def _cmd_kb(self, ctx: PipelineContext, args: list[str]) -> str:
        """Query the operator's knowledge base.

        Guarded by ``READ_KNOWLEDGE`` (admin+). Knowledge documents typically
        contain internal notes, and even *listing* them leaks their existence, so
        the permission check happens in ``run()`` before this method is reached.
        """
        if self.kb is None:
            return "知识库未启用。"
        if not args:
            docs = await self.kb.list_documents()
            if not docs:
                return "知识库是空的，可通过 WebUI 上传文档。"
            return "知识库文档：\n" + "\n".join(
                f"- {d['title']}（{d['doc_id']}，{d['chunks']} 段）" for d in docs
            )
        hits = await self.kb.search(" ".join(args), limit=3)
        if not hits:
            return "知识库里没找到相关内容。"
        return "知识库检索结果：\n" + "\n".join(
            f"- 【{h.get('title') or '资料'}】{str(h['content'])[:150]}" for h in hits
        )

    async def _cmd_budget(self, ctx: PipelineContext, args: list[str]) -> str:
        """Delegate to the budget module when one is configured.

        Returning a clear "not enabled" instead of a generic failure matters:
        otherwise a deployment that never set a ledger sees "命令执行失败，请联系
        管理员" for a command that is listed in ``/help``, and the operator goes
        looking for a bug rather than a missing setting.
        """
        if self.budget is None:
            return "未启用额度管理。"
        return await self.budget.handle(ctx, args)

    async def _cmd_bili(self, ctx: PipelineContext, args: list[str]) -> str:
        """Delegate to the Bilibili module when the feature is enabled.

        The module is optional for the same reason the ledger is: a deployment with the
        feature off must not advertise it, and must not build a network client it will
        never use.
        """
        if self.bilibili is None:
            return "未启用 B 站功能。"
        return await self.bilibili.handle(ctx, args)

    async def _cmd_help(self, ctx: PipelineContext, args: list[str]) -> str:
        lines = [
            "可用命令：",
            "/recall <关键词> — 检索我的长期记忆",
            "/timeline [数量] — 查看当前会话历史",
            "/forget <ID> — 删除某条记忆",
            "/kb [关键词] — 查看或检索知识库",
        ]
        if self.budget is not None:
            lines.append("/budget [金额 用途] — 查看额度或发起消费申请")
        if self.bilibili is not None:
            lines.append("/bili <BV号|链接> — 查看视频信息或生成观后感")
        # Moderation is listed only when the adapter can actually do it. Advertising
        # "/mute" on a transport without MUTE would produce a command that always
        # answers "不支持" — worse than not offering it.
        adapter = getattr(ctx, "adapter", None)
        if adapter is not None and adapter.supports(Capability.MUTE):
            lines.append("/mute <QQ> [分钟] — 禁言（默认 10 分钟）")
            lines.append("/unmute <QQ> — 解除禁言")
        if adapter is not None and adapter.supports(Capability.RECALL):
            lines.append("/recall-msg <消息ID> — 撤回消息（也可直接回复消息后发送）")
        if adapter is not None and adapter.supports(Capability.KICK):
            lines.append("/kick <QQ> — 移出本群")
        lines.append("/help — 显示本帮助")
        return "\n".join(lines)

    async def _cmd_ping(self, ctx: PipelineContext, args: list[str]) -> str:
        return f"pong（会话 {ctx.event.session_key}）"

    # ------------------------------------------------------------- moderation
    async def _cmd_mute(self, ctx: PipelineContext, args: list[str]) -> str:
        target, error = self._moderation_target(ctx, args)
        if error:
            return error

        minutes = self.DEFAULT_MUTE_MINUTES
        if len(args) >= 2:
            try:
                minutes = int(args[1])
            except ValueError:
                return "时长必须是整数分钟，例如：/mute 123456 30"
        if minutes < 0:
            return "时长不能为负数；解除禁言请用 /unmute"
        seconds = min(minutes * 60, self.MAX_MUTE_SECONDS)

        adapter = ctx.adapter
        receipt = await adapter.set_group_ban(ctx.event.group_id, target, seconds)
        self.audit.record(
            kind="moderation",
            action="mute",
            outcome="allow" if receipt.ok else "block",
            principal=ctx.extras.get("principal"),
            detail=f"group={ctx.event.group_id} target={target} seconds={seconds} "
            f"ok={receipt.ok}",
            trace_id=ctx.event.trace_id,
        )
        if not receipt.ok:
            return f"禁言失败：{receipt.error or '未知原因'}（机器人需要有群管理员权限）"
        return f"已禁言 {target}，时长 {minutes} 分钟。"

    async def _cmd_unmute(self, ctx: PipelineContext, args: list[str]) -> str:
        target, error = self._moderation_target(ctx, args)
        if error:
            return error
        receipt = await ctx.adapter.set_group_ban(ctx.event.group_id, target, 0)
        self.audit.record(
            kind="moderation",
            action="unmute",
            outcome="allow" if receipt.ok else "block",
            principal=ctx.extras.get("principal"),
            detail=f"group={ctx.event.group_id} target={target} ok={receipt.ok}",
            trace_id=ctx.event.trace_id,
        )
        if not receipt.ok:
            return f"解除禁言失败：{receipt.error or '未知原因'}"
        return f"已解除 {target} 的禁言。"

    async def _cmd_kick(self, ctx: PipelineContext, args: list[str]) -> str:
        target, error = self._moderation_target(ctx, args)
        if error:
            return error
        receipt = await ctx.adapter.set_group_kick(
            ctx.event.group_id, target, reject_add_request=False
        )
        self.audit.record(
            kind="moderation",
            action="kick",
            outcome="allow" if receipt.ok else "block",
            principal=ctx.extras.get("principal"),
            detail=f"group={ctx.event.group_id} target={target} ok={receipt.ok}",
            trace_id=ctx.event.trace_id,
        )
        if not receipt.ok:
            return f"移出失败：{receipt.error or '未知原因'}（机器人需要有群管理员权限）"
        return f"已将 {target} 移出本群。"

    async def _cmd_recall_msg(self, ctx: PipelineContext, args: list[str]) -> str:
        """Withdraw one message, but only if this session archived it.

        The protocol's delete call takes a bare message id and no group. So the
        command cannot ask the platform "is this message in my group" — it has to
        already know. ``find_message`` scoped to ``session_key`` is that knowledge:
        an id from another group, or one the bot never saw, returns "找不到".
        Without this check, ``/recall <id>`` is a delete primitive over the whole
        account, and message ids are sequential enough to enumerate.
        """
        raw_id = args[0] if args else self._replied_message_id(ctx)
        if not raw_id:
            return "用法：/recall-msg <消息ID>，或先引用要撤回的消息再发送 /recall-msg"

        message_id = str(raw_id).strip()
        found = await self.store.find_message(ctx.event.session_key, message_id)
        if found is None:
            # Same message for "not here" and "never seen": distinguishing them
            # would turn the command into an existence oracle.
            return "在本会话中找不到这条消息，无法撤回。"

        receipt = await ctx.adapter.recall(message_id)
        self.audit.record(
            kind="moderation",
            action="recall",
            outcome="allow" if receipt.ok else "block",
            principal=ctx.extras.get("principal"),
            detail=f"group={ctx.event.group_id} message={message_id} ok={receipt.ok}",
            trace_id=ctx.event.trace_id,
        )
        if not receipt.ok:
            return f"撤回失败：{receipt.error or '未知原因'}"
        return "已撤回该消息。"

    def _replied_message_id(self, ctx: PipelineContext) -> str:
        for seg in ctx.event.segments:
            if seg.type is SegmentType.REPLY:
                return str(seg.data.get("id", "") or "")
        return ""

    def _moderation_target(
        self, ctx: PipelineContext, args: list[str]
    ) -> tuple[str, str]:
        """Validate the target of a moderation command.

        Returns ``(target_id, "")`` on success or ``("", refusal)``. All of the
        checks are here rather than in each command because they must hold
        identically for mute, unmute and kick; a per-command copy is how one of
        them quietly loses a check during a later edit.

        The authority comparison is the important one. Bot rank and QQ group rank
        are independent: without it, a bot admin can mute the bot's *owner* — the
        person who configured the bot — and the owner has no way to undo it from
        chat because the undo is also a moderation command the admin can run.
        """
        if ctx.event.scene is not MessageScene.GROUP:
            return "", "该命令只能在群聊中使用。"
        if not args:
            return "", "请提供要操作的 QQ 号，例如：/mute 123456 10"

        raw = normalize_id(args[0])
        if not raw or not raw.isdigit():
            return "", "QQ 号格式不正确。"

        bot_id = normalize_id(ctx.event.self_id)
        if bot_id and raw == bot_id:
            return "", "不能对机器人自己执行该操作。"

        caller = ctx.extras.get("principal")
        caller_id = normalize_id(caller.user_id) if caller is not None else ""
        if raw == caller_id:
            return "", "不能对你自己执行该操作。"

        caller_role = caller.role if caller is not None else Role.ANONYMOUS
        target_role, _source = self.authority.role_for(raw)
        if target_role.rank >= caller_role.rank:
            # Equal rank is refused too: two admins moderating each other is a
            # fight the bot should not take sides in, and "strictly lower" is the
            # only rule that cannot be gamed by granting a second admin.
            return "", "对方权限不低于你，无法通过机器人对其执行该操作。"

        adapter = getattr(ctx, "adapter", None)
        if adapter is None:
            return "", "当前没有可用的连接，无法执行。"
        return raw, ""


async def make_history_provider(store: MemoryStore, *, limit: int = 40):
    """Adapter used by AIEngine to fetch prior turns."""

    async def _provider(session_key: str) -> list[dict]:
        return await store.history(session_key, limit=limit)

    return _provider
