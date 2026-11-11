"""Bilibili management view.

Three endpoints, all authenticated:

* status — is the feature on, which tier, how many calls/errors so far;
* preview — fetch a video's public metadata, so an operator can confirm the configured
  tier actually works before blaming the bot for a quiet group;
* impression — run the full "观后感" path once.

The last two hit the network on behalf of the caller. That is intentional: a tier
setting that has never been exercised is indistinguishable from a broken one, and the
first place an operator looks when a command "does nothing" is the log. Making it
explicit here means the log stays readable.
"""

from __future__ import annotations

import logging

from fastapi import APIRouter, Depends, HTTPException, Query, Request

from soapbot.api.auth import require_api_auth, require_role
from soapbot.api.errors import safe_detail
from soapbot.bilibili.client import (
    BilibiliError,
    BilibiliRateLimitedError,
    BilibiliRiskControlError,
    BilibiliTierError,
)
from soapbot.config import settings
from soapbot.security.principal import Role
from soapbot.security.ratelimit import SlidingWindowLimiter

logger = logging.getLogger(__name__)
router = APIRouter(
    prefix="/api/bilibili", tags=["bilibili"], dependencies=[Depends(require_role(Role.MEMBER))]
)

#: ``/impression`` runs the whole watch pipeline: fetch comments, then one model call.
#: Three per minute is generous for a human checking a tier, and stops the endpoint from
#: becoming an unmetered model proxy that sidesteps the chat quota entirely.
IMPRESSION_LIMIT = 3
IMPRESSION_WINDOW_SECONDS = 60.0
_impression_limiter = SlidingWindowLimiter(
    limit=IMPRESSION_LIMIT, window_seconds=IMPRESSION_WINDOW_SECONDS
)


def _client():
    from soapbot.app import get_runtime

    runtime = get_runtime()
    if runtime is None or runtime.bilibili is None:
        raise HTTPException(
            status_code=503,
            detail="Bilibili is not enabled (set SOAPBOT_ENABLE_BILIBILI=true)",
        )
    return runtime.bilibili


@router.get("")
async def bilibili_status(_: dict = Depends(require_api_auth)) -> dict:
    """Feature switch, tier and client counters."""
    from soapbot.app import get_runtime

    runtime = get_runtime()
    client = getattr(runtime, "bilibili", None) if runtime is not None else None
    return {
        "enabled": client is not None,
        "tier": getattr(client, "tier", settings.bilibili_tier),
        "configured_tier": settings.bilibili_tier,
        "stats": getattr(client, "stats", {}),
        "limits": {
            "min_interval_seconds": settings.bilibili_min_interval_seconds,
            "per_minute": settings.bilibili_rate_per_minute,
            "max_comments": settings.bilibili_max_comments,
        },
        "notice": (
            "仅获取公开元数据；L2 仅增加 wbi 请求签名，不使用登录态 Cookie。"
            "L3 未实现。启用即表示你已自行确认相关合规要求。"
        ),
    }


@router.get("/preview")
async def bilibili_preview(
    target: str = Query(..., min_length=1, max_length=200),
    _: dict = Depends(require_api_auth),
) -> dict:
    """Video metadata by BV/av/URL/short link."""
    client = _client()
    try:
        resolved = target
        from soapbot.bilibili.client import is_short_link

        if is_short_link(target):
            kind_and_id = await client.resolve_short_link(target)
            kind, ident = kind_and_id.split(":", 1)
            resolved = ident if kind == "bv" else f"av{ident}"
        video = await client.video(resolved)
        comments = await client.comments(video.aid, limit=settings.bilibili_max_comments)
    except BilibiliTierError as exc:
        raise HTTPException(status_code=400, detail=safe_detail(400, exc, "bilibili")) from exc
    except BilibiliRateLimitedError as exc:
        raise HTTPException(status_code=429, detail=safe_detail(429, exc, "bilibili")) from exc
    except BilibiliRiskControlError as exc:
        raise HTTPException(status_code=502, detail=safe_detail(502, exc, "bilibili")) from exc
    except BilibiliError as exc:
        raise HTTPException(status_code=400, detail=safe_detail(400, exc, "bilibili")) from exc

    return {"video": video.to_dict(), "comments": [c.to_dict() for c in comments]}


@router.get("/impression")
async def bilibili_impression(
    request: Request,
    target: str = Query(..., min_length=1, max_length=200),
    _: dict = Depends(require_api_auth),
) -> dict:
    """Full watch pipeline, including the model-generated impression.

    Rate-limited before anything else: an unbounded version of this endpoint is a way to
    spend the operator's model budget without going through the chat quota.
    """
    verdict = _impression_limiter.check(
        request.client.host if request.client else "-"
    )
    if not verdict.allowed:
        raise HTTPException(
            status_code=429,
            detail=(
                f"观后感调用过于频繁：每分钟最多 {IMPRESSION_LIMIT} 次，"
                f"请 {int(verdict.retry_after) + 1} 秒后重试"
            ),
            headers={"Retry-After": str(int(verdict.retry_after) + 1)},
        )
    client = _client()
    from soapbot.bilibili.watcher import VideoWatcher

    watcher = VideoWatcher(
        client,
        router=client.router,
        max_comments=settings.bilibili_max_comments,
    )
    try:
        report = await watcher.watch(target)
    except BilibiliTierError as exc:
        raise HTTPException(status_code=400, detail=safe_detail(400, exc, "bilibili")) from exc
    except BilibiliRateLimitedError as exc:
        raise HTTPException(status_code=429, detail=safe_detail(429, exc, "bilibili")) from exc
    except BilibiliRiskControlError as exc:
        raise HTTPException(status_code=502, detail=safe_detail(502, exc, "bilibili")) from exc
    except BilibiliError as exc:
        raise HTTPException(status_code=400, detail=safe_detail(400, exc, "bilibili")) from exc
    return report.to_dict()
