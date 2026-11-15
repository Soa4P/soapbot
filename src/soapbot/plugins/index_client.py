"""Read-only client for the community plugin index.

What this module decides
------------------------
The index answers two questions — "what exists" (``plugins.json``) and "what exactly
was published per version" (``plugin_versions.json``, the digest/download anchor). It
is still not a trust source for *what a plugin can do*: installing from it is now
one click, but the chain is

    索引决定「有什么」 → digest 校验决定「拿到的是不是声明的那个」
    → 审批屏（人勾能力清单）决定「能做什么」

The old stance ("nothing here is installable in one click") predates per-version
digests: back then, compromising the index *was* remote code execution. With a
verified digest, a compromised index degrades to "the download doesn't match what
was published, so it is refused" — a denial of service, not an execution. Approval
stays exactly where it was.

Fetch guards (unchanged): plain ``GET``, no credentials, no redirects to other hosts;
size-capped before parsing; depth guard like every other untrusted JSON; failures are
reported as degraded states, never exceptions that reach the panel as a 500; blocked
versions are *merged* with the local list, never replaced by it.
"""

from __future__ import annotations

import json
import logging
import time
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

import httpx

from soapbot.core.jsonguard import JsonTooDeepError, check_depth
from soapbot.plugins.manifest import block_key

logger = logging.getLogger(__name__)

#: Refuse to parse anything larger. A plugin index is a few hundred entries; a 20 MB
#: response is either a mistake or an attempt to make the panel allocate on demand.
MAX_INDEX_BYTES = 4 * 1024 * 1024

#: Depth cap for the index document. Matches the global default; stated here because the
#: index is fetched from a host nobody in this repository controls.
MAX_INDEX_DEPTH = 16

#: The local blocklist ships inside the package, so it works with no network at all.
LOCAL_BLOCKLIST = Path(__file__).with_name("blocked_versions.json")


@dataclass(slots=True)
class IndexEntry:
    """One plugin as the index describes it. Every field is a *claim*, not a fact."""

    name: str
    versions: tuple[str, ...] = ()
    summary: str = ""
    author: str = ""
    homepage: str = ""
    repository: str = ""
    latest: str = ""

    def to_dict(self) -> dict[str, Any]:
        return {
            "name": self.name,
            "versions": list(self.versions),
            "summary": self.summary,
            "author": self.author,
            "homepage": self.homepage,
            "repository": self.repository,
            "latest": self.latest,
        }


@dataclass(slots=True)
class IndexSnapshot:
    """The result of one fetch attempt, including the failure case.

    ``available`` is the field the panel branches on. Everything else is optional, so a
    caller never has to distinguish "empty index" from "fetch failed" by inspecting
    strings.
    """

    available: bool
    entries: tuple[IndexEntry, ...] = ()
    blocked: dict[str, str] = field(default_factory=dict)
    """``"name@version" -> reason``. Merged local + remote."""
    versions: dict[str, dict[str, dict[str, str]]] = field(default_factory=dict)
    """``name -> version -> {digest, download, released_at}`` from
    ``plugin_versions.json`` (fetched alongside the catalogue). This is what makes
    one-click install possible: the digest is the anchor that turns "the index says
    this exists" into "what you download is byte-for-byte what was published".
    Empty when the versions file is missing or broken — one-click install refuses
    without it, discovery still works."""
    source: str = ""
    fetched_at: float = 0.0
    error: str = ""
    warnings: tuple[str, ...] = ()
    """Degraded but usable states. Kept separate from ``error``: a broken *local*
    blocklist does not mean the catalogue could not be fetched, and collapsing the two
    would show "index unavailable" while listing plugins normally."""

    def to_dict(self) -> dict[str, Any]:
        return {
            "available": self.available,
            "entries": [e.to_dict() for e in self.entries],
            "blocked": dict(self.blocked),
            "versions": self.versions,
            "source": self.source,
            "fetched_at": self.fetched_at,
            "error": self.error,
            "warnings": list(self.warnings),
        }

    def blocked_reason(self, name: str, version: str) -> str:
        """Why this exact version must not be installed, or ``""``.

        Uses the canonical key so the answer matches what the installer enforces.
        A literal lookup here would report "not blocked" for a version the installer
        refuses — the panel would say a plugin is fine and the upload would then fail
        with no visible reason.
        """
        return self.blocked.get(block_key(name, version), "")

    def version_meta(self, name: str, version: str) -> dict[str, str] | None:
        """The published metadata for one version, or ``None``.

        Returns ``None`` when the version is unknown **or** its digest is a
        placeholder: a draft entry must not be one-click installable, and the caller
        cannot tell the two cases apart in a way that would matter.
        """
        meta = self.versions.get(name, {}).get(version)
        if not isinstance(meta, dict):
            return None
        digest = str(meta.get("digest", ""))
        download = str(meta.get("download", ""))
        if not digest.startswith("sha256:") or digest == "sha256:" + "0" * 64:
            return None
        if not download.startswith("https://"):
            return None
        return meta


