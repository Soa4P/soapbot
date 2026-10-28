"""Echo plugin: the reference implementation of the public plugin API.

It exists to prove a specific claim from the plan's acceptance gate A5:

    A plugin can add a command and a tool using **only** the public ``ctx`` API,
    without editing any core file.

Everything here goes through ``ctx.command`` / ``ctx.tool``. It never imports
``soapbot.core``, never touches the adapter, and never sees the pipeline.

Note what it does *not* do, and why that matters:

* It does not sanitise its own output — the host does that. A plugin that
  sanitises for itself would be relying on the author getting it right.
* It does not check permissions itself beyond declaring ``min_role`` — the host
  re-checks against the resolved principal.
* It declares only ``command`` and ``tool``; asking for more would require the
  operator to approve each one, and requesting ``http`` for an echo plugin would
  (rightly) look suspicious in the WebUI.
"""

from __future__ import annotations

from soapbot.plugins.base import Plugin
from soapbot.plugins.context import CallerContext, PluginContext
from soapbot.security.principal import Role


class EchoPlugin(Plugin):
    async def setup(self, ctx: PluginContext) -> None:
        await super().setup(ctx)

        @ctx.command("echo", description="原样返回你给的内容", usage="/echo <文本>")
        async def echo(caller: CallerContext, args: list[str]) -> str:
            if not args:
                return "用法：/echo <文本>"
            # Length is capped by ``validate_args`` and again by the host on the way
            # out, so no manual truncation is needed here.
            return " ".join(args)

        @ctx.command(
            "whoami",
            description="显示你自己的身份（能力演示）",
            usage="/whoami",
        )
        async def whoami(caller: CallerContext, args: list[str]) -> str:
            return f"你是 {caller.display_name}（{caller.user_id}），角色：{caller.role}"

        @ctx.command(
            "purge-demo",
            description="演示需要管理员权限的插件命令",
            min_role=Role.ADMIN,
            usage="/purge-demo",
        )
        async def admin_only(caller: CallerContext, args: list[str]) -> str:
            # Reaching this line already proves the host authorised the caller: the
            # host refuses before invoking the handler when the role is too low.
            return "管理员命令已执行（仅演示）。"

        @ctx.tool(
            "echo_text",
            description="把给定文本原样返回，用于验证工具链路",
            parameters={
                "type": "object",
                "properties": {
                    "text": {"type": "string", "description": "要返回的文本"}
                },
                "required": ["text"],
            },
        )
        async def echo_tool(caller: CallerContext, arguments: dict) -> str:
            text = arguments.get("text", "")
            if not isinstance(text, str):
                return "错误：text 必须是字符串。"
            return text
