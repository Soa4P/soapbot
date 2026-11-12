"""Publish a 说说 only after a second, explicit command.

Three gates, because a post is visible to real people: the operator must enable
the protocol route, approve ``qzone_write`` for this plugin, and then a human
must type the confirm command. The host still requires ``confirm=true`` on every
write call, so a plugin bug cannot skip the last gate either.

The draft lives in the plugin's own encrypted storage namespace, not in a log,
and is deleted as soon as it is used — a pending post must not survive a restart
as a surprise.
"""

from __future__ import annotations

from soapbot.plugins.base import Plugin
from soapbot.plugins.context import CallerContext, PluginContext

DRAFT_KEY = "pending_post"


class QzoneDiaryPlugin(Plugin):
    async def setup(self, ctx: PluginContext) -> None:
        await super().setup(ctx)

        @ctx.command(
            "qzone-diary",
            description="起草一条说说（需二次确认才会发）",
            usage="/qzone-diary <正文>",
        )
        async def draft(caller: CallerContext, args: list[str]) -> str:
            text = " ".join(args).strip()
            if not text:
                return "用法：/qzone-diary <正文>"
            if len(text) > 2000:
                return "正文最多 2000 字。"
            await ctx.storage.set(DRAFT_KEY, text)
            return f"已记下草稿（{len(text)} 字）。确认发布请用 /qzone-diary-confirm。"

        @ctx.command(
            "qzone-diary-confirm",
            description="确认并发布刚才起草的说说",
            usage="/qzone-diary-confirm",
        )
        async def confirm(caller: CallerContext, args: list[str]) -> str:
            text = await ctx.storage.get(DRAFT_KEY)
            if not isinstance(text, str) or not text:
                return "没有待确认的草稿，先用 /qzone-diary 起草。"
            try:
                await ctx.qzone_write(text, confirm=True)
            except Exception:
                # Keep the draft so a transient failure is not a lost post, but say
                # plainly that nothing was published.
                return "发布失败，草稿仍在；请检查宿主开关与协议端状态后重试。"
            await ctx.storage.delete(DRAFT_KEY)
            return "已发布一条说说。"
