"""Help plugin: lists available plugin commands.

Demonstrates that a plugin can enumerate the *host's* registry through the public
API without being given access to the loader itself. ``ctx.commands`` only returns
what this plugin registered, so a plugin cannot use it to map other plugins'
surfaces — the host exposes the merged list to the UI, not to plugins.
"""

from __future__ import annotations

from soapbot.plugins.base import Plugin
from soapbot.plugins.context import CallerContext, PluginContext


class HelpPlugin(Plugin):
    async def setup(self, ctx: PluginContext) -> None:
        await super().setup(ctx)

        @ctx.command("plughelp", description="列出插件命令", usage="/plughelp")
        async def plughelp(caller: CallerContext, args: list[str]) -> str:
            own = ctx.commands
            if not own:
                return "当前没有可用的插件命令。"
            lines = ["可用的插件命令："]
            for name in sorted(own):
                meta = own[name]
                desc = meta.get("description") or ""
                lines.append(f"/{name} — {desc}" if desc else f"/{name}")
            return "\n".join(lines)
