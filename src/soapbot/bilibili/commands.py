"""``/bili`` command: video metadata and a written impression.

Shape follows the budget module deliberately: the command layer is a small object
handed to ``CommandStage`` as an optional collaborator, ``None`` meaning "this
deployment has Bilibili off". Nothing about the network client leaks into the memory
package, and a deployment that never enables the feature pays nothing for it.

Why a per-session rate limit and not a global one
-------------------------------------------------
The upstream limits are already enforced in the client. What this adds is fairness:
one group issuing twenty lookups should not exhaust the budget for every other group
for the rest of the minute. Keying on the session gives each conversation its own
small allowance.
"""

from __future__ import annotations

import logging

from soapbot.bilibili.client import (
    BilibiliError,
    BilibiliRateLimitedError,
    BilibiliRiskControlError,
    BilibiliTierError,
)
from soapbot.bilibili.models import WatchReport
from soapbot.bilibili.watcher import VideoWatcher
from soapbot.security.audit import AuditLog, get_audit_log
from soapbot.security.ratelimit import SlidingWindowLimiter

logger = logging.getLogger(__name__)

_WATCH_WORDS = frozenset({"watch", "观后感", "感想", "评一下"})


class BilibiliCommands:
    """Handles ``/bili``. Authorisation is done by ``CommandStage`` before entry."""

    USAGE = (
        "用法：\n"
        "/bili <BV号 | av号 | 链接>　— 查看视频信息\n"
        "/bili 观后感 <BV号 | av号 | 链接>　— 生成一段基于公开信息的观后感"
    )

    def __init__(
        self,
        watcher: VideoWatcher,
        *,
        audit: AuditLog | None = None,
        per_session_limit: int = 4,
        window_seconds: float = 300.0,
    ) -> None:
        self.watcher = watcher
        self.audit = audit or get_audit_log()
        self._limiter = SlidingWindowLimiter(
            limit=max(1, per_session_limit), window_seconds=window_seconds
        )

    async def handle(self, ctx, args: list[str]) -> str:
        session_key = getattr(ctx.event, "session_key", "") or "unknown"
        trace_id = getattr(ctx.event, "trace_id", "") or ""
        limit = self._limiter.check(session_key)
        if limit.limited:
            self.audit.record(
                kind="command",
                action="cmd:bili",
                outcome="deny",
                principal=ctx.extras.get("principal"),
                detail=f"per-session limit reached session={session_key}",
                trace_id=trace_id,
            )
            return f"B 站查询太频繁了，请 {int(limit.retry_after) + 1} 秒后再试。"

        words = [a for a in args if a.strip()]
        if not words:
            return self.USAGE

        wants_impression = words[0].lower() in _WATCH_WORDS
        target = " ".join(words[1:] if wants_impression else words).strip()
        if not target:
            return self.USAGE

        try:
            if wants_impression:
                report = await self.watcher.watch(target)
                return self.render_report(report)
            video = await self.watcher.client.video(target)
            return self.render_video(video)
        except BilibiliTierError as exc:
            return str(exc)
        except BilibiliRateLimitedError as exc:
            return str(exc)
        except BilibiliRiskControlError as exc:
            # Recorded as a security event on purpose: a sustained stream of these
            # means someone is hammering the command, and the operator should see it
            # rather than read it as a bug in the bot.
            self.audit.record(
                kind="command",
                action="cmd:bili",
                outcome="block",
                principal=ctx.extras.get("principal"),
                detail=f"risk control session={session_key}",
                trace_id=trace_id,
            )
            return str(exc)
        except BilibiliError as exc:
            return str(exc)
        except Exception as exc:
            # Never surface a raw exception: it can carry the request URL (and thus
            # the target) or an internal traceback.
            logger.exception("bilibili command failed")
            return f"B 站查询失败（{type(exc).__name__}），请稍后再试。"

    # ------------------------------------------------------------------ rendering
    def render_video(self, video) -> str:
        lines = [
            f"《{video.title}》",
            f"UP 主：{video.author}　分区：{video.category or '未知'}　时长：{video.duration_text}",
            f"播放 {_human(video.stat.view)}　点赞 {_human(video.stat.like)}　"
            f"评论 {_human(video.stat.reply)}　收藏 {_human(video.stat.favorite)}",
        ]
        if video.description:
            lines.append(f"简介：{video.description[:180]}")
        if video.url:
            lines.append(video.url)
        return "\n".join(lines)

    def render_report(self, report: WatchReport) -> str:
        header = self.render_video(report.video)
        note = ""
        if report.degraded == "no_model":
            note = "\n（未配置模型，以下只是对公开信息的整理，不是观后感。）"
        elif report.degraded:
            note = "\n（模型调用失败，以下只是对公开信息的整理。）"

        body = report.impression or "（暂无内容）"
        label = "\n观后感（基于标题、简介与热评推断，并非真正观看）：" if not note else "\n信息整理："
        return f"{header}{label}\n{body}{note}"


def _human(value: int) -> str:
    if value >= 100_000_000:
        return f"{value / 100_000_000:.1f}亿"
    if value >= 10_000:
        return f"{value / 10_000:.1f}万"
    return str(value)


__all__ = ["BilibiliCommands"]
