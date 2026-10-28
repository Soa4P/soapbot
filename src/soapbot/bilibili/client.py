"""Bilibili public-metadata client.

Tiers
-----
``l1`` — unsigned public endpoints only (video detail, replies, user card). No
signature, no cookie, no login.
``l2`` — additionally signs requests with wbi so the space/search endpoints accept
them. Still no cookie and no login: the signature is a request-shape requirement on
public metadata, not an identity.

``l3`` is **not implemented and cannot be enabled**. L3 in the project's vocabulary
means "act as a logged-in browser", which requires a session cookie the project has no
business holding; the README says upgrading past L1 is the operator's own compliance
decision, so the code refuses to pretend the tier exists rather than accepting the
string and silently behaving like L2.

Egress rules, and why each one is here
--------------------------------------
* **Host allow-list.** Every request goes to a fixed pair of Bilibili hosts. A
  URL-shaped input from a chat message must never become the target of an outbound
  request, or the command turns the bot into an SSRF pivot into the operator's
  network.
* **No redirect following.** ``follow_redirects=False`` everywhere. A redirect is how
  an allow-listed host would otherwise hand control of the destination to whoever
  controls it.
* **Short links resolved by header inspection only.** ``b23.tv/xxxx`` is answered with
  a 302 whose ``Location`` is the real video URL. We read that header, validate that
  the destination is a Bilibili host, and never fetch the redirect target as a raw
  URL.
* **Local rate limit.** Two limits: a minimum interval between calls (so a burst of
  commands does not look like scraping) and a per-minute cap. The cap raises a
  user-visible message instead of queueing, because a chat command that silently waits
  two minutes is worse than one that says "slow down".
* **Fixed User-Agent.** Deliberately not rotated. Fingerprint randomisation exists to
  evade a platform's detection, which is precisely what the project's disclaimer says
  it does not do. Rotating it here would make the L1/L2 framing a lie.
"""

from __future__ import annotations

import asyncio
import logging
import re
import time
from urllib.parse import urlsplit

import httpx

from soapbot.bilibili.models import Comment, VideoInfo, VideoStat
from soapbot.bilibili.wbi import extract_key, mixin_key, sign
from soapbot.config import settings
from soapbot.security.ratelimit import SlidingWindowLimiter

logger = logging.getLogger(__name__)

API_HOST = "https://api.bilibili.com"
SHORT_HOSTS = frozenset({"b23.tv", "bili2233.cn"})
VIDEO_HOSTS = frozenset({"www.bilibili.com", "m.bilibili.com", "bilibili.com"})

#: Fixed, descriptive. See the module docstring for why this is not randomised.
USER_AGENT = (
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
    "(KHTML, like Gecko) Chrome/131.0.0.0 Safari/537.36 soapbot/bilibili-l1"
)

_BV_RE = re.compile(r"BV[0-9A-Za-z]{10}")
_AV_RE = re.compile(r"av(\d+)", re.IGNORECASE)
_SHORT_RE = re.compile(r"https?://(?:b23\.tv|bili2233\.cn)/[A-Za-z0-9]+", re.IGNORECASE)

#: How long a fetched wbi key pair is reused. The platform rotates the keys daily; a
#: six-hour cache means at most a handful of refreshes per day, and a stale key
#: degrades to a retry-once rather than a permanent failure.
WBI_TTL_SECONDS = 6 * 3600


class BilibiliError(RuntimeError):
    """User-presentable failure. The message is safe to send to a chat."""


class BilibiliNotFoundError(BilibiliError):
    pass


class BilibiliRiskControlError(BilibiliError):
    """The platform refused the request (``-412`` / ``-352``)."""


class BilibiliTierError(BilibiliError):
    """The configured tier does not allow this call."""


class BilibiliRateLimitedError(BilibiliError):
    pass


