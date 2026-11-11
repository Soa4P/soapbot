"""Bilibili L3 plugin: logged-in reads through the vetted ``bilibili`` surface.

What makes this "L3" is the login state — watch history is only visible with the
account's own cookie. The architecture is the point, so it is stated once here:

* The plugin **never holds the credential**. ``ctx.bilibili`` sends a path to the
  host; the host injects ``SOAPBOT_BILI_COOKIE`` into a request pinned to
  ``api.bilibili.com`` and hands back JSON. The sandbox would refuse a ``Cookie``
  header from ``ctx.http`` anyway (see ``SafeHttpClient._sanitize_headers``), so
  the alternative to this surface was never "plugins hold the cookie safely".
* The plugin declares only what it uses: ``command``, ``bilibili``, ``storage``.
  No ``send`` (replies go through the command return path), no ``http`` (nothing
  here talks to a non-Bilibili host), no ``memory_read``.
* Everything it says in chat goes through the host's output sanitiser — this file
  does not sanitise, because doing it twice means the two copies drift.

Endpoints used (GET, both return ``{"code": 0, "data": ...}``):

- ``/x/web-interface/history/cursor`` — watch history, newest first (login state).
- ``/x/web-interface/view`` — public video metadata by ``bvid`` (no login state).
"""

from __future__ import annotations

import time

from soapbot.plugins.base import Plugin
from soapbot.plugins.context import CallerContext, PluginContext

HISTORY_PATH = "/x/web-interface/history/cursor"
VIEW_PATH = "/x/web-interface/view"
DEDUP_KEY = "seen_bvids"
DEDUP_LIMIT = 50


def _card(item: dict) -> str:
    """One history/history-entry line, built only from fields that exist."""
    title = str(item.get("title") or "（无标题）")
    bvid = str(item.get("bvid") or item.get("history", {}).get("bvid") or "")
    author = str(item.get("author_name") or item.get("author") or "")
    prefix = f"[{bvid}] " if bvid else ""
    suffix = f" · UP：{author}" if author else ""
    return f"{prefix}{title}{suffix}"


class BiliPlugin(Plugin):
    async def setup(self, ctx: PluginContext) -> None:
        await super().setup(ctx)

        @ctx.command("bili-history", description="读取 B 站登录账号的观看历史", usage="/bili-history [条数]")
        async def history(caller: CallerContext, args: list[str]) -> str:
            try:
                limit = max(1, min(int(args[0]) if args else 5, 20))
            except ValueError:
                return "用法：/bili-history [条数]"
            payload = await ctx.bilibili.get_json(
                HISTORY_PATH, params={"ps": str(limit), "type": "archive"}
            )
            if payload.get("code") != 0:
                return f"B 站返回错误码 {payload.get('code')}：{payload.get('message', '')}"
            items = (payload.get("data") or {}).get("items") or []
            if not items:
                return "这个账号最近没有观看记录。"
            lines = [_card(item) for item in items[:limit]]
            return "最近的观看历史：\n" + "\n".join(f"- {line}" for line in lines)

        @ctx.command("bili-look", description="按 bvid 取视频元数据，拼一段观前摘要", usage="/bili-look <bvid>")
        async def look(caller: CallerContext, args: list[str]) -> str:
            if not args or not args[0].startswith("BV"):
                return "用法：/bili-look <BV号>"
            bvid = args[0]
            payload = await ctx.bilibili.get_json(VIEW_PATH, params={"bvid": bvid})
            if payload.get("code") != 0:
                return f"没有找到 {bvid}（B 站错误码 {payload.get('code')}）"
            data = payload.get("data") or {}
            title = data.get("title", "")
            owner = (data.get("owner") or {}).get("name", "")
            stat = data.get("stat") or {}
            desc = str(data.get("desc") or "")[:200]
            await _remember(ctx, bvid, str(title))
            return "\n".join(
                filter(
                    None,
                    [
                        f"《{title}》",
                        f"UP：{owner} · 播放 {stat.get('view', 0)} · 弹幕 {stat.get('danmaku', 0)}",
                        f"简介：{desc}" if desc else "",
                        "（这条已记入 /bili-forget 可清空）",
                    ],
                )
            )

        @ctx.command("bili-forget", description="清空本插件记录的已看视频列表", usage="/bili-forget")
        async def forget(caller: CallerContext, args: list[str]) -> str:
            ctx.storage.delete(DEDUP_KEY)
            return "已清空。"


async def _remember(ctx: PluginContext, bvid: str, title: str) -> None:
    """Keep a small dedup list in the plugin's own encrypted storage.

    Titles only — no cookie material ever touches storage, and the list is capped
    so a heavy viewer cannot grow it without bound. ``ctx.storage`` is sync by
    design (in-memory backend, capability-checked at the method entry).
    """
    seen = ctx.storage.get(DEDUP_KEY) or {}
    if not isinstance(seen, dict):
        seen = {}
    seen[bvid] = {"title": title[:100], "at": time.time()}
    trimmed = dict(sorted(seen.items(), key=lambda kv: -kv[1]["at"])[:DEDUP_LIMIT])
    ctx.storage.set(DEDUP_KEY, trimmed)
