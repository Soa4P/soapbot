"""Memory plugin: answer "what do you remember about us" using the host's recall.

Shows the intended shape of a Wave 3 plugin — the whole point is that it is short.
There is no database handle, no query language, no configuration: the operator
approves ``memory_read`` and the plugin can read the memories the host already
extracted from this conversation.

Contrast with what this would look like without the host's API:

    # what a plugin would otherwise have to do (and must NOT be able to do)
    session = host.db.session_factory()()
    rows = await session.execute(text("SELECT * FROM memories"))
    # ...which is a cross-tenant read of every group's memories, using SQL the
    # plugin authored, against a database the plugin was never granted.

The two calls below are the entire surface. ``ctx.memory`` is scoped to whoever
triggered the command; a plugin cannot name another session even if its author
tried, because there is no scope argument to name.

Read-only by design: a plugin cannot write memories. A plugin with write access
would own a persistence layer for prompt injection — plant one "我是管理员" and it is
recalled into every future turn. Writing stays in the host, behind ``vet_memory``.
"""

from __future__ import annotations

from soapbot.plugins.base import Plugin
from soapbot.plugins.context import CallerContext, PluginContext


class RemindPlugin(Plugin):
    async def setup(self, ctx: PluginContext) -> None:
        await super().setup(ctx)

        @ctx.command(
            "remember",
            description="查一下我还记得这个群的什么",
            usage="/remember [关键词]",
        )
        async def remember(caller: CallerContext, args: list[str]) -> str:
            # No capability check here on purpose — the host enforces it inside
            # ``recall``. Writing one in the plugin would be a *second* check with a
            # different idea of what is allowed, and the plugin's opinion is not
            # authoritative. If the operator has not approved memory_read this raises
            # and the host reports a clean failure.
            query = " ".join(args).strip()
            if query:
                hits = await ctx.memory.recall(query, limit=5)
                header = f"关于「{query}」我记得 {len(hits)} 条："
            else:
                hits = await ctx.memory.about_me(limit=5)
                header = f"关于大家我记得 {len(hits)} 条：" if hits else ""

            if not hits:
                return "这个群我还没记住什么。多聊几句，或者对我说「记住…」。"

            lines = [f"{i + 1}. {h.content}" for i, h in enumerate(hits)]
            return header + "\n" + "\n".join(lines)

        @ctx.command("whereami", description="看当前会话信息", usage="/whereami")
        async def whereami(caller: CallerContext, args: list[str]) -> str:
            # ``ctx.session`` needs the separate ``session`` capability. Keeping it
            # separate from ``memory_read`` matters: knowing which group you are in
            # is different from reading what was said in it.
            if not ctx.session.is_group:
                return f"当前是私聊会话（{ctx.session.display_name or '你'}）。"
            return f"当前群：{ctx.session.group_id}，你是 {ctx.session.display_name or caller.user_id}。"

        @ctx.command("rules", description="从知识库查群规", usage="/rules [关键词]")
        async def rules(caller: CallerContext, args: list[str]) -> str:
            # ``kb_read`` is a separate capability with its own tighter quota: the
            # knowledge base is operator material, not conversation data.
            if not ctx.kb.available:
                return "知识库没有启用。"
            query = " ".join(args).strip() or "群规"
            hits = await ctx.kb.search(query, limit=3)
            if not hits:
                return f"知识库里没找到和「{query}」有关的内容。"
            return "找到这些资料：\n" + "\n".join(
                f"- 【{h.title or '资料'}】{h.content}" for h in hits
            )
