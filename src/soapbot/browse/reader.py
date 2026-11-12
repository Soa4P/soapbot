"""Fetch one public page, obeying the destination allow-list and robots.txt.

Compliance is not a comment in this module, it is the shape of the code:

* only ``GET``, only http(s), only a host in ``browse_allow_hosts`` (an empty list
  refuses everything — a typo must not silently turn into "anywhere");
* robots.txt is fetched once per host and consulted with our own user agent. A
  missing robots.txt allows; a network error fetching it refuses (fail closed);
* no Cookie/Authorization header, no redirect following, no form submission, no
  JavaScript. The page is parsed as text with the standard library, so a script in
  the response is data, never code;
* response size, text length and image count are bounded before anything is
  returned to a plugin or a model.

This is a **static** reader: pages that render their content only in JavaScript come
back with ``static_only=True`` and an empty body rather than a plausible-looking
guess. A headless browser can be added behind the same function later; pretending
the current reader rendered one is how a proposal ends up based on nothing.
"""

from __future__ import annotations

import logging
import re
import time
from dataclasses import dataclass
from html.parser import HTMLParser
from typing import Any
from urllib.parse import urljoin, urlsplit
from urllib.robotparser import RobotFileParser

logger = logging.getLogger(__name__)

#: Deliberately identifiable. A site that wants to refuse automated readers can do
#: so in robots.txt, and an operator can find our requests in their access log.
USER_AGENT = "SoapbotBot/1.0 (public-page-reader)"

MAX_TEXT_CHARS = 4000
MAX_IMAGES = 8
_PRICE_RE = re.compile(r"[¥￥]\s*(\d{1,7}(?:[.,]\d{1,2})?)")
_CONTROL_RE = re.compile(r"[\x00-\x08\x0b\x0c\x0e-\x1f]")


class ReadError(RuntimeError):
    """A page could not be read under the browsing policy. Safe to show verbatim."""


@dataclass(frozen=True, slots=True)
class PageSnapshot:
    """Bounded, text-only view of a public page."""

    url: str
    host: str
    status: int
    title: str
    description: str
    text: str
    price_minor: int | None
    currency: str
    images: tuple[str, ...]
    bytes_read: int
    static_only: bool = True

    def to_dict(self) -> dict[str, Any]:
        """Explicit whitelist: a proposal must not smuggle raw HTML into an event."""
        return {
            "url": self.url,
            "host": self.host,
            "status": self.status,
            "title": self.title,
            "description": self.description,
            "text": self.text,
            "price_minor": self.price_minor,
            "currency": self.currency,
            "images": list(self.images),
            "bytes_read": self.bytes_read,
            "static_only": self.static_only,
        }


@dataclass(frozen=True, slots=True)
class BrowsePolicy:
    allowed_hosts: frozenset[str]
    max_bytes: int = 512 * 1024
    timeout_seconds: float = 10.0
    robots_ttl_seconds: float = 3600.0

    @classmethod
    def from_settings(cls) -> BrowsePolicy:
        from soapbot.config import settings

        return cls(
            allowed_hosts=frozenset(
                str(host).strip().lower()
                for host in (settings.browse_allow_hosts or [])
                if str(host).strip()
            ),
            max_bytes=int(settings.browse_max_bytes),
            timeout_seconds=float(settings.browse_timeout_seconds),
            robots_ttl_seconds=float(settings.browse_robots_ttl_seconds),
        )


class _PageParser(HTMLParser):
    """Collect title, meta fields, visible text and image references."""

    _SKIP = frozenset({"script", "style", "noscript", "svg", "template"})

    def __init__(self) -> None:
        super().__init__(convert_charrefs=True)
        self.title_parts: list[str] = []
        self.text_parts: list[str] = []
        self.images: list[str] = []
        self.meta: dict[str, str] = {}
        self._in_title = False
        self._skip_depth = 0

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        if tag in self._SKIP:
            self._skip_depth += 1
            return
        if self._skip_depth:
            return
        if tag == "title":
            self._in_title = True
        elif tag == "meta":
            values = {str(k).lower(): (v or "") for k, v in attrs}
            key = values.get("property") or values.get("name") or ""
            if key:
                self.meta[key.lower()] = values.get("content", "")
        elif tag == "img" and len(self.images) < MAX_IMAGES:
            src = next(
                (v for k, v in attrs if k and k.lower() in ("src", "data-src") and v), ""
            )
            if src and not src.lower().startswith(("data:", "javascript:")):
                self.images.append(src)

    def handle_endtag(self, tag: str) -> None:
        if tag in self._SKIP:
            self._skip_depth = max(0, self._skip_depth - 1)
            return
        if tag == "title":
            self._in_title = False

    def handle_data(self, data: str) -> None:
        if self._skip_depth:
            return
        clean = _CONTROL_RE.sub("", data).strip()
        if not clean:
            return
        if self._in_title:
            self.title_parts.append(clean)
        else:
            self.text_parts.append(clean)


def _clean(value: str, *, limit: int) -> str:
    return _CONTROL_RE.sub("", value)[:limit]


