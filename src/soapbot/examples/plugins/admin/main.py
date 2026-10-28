"""Admin plugin: privileged operations, and how *not* to leak secrets.

Two demonstrations:

1. **Admin-gated command.** ``/pladmin`` declares ``min_role=ADMIN``. The host
   refuses for anyone below that before the handler runs.

2. **Encrypted storage.** ``/plsecret set <value>`` stores a secret through
   ``ctx.storage``, which is encrypted at rest. The read-back path returns only a
   *fingerprint* (length + last 2 chars), never the value — because a command that
   prints a stored credential is a credential-disclosure primitive, and group chat
   is the worst possible place to disclose one.

This is the pattern plugins should copy: store secrets, but never render them.
"""

from __future__ import annotations

from soapbot.plugins.base import Plugin
from soapbot.plugins.context import CallerContext, PluginContext
from soapbot.security.principal import Role

_SECRET_KEY = "demo_secret"


class AdminPlugin(Plugin):
    async def setup(self, ctx: PluginContext) -> None:
        await super().setup(ctx)

        @ctx.command(
            "pladmin",
            description="插件运行状态（管理员）",
            min_role=Role.ADMIN,
            usage="/pladmin",
        )
        async def status(caller: CallerContext, args: list[str]) -> str:
            api = ctx.exported_api()
            return (
                f"插件 {api['plugin']} 已加载；"
                f"命令 {len(api['commands'])} 个，工具 {len(api['tools'])} 个。"
            )

        @ctx.command(
            "plsecret",
            description="演示加密存储（管理员）：set/get/clear",
            min_role=Role.ADMIN,
            usage="/plsecret set <值> | /plsecret get | /plsecret clear",
        )
        async def secret_cmd(caller: CallerContext, args: list[str]) -> str:
            action = (args[0].lower() if args else "get")

            if action == "set":
                if len(args) < 2:
                    return "用法：/plsecret set <值>"
                value = " ".join(args[1:])
                if len(value) < 4:
                    return "值太短了（至少 4 个字符）。"
                ctx.storage.set(_SECRET_KEY, value)
                # Confirmation without disclosure: length only.
                return f"已加密保存（{len(value)} 个字符）。"

            if action == "clear":
                ctx.storage.delete(_SECRET_KEY)
                return "已清除。"

            stored = ctx.storage.get(_SECRET_KEY)
            if not stored:
                return "尚未设置。"
            # Deliberately not the value. Even an admin reading it in a group chat
            # leaks it to everyone in the group and to the chat log.
            tail = str(stored)[-2:]
            return f"已设置，长度 {len(str(stored))}，以 {tail!r} 结尾（不回显明文）。"
