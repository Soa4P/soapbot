"""Read-only 空间 observer, through the host's vetted qzone gateway.

The plugin declares only ``command`` and ``qzone_read``. It has no ``http``, so it
cannot reach the protocol endpoint itself, and no ``qzone_write``, so a prompt
injection inside a 说说 cannot turn this reader into a publisher. The response
body is untrusted text: only a few scalars are picked out, never evaluated.
"""

from __future__ import annotations

import json

from soapbot.plugins.base import Plugin
from soapbot.plugins.context import CallerContext, PluginContext


class QzoneWatchPlugin(Plugin):
    async def setup(self, ctx: PluginContext) -> None:
        await super().setup(ctx)

        @ctx.command(
            "qzone-watch",
            description="看关注的人最近发的说说",
            usage="/qzone-watch [条数]",
        )
        async def watch(caller: CallerContext, args: list[str]) -> str:
            try:
                limit = max(1, min(int(args[0]) if args else 5, 20))
            except ValueError:
                return "用法：/qzone-watch [条数]"
            try:
                result = await ctx.qzone_read(
                    "get_friend_feeds", {"limit": limit}
                )
            except Exception:
                # Fixed wording: the gateway's error text must not become a reply
                # that echoes an endpoint URL or a token.
                return "空间读取不可用：请确认宿主已开启并配置协议端。"
            try:
                payload = json.loads(result.get("text") or "{}")
            except (ValueError, TypeError):
                return "空间返回了无法解析的内容。"
            items = payload.get("data") or payload.get("feeds") or []
            if not isinstance(items, list) or not items:
                return "最近没有新的说说。"
            lines: list[str] = []
            for item in items[:limit]:
                if not isinstance(item, dict):
                    continue
                name = str(item.get("name") or item.get("nick") or "某人")
                text = str(item.get("content") or item.get("text") or "").replace("\n", " ")
                lines.append(f"- {name}：{text[:80]}")
            return "最近的说说：\n" + "\n".join(lines)