def _text(value: Any, limit: int = 300) -> str:
    """Coerce an index field to a displayable string.

    Control characters are stripped rather than rejected: the index is third-party data
    rendered into a browser, and a newline in a summary is a formatting problem, not a
    reason to discard the whole catalogue. Length is capped so one entry cannot push the
    rest off the page.
    """
    if not isinstance(value, str):
        return ""
    cleaned = "".join(ch for ch in value if ch >= " " or ch in "\t")
    return cleaned.strip()[:limit]


def _parse_entries(raw: Any) -> tuple[IndexEntry, ...]:
    """Parse the ``plugins`` array, skipping malformed entries.

    Skipping rather than failing is deliberate: one bad entry in a community file should
    cost that entry, not the entire catalogue. A *structurally* wrong document (not a
    dict, no list) is a different matter and returns empty, which the caller reports as
    an unusable index.
    """
    if not isinstance(raw, list):
        return ()
    entries: list[IndexEntry] = []
    for item in raw:
        if not isinstance(item, dict):
            continue
        name = _text(item.get("name"), 64)
        if not name:
            continue
        versions_raw = item.get("versions")
        versions: tuple[str, ...] = ()
        if isinstance(versions_raw, list):
            versions = tuple(
                v for v in (_text(x, 32) for x in versions_raw) if v
            )
        entries.append(
            IndexEntry(
                name=name,
                versions=versions,
                summary=_text(item.get("summary") or item.get("description")),
                author=_text(item.get("author"), 80),
                homepage=_text(item.get("homepage")),
                repository=_text(item.get("repository")),
                latest=_text(item.get("latest"), 32) or (versions[-1] if versions else ""),
            )
        )
    return tuple(entries)


def _parse_blocked(raw: Any) -> dict[str, str]:
    """Parse ``[{"name":…, "version":…, "reason":…}]`` into ``name@version -> reason``.

    Keys go through :func:`block_key`, so a remote entry for ``1.0.0`` also covers a
    package that spells the same release ``1.0``. The index is third-party data and
    the version string in it is a claim; normalising on both sides is what makes the
    two spellings the same block instead of two different ones.
    """
    if not isinstance(raw, list):
        return {}
    blocked: dict[str, str] = {}
    for item in raw:
        if not isinstance(item, dict):
            continue
        name = _text(item.get("name"), 64)
        version = _text(item.get("version"), 32)
        if not name or not version:
            continue
        blocked[block_key(name, version)] = _text(item.get("reason"), 300) or "已被索引标记为不安全"
    return blocked


def load_local_blocklist_checked(path: Path | None = None) -> tuple[dict[str, str], str]:
    """Read the shipped blocklist, returning the blocks *and* why none were loaded.

    A missing or unreadable file yields an empty dict, not an exception: the blocklist
    is a safety net, and a deployment whose wheel lost the file should still start.
    But returning only ``{}`` made that failure invisible at every layer above a log
    line — the panel and the install endpoint both saw "nothing is blocked", which is
    indistinguishable from a clean install. The caller now gets a reason to surface.
    """
    target = path or LOCAL_BLOCKLIST
    try:
        data = json.loads(target.read_text(encoding="utf-8"))
    except FileNotFoundError:
        logger.warning("plugin blocklist missing at %s; no local blocks active", target)
        return {}, "本地封禁表缺失，随包封禁未生效"
    except (OSError, json.JSONDecodeError) as exc:
        logger.warning("plugin blocklist unreadable (%s); no local blocks active", type(exc).__name__)
        return {}, f"本地封禁表无法读取（{type(exc).__name__}），随包封禁未生效"
    return _parse_blocked(data.get("blocked") if isinstance(data, dict) else None), ""


