"""Read-only observer for the host-computed warmth scalar.

Adapted from the *question* dsh-longing asks ("is this conversation still warm
when nobody talks?"), not from its state machine. In this repository the number
is computed by ``ai/autonomy.py`` from delivered replies, never written by a
model, and a plugin can only read it through ``ctx.session``. Deliberately no
``send``, ``cron`` or ``storage`` capability: an observer that could also speak
or persist its own mood would be a different (and much less safe) plugin.
"""

from __future__ import annotations

from soapbot.plugins.base import Plugin
from soapbot.plugins.context import CallerContext, PluginContext

DEFAULT_THRESHOLD = 0.6


class WarmthObserverPlugin(Plugin):
    async def setup(self, ctx: PluginContext) -> None:
        await super().setup(ctx)

        @ctx.command(
            "warmth",
            description="查看当前会话的宿主温度（只读）",
            usage="/warmth [阈值 0..1]",
        )
        async def warmth(caller: CallerContext, args: list[str]) -> str:
            try:
                threshold = float(args[0]) if args else DEFAULT_THRESHOLD
            except ValueError:
                return "用法：/warmth [阈值 0..1]"
            if not 0.0 <= threshold <= 1.0:
                return "阈值必须在 0 到 1 之间。"
            value = float(getattr(ctx.session, "warmth", 0.0))
            state = "够热" if value >= threshold else "偏冷"
            return (
                f"当前会话温度 {value:.2f}（阈值 {threshold:.2f}，{state}）。\n"
                "这个数字由宿主按成功归档的回复数与空闲时长算出，插件不能改；"
                "本插件也不会据此主动发言。"
            )