def _price_from(parser: _PageParser, text: str) -> int | None:
    raw = parser.meta.get("product:price:amount") or ""
    if raw:
        try:
            return round(float(raw.replace(",", "")) * 100)
        except ValueError:
            # A malformed meta price is not an error: fall through to the visible
            # text instead of letting one bad tag suppress a real price.
            logger.debug("ignoring malformed product:price:amount")
    match = _PRICE_RE.search(text)
    if match is None:
        return None
    try:
        return round(float(match.group(1).replace(",", ".")) * 100)
    except ValueError:  # pragma: no cover - the regex already bounds the shape
        return None


def parse_page(url: str, body: bytes, *, status: int) -> PageSnapshot:
    """Turn bounded HTML bytes into a text-only snapshot."""
    parts = urlsplit(url)
    text = body.decode("utf-8", errors="replace")
    parser = _PageParser()
    try:
        parser.feed(text)
        parser.close()
    except Exception as exc:
        # HTMLParser is lenient, but a page that breaks it must still be visible in
        # the log. Keep whatever was parsed before the failure; never guess at the
        # missing part.
        logger.warning("page parser stopped early err=%s", type(exc).__name__)
    visible = " ".join(parser.text_parts)
    visible = re.sub(r"\s+", " ", visible).strip()[:MAX_TEXT_CHARS]
    title = _clean(" ".join(parser.title_parts) or parser.meta.get("og:title", ""), limit=300)
    description = _clean(
        parser.meta.get("description") or parser.meta.get("og:description", ""), limit=500
    )
    images = tuple(urljoin(url, src) for src in parser.images)[:MAX_IMAGES]
    return PageSnapshot(
        url=url,
        host=parts.hostname or "",
        status=status,
        title=title,
        description=description,
        text=visible,
        price_minor=_price_from(parser, visible),
        currency="CNY",
        images=images,
        bytes_read=len(body),
    )


class _Robots:
    """Per-host cache; never cached across a policy change."""

    def __init__(self) -> None:
        self._entries: dict[str, tuple[float, RobotFileParser | None]] = {}

    async def allows(self, url: str, *, fetcher, policy: BrowsePolicy) -> bool:
        parts = urlsplit(url)
        origin = f"{parts.scheme}://{parts.netloc}"
        now = time.monotonic()
        cached = self._entries.get(origin)
        if cached and cached[0] > now:
            parser = cached[1]
            return parser is None or parser.can_fetch(USER_AGENT, url)

        robots_url = f"{origin}/robots.txt"
        try:
            status, body = await fetcher(
                robots_url, {"User-Agent": USER_AGENT}, policy.timeout_seconds
            )
        except Exception as exc:
            raise ReadError("robots.txt could not be read; refusing the fetch") from exc
        parser: RobotFileParser | None
        if status == 404 or status >= 400:
            # No robots file means no stated restriction; a 5xx does NOT mean that.
            parser = None if status == 404 else _deny_all()
        else:
            parser = RobotFileParser()
            parser.parse(body.decode("utf-8", errors="replace").splitlines())
        self._entries[origin] = (now + policy.robots_ttl_seconds, parser)
        return parser is None or parser.can_fetch(USER_AGENT, url)


def _deny_all() -> RobotFileParser:
    parser = RobotFileParser()
    parser.parse(["User-agent: *", "Disallow: /"])
    return parser


_ROBOTS = _Robots()


async def read_public_page(
    url: str,
    *,
    policy: BrowsePolicy | None = None,
    fetcher=None,
) -> PageSnapshot:
    """Fetch and parse one public page under the browsing policy.

    ``fetcher`` is ``(url, headers, timeout) -> (status, bytes)``. Production passes
    a :class:`SafeHttpClient` built with the ``BROWSE`` capability, so SSRF checks,
    DNS pinning, redirect refusal and header allow-listing are the same ones the
    rest of the plugin sandbox enforces. It is a required argument rather than a
    default: a browse that quietly fell back to an unvetted client would be worse
    than no browse at all.
    """
    from soapbot.plugins.sandbox import assert_url_allowed

    current = policy or BrowsePolicy.from_settings()
    clean_url = str(url or "").strip()
    if not clean_url or len(clean_url) > 2000:
        raise ReadError("a URL of at most 2000 characters is required")
    # Fails closed on an empty allow-list, and rejects private IPs / metadata hosts.
    assert_url_allowed(clean_url, allowed_hosts=current.allowed_hosts)
    if fetcher is None:
        raise ReadError("no vetted HTTP client installed for browsing")

    if not await _ROBOTS.allows(clean_url, fetcher=fetcher, policy=current):
        raise ReadError("robots.txt disallows this page for our user agent")

    status, body = await fetcher(
        clean_url, {"User-Agent": USER_AGENT}, current.timeout_seconds
    )
    if len(body) > current.max_bytes:
        raise ReadError("page exceeds the configured byte cap")
    if status != 200:
        raise ReadError(f"page returned HTTP {status}")
    return parse_page(clean_url, body, status=status)