def load_local_blocklist(path: Path | None = None) -> dict[str, str]:
    """Convenience wrapper for callers that only need the blocks."""
    blocked, _ = load_local_blocklist_checked(path)
    return blocked


class IndexClient:
    """Fetches and caches the community index.

    One instance lives on the plugin manager. The cache is per-process and time-based;
    there is no persistence, because a stale index on disk is a claim about the world
    that nobody re-verified.
    """

    def __init__(
        self,
        url: str = "",
        *,
        timeout: float = 5.0,
        ttl: float = 900.0,
        blocklist_path: Path | None = None,
        transport: httpx.AsyncBaseTransport | None = None,
    ) -> None:
        self.url = url.strip()
        self.timeout = timeout
        self.ttl = ttl
        self._blocklist_path = blocklist_path
        self._transport = transport
        self._cached: IndexSnapshot | None = None
        self._local_blocked: dict[str, str] | None = None
        self._local_blocklist_error = ""

    @property
    def local_blocked(self) -> dict[str, str]:
        """Local blocks, read once per process.

        Cached because the file is shipped with the package and cannot change while the
        process runs; re-reading it per request would be a syscall per plugin page for a
        value that is constant.
        """
        if self._local_blocked is None:
            self._local_blocked, self._local_blocklist_error = load_local_blocklist_checked(
                self._blocklist_path
            )
        return self._local_blocked

    def _stale(self) -> bool:
        if self._cached is None:
            return True
        return (time.time() - self._cached.fetched_at) > self.ttl

    async def snapshot(self, *, force: bool = False) -> IndexSnapshot:
        """The current index, fetching if the cache is cold or stale.

        Never raises. Every failure becomes ``available=False`` with a short reason, so
        the caller can render the plugin page regardless of the network.
        """
        if not force and not self._stale() and self._cached is not None:
            return self._cached

        if not self.url:
            # Not an error: an operator who has not configured an index is the default
            # state, and the panel should say "no index configured" rather than "failed".
            snapshot = IndexSnapshot(
                available=False,
                blocked=dict(self.local_blocked),
                error="",
                source="",
            )
            self._cached = self._with_warnings(snapshot)
            return self._cached

        snapshot = await self._fetch()
        previous = self._cached
        if previous is not None and not snapshot.available:
            # A failed refresh must not lift a block learned from the last good fetch.
            # `_fetch` starts from the local list only, so caching this snapshot as-is
            # used to make every remote block disappear on the first timeout or 503 —
            # exactly what the caller in api/plugins.py says must not happen. Merging
            # is safe because both maps only ever ADD blocks; a remote index can never
            # remove one.
            merged = dict(previous.blocked)
            merged.update(snapshot.blocked)
            snapshot.blocked = merged
        self._cached = self._with_warnings(snapshot)
        return self._cached

    def _with_warnings(self, snapshot: IndexSnapshot) -> IndexSnapshot:
        """Attach degraded-state notes that the panel can render without lying."""
        _ = self.local_blocked  # force the one-time read that sets the error
        warnings = list(snapshot.warnings)
        if self._local_blocklist_error:
            warnings.append(self._local_blocklist_error)
        snapshot.warnings = tuple(warnings)
        return snapshot

    async def _fetch(self) -> IndexSnapshot:
        blocked = dict(self.local_blocked)
        try:
            async with httpx.AsyncClient(
                timeout=self.timeout,
                follow_redirects=False,
                transport=self._transport,
            ) as client:
                response = await client.get(
                    self.url,
                    headers={"accept": "application/json", "user-agent": "soapbot-plugin-index"},
                )
        except httpx.TimeoutException:
            logger.warning("plugin index timed out after %.1fs", self.timeout)
            return IndexSnapshot(available=False, blocked=blocked, source=self.url, error="索引请求超时")
        except httpx.HTTPError as exc:
            logger.warning("plugin index unreachable: %s", type(exc).__name__)
            return IndexSnapshot(
                available=False, blocked=blocked, source=self.url, error="索引不可达"
            )

        if response.status_code != 200:
            logger.warning("plugin index returned %d", response.status_code)
            return IndexSnapshot(
                available=False,
                blocked=blocked,
                source=self.url,
                error=f"索引返回 {response.status_code}",
            )

        body = response.content
        if len(body) > MAX_INDEX_BYTES:
            logger.warning("plugin index too large: %d bytes", len(body))
            return IndexSnapshot(
                available=False, blocked=blocked, source=self.url, error="索引体积超出上限"
            )

        # Depth is checked on the *bytes*, before the parser sees them: `json.loads`
        # recurses, and a deeply nested document raises RecursionError — a RuntimeError,
        # not the JSONDecodeError the handler below catches. See core/jsonguard.py.
        try:
            check_depth(body, limit=MAX_INDEX_DEPTH)
        except JsonTooDeepError:
            return IndexSnapshot(
                available=False, blocked=blocked, source=self.url, error="索引嵌套过深"
            )

        try:
            payload = json.loads(body)
        except (json.JSONDecodeError, UnicodeDecodeError):
            return IndexSnapshot(
                available=False, blocked=blocked, source=self.url, error="索引不是合法 JSON"
            )

        if not isinstance(payload, dict):
            return IndexSnapshot(
                available=False, blocked=blocked, source=self.url, error="索引结构不正确"
            )

        entries = _parse_entries(payload.get("plugins"))
        # Remote blocks are *added* to the local set. `update` after the local dict is
        # already populated means a remote entry can overwrite the reason for a version
        # both lists block, but can never remove a local block outright — removal would
        # require the local key to be absent, which it is not.
        blocked.update(_parse_blocked(payload.get("blocked_versions")))

        versions, versions_warning = await self._fetch_versions()
        warnings = tuple(w for w in (versions_warning,) if w)

        logger.info(
            "plugin index loaded: %d entries, %d blocked, %d versioned",
            len(entries),
            len(blocked),
            len(versions),
        )
        return IndexSnapshot(
            available=True,
            entries=entries,
            blocked=blocked,
            versions=versions,
            source=self.url,
            fetched_at=time.time(),
            warnings=warnings,
        )

    def _versions_url(self) -> str:
        """``plugin_versions.json`` next to the catalogue (same directory, same origin).

        The catalogue file answers "what exists"; this one answers "what exactly was
        published per version" (digest/download). Same-directory derivation means an
        operator who points the index at their own fork gets their own versions file —
        there is no hidden second source.
        """
        base = self.url.rsplit("/", 1)[0]
        return f"{base}/plugin_versions.json"

    async def _fetch_versions(self) -> tuple[dict[str, dict[str, dict[str, str]]], str]:
        """Fetch the per-version metadata. Missing or broken → empty + a warning:
        discovery keeps working, one-click install refuses (it refuses *any* version
        without a real digest anyway)."""
        url = self._versions_url()
        try:
            async with httpx.AsyncClient(
                timeout=self.timeout,
                follow_redirects=False,
                transport=self._transport,
            ) as client:
                response = await client.get(
                    url, headers={"accept": "application/json", "user-agent": "soapbot-plugin-index"}
                )
        except httpx.HTTPError:
            return {}, "版本元数据不可达，一键安装暂不可用"
        if response.status_code != 200:
            return {}, f"版本元数据返回 {response.status_code}，一键安装暂不可用"
        body = response.content
        if len(body) > MAX_INDEX_BYTES:
            return {}, "版本元数据体积超出上限，一键安装暂不可用"
        try:
            check_depth(body, limit=MAX_INDEX_DEPTH)
            payload = json.loads(body)
        except (JsonTooDeepError, json.JSONDecodeError, UnicodeDecodeError):
            return {}, "版本元数据不是合法 JSON，一键安装暂不可用"
        versions_map = payload.get("versions") if isinstance(payload, dict) else None
        if not isinstance(versions_map, dict):
            return {}, "版本元数据结构不正确，一键安装暂不可用"

        out: dict[str, dict[str, dict[str, str]]] = {}
        for name, entries in versions_map.items():
            if not isinstance(name, str) or not isinstance(entries, list):
                continue
            per_version: dict[str, dict[str, str]] = {}
            for entry in entries:
                if not isinstance(entry, dict):
                    continue
                version = _text(entry.get("version"), 32)
                if not version:
                    continue
                per_version[version] = {
                    "digest": _text(entry.get("digest"), 80),
                    "download": _text(entry.get("download"), 400),
                    "released_at": _text(entry.get("released_at"), 20),
                }
            if per_version:
                out[name] = per_version
        return out, ""

    def invalidate(self) -> None:
        """Drop the cache. Called after an install so a just-blocked version is not
        reported from a snapshot taken before the operator acted."""
        self._cached = None