def parse_target(text: str) -> tuple[str, str]:
    """Normalise user input into ``("bv", "BV...")`` or ``("av", "12345")``.

    Accepts a bare id, a full video URL, or a short link. Raises rather than
    returning empty so the command can say *why* it did not understand the input.
    """
    raw = (text or "").strip()
    if not raw:
        raise BilibiliError("请提供视频号，例如 /bili BV1xx411c7mD")

    bv = _BV_RE.search(raw)
    if bv:
        return "bv", bv.group(0)

    av = _AV_RE.search(raw)
    if av:
        return "av", av.group(1)

    raise BilibiliError("没认出视频号：可用 BV 号、av 号或视频链接")


def is_short_link(text: str) -> bool:
    return bool(_SHORT_RE.match((text or "").strip()))


class BilibiliClient:
    """Read-only access to public video metadata."""

    def __init__(
        self,
        *,
        tier: str = "l1",
        timeout: float = 10.0,
        min_interval: float = 1.0,
        per_minute: int = 12,
        router=None,
    ) -> None:
        normalised = (tier or "l1").lower()
        if normalised == "l3":
            raise BilibiliTierError(
                "L3 档位未实现：它需要登录态 Cookie 才能工作，本项目不持有任何 B 站账号凭据。"
                "请使用 l1 或 l2。"
            )
        if normalised not in ("l1", "l2"):
            raise BilibiliTierError(f"未知档位 {tier!r}；可选 l1 / l2")
        self.tier = normalised
        self.timeout = float(timeout)
        self.min_interval = max(0.0, float(min_interval))
        self._limiter = SlidingWindowLimiter(limit=max(1, per_minute), window_seconds=60.0)
        self.router = router

        self._http: httpx.AsyncClient | None = None
        self._lock = asyncio.Lock()
        self._last_call = 0.0
        self._wbi_key = ""
        self._wbi_fetched_at = 0.0

        self.stats = {"calls": 0, "errors": 0, "risk_control": 0, "last_error": ""}

    # ------------------------------------------------------------------ lifecycle
    def _client(self) -> httpx.AsyncClient:
        if self._http is None:
            self._http = httpx.AsyncClient(
                timeout=self.timeout,
                follow_redirects=False,
                headers={"User-Agent": USER_AGENT, "Referer": "https://www.bilibili.com/"},
            )
        return self._http

    async def close(self) -> None:
        if self._http is not None:
            await self._http.aclose()
            self._http = None

    async def __aenter__(self) -> BilibiliClient:
        return self

    async def __aexit__(self, *exc_info) -> None:
        await self.close()

    # --------------------------------------------------------------- rate limiting
    async def _throttle(self) -> None:
        """Serialize calls and enforce both limits before touching the network."""
        limit = self._limiter.check("bilibili")
        if limit.limited:
            raise BilibiliRateLimitedError(
                f"B 站请求太频繁，请 {int(limit.retry_after) + 1} 秒后再试"
            )
        async with self._lock:
            wait = self.min_interval - (time.monotonic() - self._last_call)
            if wait > 0:
                await asyncio.sleep(wait)
            self._last_call = time.monotonic()

    # ------------------------------------------------------------------- transport
    async def _get_json(
        self, path: str, params: dict[str, object], *, signed: bool = False
    ) -> dict:
        if signed and self.tier != "l2":
            raise BilibiliTierError(
                f"该接口需要 L2（wbi 签名）档位，当前为 {self.tier.upper()}"
            )
        await self._throttle()

        query = dict(params)
        if signed:
            query = sign(query, await self._signing_key())

        url = f"{API_HOST}{path}"
        self.stats["calls"] += 1
        try:
            response = await self._client().get(url, params=query)
        except httpx.HTTPError as exc:
            self.stats["errors"] += 1
            self.stats["last_error"] = type(exc).__name__
            raise BilibiliError(f"B 站连接失败（{type(exc).__name__}），请稍后再试") from exc

        if response.status_code in (403, 412):
            self.stats["risk_control"] += 1
            raise BilibiliRiskControlError("B 站风控拦截了这次请求，请稍后再试")
        if response.status_code >= 400:
            self.stats["errors"] += 1
            raise BilibiliError(f"B 站返回 HTTP {response.status_code}")

        try:
            payload = response.json()
        except ValueError as exc:
            self.stats["errors"] += 1
            raise BilibiliError("B 站返回了无法解析的内容") from exc

        code = int(payload.get("code", 0))
        if code == 0:
            return payload.get("data") or {}

        self.stats["errors"] += 1
        self.stats["last_error"] = str(payload.get("message", code))
        if code in (-412, -352):
            self.stats["risk_control"] += 1
            raise BilibiliRiskControlError("B 站风控拦截了这次请求，请稍后再试")
        if code in (-404, 62002, 62004):
            raise BilibiliNotFoundError("视频不存在、已删除或不可见")
        if code in (-403, -799):
            raise BilibiliRateLimitedError("B 站要求降低请求频率，请稍后再试")
        raise BilibiliError(f"B 站接口错误（code={code}）")

    # ------------------------------------------------------------------ wbi signing
    async def _signing_key(self) -> str:
        now = time.time()
        if self._wbi_key and now - self._wbi_fetched_at < WBI_TTL_SECONDS:
            return self._wbi_key

        # ``nav`` answers ``-101 not logged in`` when anonymous, but still carries the
        # key pair in ``data``. Reading it through the normal error path would treat a
        # perfectly usable response as a failure.
        await self._throttle()
        try:
            response = await self._client().get(f"{API_HOST}/x/web-interface/nav")
            payload = response.json()
        except Exception as exc:
            raise BilibiliError(f"无法获取 wbi 签名密钥（{type(exc).__name__}）") from exc

        data = payload.get("data") or {}
        wbi = data.get("wbi_img") or {}
        img_key = extract_key(str(wbi.get("img_url", "")))
        sub_key = extract_key(str(wbi.get("sub_url", "")))
        if not img_key or not sub_key:
            raise BilibiliError("B 站未返回 wbi 密钥，可能已调整接口")

        self._wbi_key = mixin_key(img_key, sub_key)
        self._wbi_fetched_at = now
        logger.info("refreshed wbi signing key")
        return self._wbi_key

    # --------------------------------------------------------------------- reads
    async def resolve_short_link(self, url: str) -> str:
        """Turn ``b23.tv/xxxx`` into the BV id it points at, without following it."""
        parsed = urlsplit(url.strip())
        if parsed.hostname not in SHORT_HOSTS:
            raise BilibiliError("只接受 b23.tv / bili2233.cn 短链")

        await self._throttle()
        try:
            response = await self._client().get(url.strip())
        except httpx.HTTPError as exc:
            raise BilibiliError(f"短链解析失败（{type(exc).__name__}）") from exc

        location = response.headers.get("location", "")
        if not location:
            raise BilibiliError("短链没有返回跳转地址")
        # Validate the *destination* before extracting anything from it. Trusting the
        # Location blindly would let a compromised short link point us anywhere.
        host = urlsplit(location).hostname or ""
        if host not in VIDEO_HOSTS:
            raise BilibiliError("短链指向了非 B 站地址，已拒绝")
        kind, ident = parse_target(location)
        return f"{kind}:{ident}"

    async def video(self, target: str) -> VideoInfo:
        """Fetch video detail by BV/av id or URL."""
        kind, ident = parse_target(target)
        params = {"bvid": ident} if kind == "bv" else {"aid": ident}
        data = await self._get_json("/x/web-interface/view", params)

        owner = data.get("owner") or {}
        stat = data.get("stat") or {}
        bvid = str(data.get("bvid") or (ident if kind == "bv" else ""))
        return VideoInfo(
            bvid=bvid,
            aid=int(data.get("aid") or 0),
            title=str(data.get("title") or ""),
            description=str(data.get("desc") or ""),
            duration_seconds=int(data.get("duration") or 0),
            published_at=float(data.get("pubdate") or 0),
            author=str(owner.get("name") or ""),
            author_mid=int(owner.get("mid") or 0),
            cover_url=str(data.get("pic") or ""),
            category=str(data.get("tname") or ""),
            url=f"https://www.bilibili.com/video/{bvid}" if bvid else "",
            pages=max(1, len(data.get("pages") or [])),
            stat=VideoStat(
                view=int(stat.get("view") or 0),
                danmaku=int(stat.get("danmaku") or 0),
                reply=int(stat.get("reply") or 0),
                like=int(stat.get("like") or 0),
                coin=int(stat.get("coin") or 0),
                favorite=int(stat.get("favorite") or 0),
                share=int(stat.get("share") or 0),
            ),
        )

    async def comments(self, aid: int, *, limit: int = 10) -> list[Comment]:
        """Hot comments for a video. Public and unsigned (L1)."""
        if aid <= 0:
            return []
        data = await self._get_json(
            "/x/v2/reply",
            {"type": 1, "oid": aid, "sort": 2, "ps": max(1, min(limit, 20)), "pn": 1},
        )
        replies = data.get("replies") or []
        out: list[Comment] = []
        for item in replies[:limit]:
            member = item.get("member") or {}
            content = item.get("content") or {}
            out.append(
                Comment(
                    author=str(member.get("uname") or ""),
                    content=str(content.get("message") or "")[:300],
                    likes=int(item.get("like") or 0),
                )
            )
        return out

    async def user_videos(self, mid: int, *, limit: int = 10) -> list[dict]:
        """An uploader's recent videos. Requires L2 — the endpoint checks the signature."""
        data = await self._get_json(
            "/x/space/wbi/arc/search",
            {
                "mid": mid,
                "ps": max(1, min(limit, 30)),
                "pn": 1,
                "order": "pubdate",
                "platform": "web",
            },
            signed=True,
        )
        videos = ((data.get("list") or {}).get("vlist")) or []
        return [
            {
                "bvid": str(v.get("bvid") or ""),
                "title": str(v.get("title") or ""),
                "created": int(v.get("created") or 0),
                "play": int(v.get("play") or 0),
            }
            for v in videos[:limit]
        ]

    async def search(self, keyword: str, *, limit: int = 10) -> list[dict]:
        """Video search. Requires L2."""
        data = await self._get_json(
            "/x/web-interface/wbi/search/type",
            {"search_type": "video", "keyword": keyword, "page": 1},
            signed=True,
        )
        results = data.get("result") or []
        out: list[dict] = []
        for item in results[:limit]:
            title = str(item.get("title") or "")
            # Search results embed highlight markers; strip them so the reply is text.
            out.append(
                {
                    "bvid": str(item.get("bvid") or ""),
                    "title": re.sub(r"</?em[^>]*>", "", title),
                    "author": str(item.get("author") or ""),
                    "play": int(item.get("play") or 0),
                }
            )
        return out


def from_settings() -> BilibiliClient:
    """Build a client from configuration.

    Refuses when disabled: a client that exists while the feature is off would be
    reachable from code paths that forgot to check the flag, which is the same class of
    problem as a command registered but not authorised.
    """
    if not settings.enable_bilibili:
        raise BilibiliError("B 站功能未启用（SOAPBOT_ENABLE_BILIBILI=false）")
    return BilibiliClient(
        tier=settings.bilibili_tier,
        timeout=settings.bilibili_timeout_seconds,
        min_interval=settings.bilibili_min_interval_seconds,
        per_minute=settings.bilibili_rate_per_minute,
    )


__all__ = [
    "API_HOST",
    "USER_AGENT",
    "BilibiliClient",
    "BilibiliError",
    "BilibiliNotFoundError",
    "BilibiliRateLimitedError",
    "BilibiliRiskControlError",
    "BilibiliTierError",
    "from_settings",
    "is_short_link",
    "parse_target",
]
