"""Plugin management API.

Every mutating endpoint here is a code-execution trigger: loading a plugin runs
third-party code in-process. Consequently:

* the **declared capability set and trust level are returned with every plugin**, so
  the UI can require the operator to see what they are enabling rather than
  offering a bare "enable" switch;
* approval is a separate call from discovery — listing plugins never loads them;
* paths and errors are sanitised: a plugin's own exception message can contain
  credentials, and the UI is streamed to a browser.

Auth: every endpoint calls ``_authorize``, which requires a signed operator token
from any non-loopback client (``soapbot.api.auth``). Loopback is kept as a shortcut
for the local single-operator case only. The bind address is one config edit away
from ``0.0.0.0``, and a plugin-load endpoint exposed to a network is remote code
execution — so the decision is made per request from the credential, not from the
assumption that the process is listening somewhere private.
"""

from __future__ import annotations

import hashlib
import logging
from pathlib import Path
from typing import Any

from fastapi import APIRouter, Depends, HTTPException, Query, Request
from pydantic import BaseModel, Field

from soapbot.api.auth import require_role
from soapbot.api.errors import safe_detail
from soapbot.config import settings
from soapbot.security.principal import Role

logger = logging.getLogger(__name__)

#: Plugins reviewed and shipped *inside this package*. A plugin discovered under the
#: user's data directory can never be official, no matter what its manifest says —
#: `channel` in plugin.yaml is a claim by the package author, and adding one line to a
#: zip costs nothing. Provenance is decided here, in code that ships with the release.
#:
#: Empty today because the bundled samples in ``soapbot/examples/plugins`` are examples,
#: not loaded plugins. When one is promoted to a shipped plugin, add its name here and
#: make sure it is loaded from the package path (see ``_channel_of``).
BUNDLED_OFFICIAL_PLUGINS: frozenset[str] = frozenset()


def _channel_of(manifest: Any, loader: Any) -> str:
    """Whether this *installed* plugin is official, decided by provenance not by claim."""
    name = str(getattr(manifest, "name", ""))
    if name not in BUNDLED_OFFICIAL_PLUGINS:
        return "community"
    try:
        # ``api/plugins.py`` -> ``soapbot/`` is one parent up from this file's parent.
        package_root = Path(__file__).resolve().parent.parent
        plugin_dir = (Path(loader.plugins_dir) / name).resolve()
        # A same-named upload in data/plugins must not inherit the label.
        return "official" if plugin_dir.is_relative_to(package_root) else "community"
    except (AttributeError, OSError, TypeError):
        return "community"


# Installing, approving and loading a plugin executes third-party code in a worker
# process. A MEMBER who can do that but cannot edit one config line is a permission
# inversion, so the whole router starts at ADMIN.
router = APIRouter(
    prefix="/api/plugins", tags=["plugins"], dependencies=[Depends(require_role(Role.ADMIN))]
)

def _authorize(request: Request) -> None:
    """Require an operator credential for plugin management.

    Previously this was "loopback only", enforced in code rather than assumed from the
    bind address. That was still not a control: a reverse proxy makes remote requests
    arrive from loopback, and one ``SOAPBOT_HOST=0.0.0.0`` in a ``.env`` turns "load
    plugin" into unauthenticated remote code execution. The check now demands a signed
    token from any non-loopback client, and keeps the loopback shortcut only for the
    local single-operator case (see ``soapbot.api.auth``).
    """
    from soapbot.api.auth import authenticate

    authenticate(request)


class ApproveRequest(BaseModel):
    capabilities: list[str] = Field(default_factory=list)
    """Explicit capability grant. Empty means "approve nothing yet" — the operator
    must name what they are granting, so a fat-fingered click cannot hand out
    network access by default."""


def _manager():
    from soapbot.app import get_plugin_manager

    manager = get_plugin_manager()
    if manager is None:
        raise HTTPException(status_code=503, detail="plugin system is not initialised")
    return manager


async def _code_changed(loader, name: str, record) -> bool:
    """Whether the plugin's source no longer matches what was approved.

    Computed for the listing so the panel can warn *before* someone presses Load. The
    enforcement lives in ``PluginLoader.load``; this is the same comparison, done earlier,
    because an operator's first notice of tampering should not be a failed load.

    Async because the comparison hashes the plugin tree: this runs once per installed
    plugin inside the listing endpoint, so doing it inline summed every plugin's disk
    read onto the event loop and stalled chat while the panel was open.
    """
    if record is None or not getattr(record, "content_digest", ""):
        return False
    directory = loader.plugins_dir / name
    if not directory.is_dir():
        return False
    try:
        from soapbot.plugins.integrity import compare_async

        return (await compare_async(directory, record.content_digest)).state == "changed"
    except OSError:  # pragma: no cover - unreadable tree
        return False


@router.post("/install")
async def install_plugin(request: Request) -> dict:
    """Upload a plugin package as the raw request body. **This does not approve it.**

    The security model keys on the manifest digest and on an explicit, per-capability
    grant. If installation also approved the plugin, uploading a file would be the
    whole attack: declare ``network`` + ``command``, upload, and the bot runs it. So
    this endpoint stops at "the bytes are on disk and discovered", and the response
    says ``approved: false`` so a caller cannot mistake one for the other.

    The body is the archive itself, not multipart: FastAPI's ``UploadFile`` requires
    ``python-multipart``, and adding a parser (plus a dependency that must be present
    in the image or the app fails at import) to accept one file is a poor trade. The
    plugin's name comes from its manifest, so the multipart filename carried no
    information anyway.

    The caller is expected to send the operator to ``POST /{name}/approve`` next; the
    console does exactly that.
    """
    _authorize(request)
    from soapbot.plugins.installer import MAX_ARCHIVE_BYTES, InstallError, install_from_zip

    declared = request.headers.get("content-length")
    if declared is not None:
        try:
            if int(declared) > MAX_ARCHIVE_BYTES:
                raise HTTPException(
                    status_code=413,
                    detail=f"archive is larger than {MAX_ARCHIVE_BYTES // 1024} KiB",
                )
        except ValueError:
            raise HTTPException(status_code=400, detail="invalid content-length") from None

    payload = await request.body()
    manager = _manager()
    loader = manager.loader
    # The blocklist is consulted here, not inside the installer: the local file always
    # applies, the community index only when it happened to be reachable. A stale cache
    # is used on purpose — a version blocked fifteen minutes ago must still be refused
    # when the network is down, and the local list is the part that cannot be emptied.
    blocked = dict(manager.index.local_blocked)
    snapshot = await manager.index.snapshot()
    blocked.update(snapshot.blocked)
    try:
        result = install_from_zip(
            payload,
            loader.plugins_dir,
            host_version=loader.host_version,
            blocked=blocked,
        )
    except InstallError as exc:
        logger.warning("plugin install rejected: %s", exc)
        raise HTTPException(status_code=400, detail=safe_detail(400, exc, "plugins")) from exc

    logger.info("plugin uploaded name=%s bytes=%d", result.name, len(payload))
    return result.to_dict()


@router.post("/install-from-index")
async def install_from_index(body: InstallFromIndexRequest, request: Request) -> dict:
    """One-click install from the community index — download, verify, install.

    The old stance ("nothing here is installable in one click") predates per-version
    digests; the chain that makes this safe now:

    1. **索引决定「有什么」**：version metadata comes from the index snapshot
       (``plugin_versions.json``, fetched with the same guards as the catalogue);
    2. **digest 决定「拿到的是不是声明的那个」**：the release zip is downloaded and
       hashed; a mismatch with the index-declared digest is a hard 400 — a compromised
       index degrades to "the download is refused", not to code execution;
    3. **审批决定「能做什么」**：this endpoint calls the same ``install_from_zip`` and
       returns ``approved: false`` — the operator still ticks capabilities on the
       approval screen, and load still refuses anything not approved.

    Refusals that are by design: versions without a real digest (draft placeholders),
    versions on the blocklist, archives that fail any installer check.
    """
    _authorize(request)
    from soapbot.plugins.installer import MAX_ARCHIVE_BYTES, InstallError, install_from_zip
    from soapbot.plugins.sandbox import assert_url_allowed

    manager = _manager()
    snapshot = await manager.index.snapshot()
    if not snapshot.available:
        raise HTTPException(status_code=503, detail="插件索引不可用，无法一键安装")
    meta = snapshot.version_meta(body.name, body.version)
    if meta is None:
        raise HTTPException(
            status_code=404,
            detail=f"索引里没有 {body.name} {body.version} 的可用版本元数据",
        )
    blocked_reason = snapshot.blocked_reason(body.name, body.version)
    if blocked_reason:
        raise HTTPException(status_code=400, detail=f"该版本已被封禁：{blocked_reason}")

    download_url = str(meta.get("download", ""))
    try:
        assert_url_allowed(download_url, allowed_hosts=None)
    except Exception as exc:
        raise HTTPException(status_code=400, detail=f"下载地址未通过安全检查：{exc}") from exc

    try:
        payload = await _download_release(download_url)
    except Exception:
        logger.warning("plugin download failed name=%s", body.name)
        raise HTTPException(status_code=502, detail="下载发布包失败") from None
    if len(payload) > MAX_ARCHIVE_BYTES:
        raise HTTPException(status_code=413, detail="发布包超出安装器体积上限")
    digest = "sha256:" + hashlib.sha256(payload).hexdigest()
    expected = str(meta.get("digest", ""))
    if digest != expected:
        # 信任链的锚：下载内容与索引声明不一致，一律拒绝——不管看起来多像。
        # 详情带两个哈希前缀：这是操作者能自查「索引还是源被换了」的唯一线索，
        # 且哈希前缀不构成任何内容泄漏。
        logger.warning(
            "plugin digest mismatch name=%s got=%s want=%s", body.name, digest[:19], expected[:19]
        )
        raise HTTPException(
            status_code=400,
            detail=f"发布包 digest 与索引声明不一致（{digest[:19]}… != {expected[:19]}…）",
        )

    loader = manager.loader
    blocked = dict(manager.index.local_blocked)
    blocked.update(snapshot.blocked)
    try:
        result = install_from_zip(
            payload,
            loader.plugins_dir,
            host_version=loader.host_version,
            blocked=blocked,
        )
    except InstallError as exc:
        logger.warning("plugin install rejected: %s", exc)
        raise HTTPException(status_code=400, detail=safe_detail(400, exc, "plugins")) from exc
    manager.index.invalidate()
    logger.info("plugin installed from index name=%s version=%s", body.name, body.version)
    return result.to_dict()


class InstallFromIndexRequest(BaseModel):
    name: str = Field(..., min_length=1, max_length=64)
    version: str = Field(..., min_length=1, max_length=32)


async def _download_release(url: str) -> bytes:
    """Fetch one release archive. One short-lived client per call (same pattern as
    ``IndexClient._fetch``): a rare 50MiB download gains nothing from connection
    pooling, and a shared pool would bind its transport into whatever test double or
    event loop the caller brought — measured, not hypothetical.

    Non-200 raises, so the caller's single ``except`` covers both transport and
    status failures — "下载失败" is one error shape for the operator, not two.
    """
    import httpx

    from soapbot.net.client import build_timeout

    async with httpx.AsyncClient(
        timeout=build_timeout(15.0), follow_redirects=False, trust_env=False
    ) as http:
        response = await http.get(url, headers={"user-agent": "soapbot-plugin-install"})
    if response.status_code != 200:
        raise RuntimeError(f"release download returned {response.status_code}")
    return response.content


def _version_tuple(version: str) -> tuple[int, ...] | None:
    """Numeric version key for "is there a newer version", or ``None`` when the
    string is not plain numeric segments (``1.2.3``). ``None`` means "cannot tell" —
    and "cannot tell" must never render as an update badge."""
    parts = version.strip().split(".")
    if not parts or not all(p.isdigit() for p in parts):
        return None
    return tuple(int(p) for p in parts)


def _update_available(installed: str, latest: str) -> bool:
    installed_key = _version_tuple(installed)
    latest_key = _version_tuple(latest)
    if installed_key is None or latest_key is None:
        return False
    return latest_key > installed_key


@router.get("")
async def list_plugins(request: Request) -> dict:
    """Installed plugins: what is on disk, what is loaded, what is approved."""
    _authorize(request)
    manager = _manager()
    loader = manager.loader
    report = loader.discover()

    installed = []
    for manifest in report.found:
        grant = loader.grant_for(manifest)
        loaded = loader.get(manifest.name)
        record = (
            loader.approvals.get(manifest.name)
            if getattr(loader, "approvals", None) is not None
            else None
        )
        installed.append(
            {
                **manifest.to_dict(),
                # Overrides the manifest's own `channel`: see BUNDLED_OFFICIAL_PLUGINS.
                # Without this, any uploaded zip could label itself official.
                "channel": _channel_of(manifest, loader),
                "approved": loader.is_approved(manifest.name),
                "loaded": loaded is not None,
                "granted": sorted(c.value for c in grant.effective),
                "pending": sorted(c.value for c in grant.declared - grant.effective),
                "invocations": loaded.invocations if loaded else 0,
                "api": loaded.context.exported_api() if loaded else None,
                # Approval provenance. Without it the UI cannot distinguish "the
                # operator approved this" from "it happens to have no pending
                # capabilities", and an approval that survived a restart is
                # otherwise indistinguishable from a fresh in-memory default.
                "approval": (
                    {
                        "approved_at": record.approved_at,
                        "approved_by": record.approved_by,
                        # Digest drift: the manifest changed after approval. Reported
                        # rather than enforced (see plugins/approvals.py) but it must be
                        # visible, because "approved v1.0, running v1.1" is exactly the
                        # state an operator wants to notice.
                        "manifest_changed": bool(
                            record.digest
                            and manifest.manifest_digest
                            and record.digest != manifest.manifest_digest
                        ),
                        # Code drift: the *implementation* changed after approval. This one
                        # is enforced on load (block by default), but the panel has to show
                        # it *before* someone presses Load, or the only way to discover it
                        # is a failed attempt with a stack trace.
                        "code_changed": await _code_changed(loader, manifest.name, record),
                        "integrity_mode": settings.plugin_integrity_mode,
                    }
                    if record is not None
                    else None
                ),
                "integrity": loaded.integrity if loaded else None,
            }
        )

    # An installed plugin can be on a version that was blocked *after* it was installed.
    # That is not something to auto-uninstall — removing working code because a list
    # changed is its own outage — but it must be visible, because "this is known bad and
    # still running" is the state an operator needs to see.
    snapshot = await manager.index.snapshot()
    catalogue_latest = {e.name: e.latest for e in snapshot.entries if e.latest}
    for item in installed:
        reason = snapshot.blocked_reason(item["name"], item["version"])
        if reason:
            item["blocked"] = {"version": item["version"], "reason": reason}
        # 升级提示：索引声明了更新的版本就标出来——「能不能升」由操作者决定，
        # 「有新版」必须可见（fish-memory 的教训：装了旧版无人提醒）。
        item["update_available"] = _update_available(
            str(item["version"]), catalogue_latest.get(item["name"], "")
        )

    return {
        "installed": installed,
        "rejected": [{"path": p, "reason": r} for p, r in report.rejected],
        "loaded": sorted(loader.loaded),
        "index": {
            "available": snapshot.available,
            "source": snapshot.source,
            "error": snapshot.error,
            "entries": [e.to_dict() for e in snapshot.entries],
        },
    }


@router.get("/discover")
async def discover(request: Request, refresh: bool = Query(False)) -> dict:
    """The community catalogue, read-only.

    Deliberately separate from the installed listing: this is the only endpoint that
    touches the network, so a slow or hostile index cannot delay the page that shows what
    is actually on disk. ``refresh=true`` bypasses the cache, which is what the panel's
    "重新获取" button sends.

    Cards here carry a one-click install (``POST /install-from-index``): the download is
    verified against the index-declared digest and installed through the same installer
    — and it still lands as ``approved: false``. Approval remains the human gate.
    """
    _authorize(request)
    manager = _manager()
    snapshot = await manager.index.snapshot(force=refresh)
    return snapshot.to_dict()


@router.post("/{name}/approve")
async def approve(name: str, body: ApproveRequest, request: Request) -> dict:
    """Grant specific capabilities to a plugin.

    Deliberately not "approve everything the manifest asks for": the operator must
    name each capability, which keeps the decision conscious and makes the granted
    set independent of whatever the plugin later writes into its own manifest.
    """
    _authorize(request)
    manager = _manager()
    loader = manager.loader
    manifest = next((m for m in loader.discover().found if m.name == name), None)
    if manifest is None:
        raise HTTPException(status_code=404, detail="plugin not found")

    from soapbot.plugins.manifest import Capability

    known = {c.value for c in Capability}
    unknown = [c for c in body.capabilities if c not in known]
    if unknown:
        raise HTTPException(
            status_code=400, detail=f"unknown capabilities: {', '.join(unknown)}"
        )
    undeclared = [c for c in body.capabilities if c not in {x.value for x in manifest.capabilities}]
    if undeclared:
        # Granting a capability the plugin never declared would be a no-op that
        # looks like success; refuse so the mismatch is visible.
        raise HTTPException(
            status_code=400,
            detail=f"capabilities not declared by the plugin: {', '.join(undeclared)}",
        )

    # ``actor="webui"`` and the manifest digest both go into the record: the first
    # tells an auditor where the decision came from, the second makes a later
    # silent manifest edit detectable instead of invisible.
    #
    # The content digest is computed here, off the loop, and passed in: ``approve``
    # would otherwise hash the tree synchronously inside this request and stall chat.
    # It must be hashed *now* rather than at load time — the approved bytes are the
    # reviewed bytes, and a load-time hash records whatever is on disk by then.
    content_digest = await loader.hash_plugin(name)
    loader.approve(
        name,
        set(body.capabilities),
        actor="webui",
        manifest_digest=manifest.manifest_digest,
        content_digest=content_digest,
    )
    return {"ok": True, "name": name, "granted": body.capabilities, "persisted": True}


@router.post("/{name}/revoke")
async def revoke(name: str, request: Request) -> dict:
    """Withdraw approval without unloading anything.

    Separate from ``/unload`` because the two answer different questions: "stop
    this now" versus "do not start this again". Unloading first would also make a
    revoke-then-reload sequence silently succeed, which is the bug this endpoint
    exists to make impossible to express by accident.
    """
    _authorize(request)
    manager = _manager()
    loader = manager.loader
    if not loader.is_approved(name) and loader.get(name) is None:
        raise HTTPException(status_code=404, detail="plugin not approved")
    loader.revoke(name, actor="webui")
    return {"ok": True, "name": name, "loaded": loader.get(name) is not None}


@router.post("/{name}/load")
async def load_plugin(name: str, request: Request) -> dict:
    from soapbot.plugins.loader import PluginBlockedError

    _authorize(request)
    manager = _manager()
    try:
        loaded = await manager.load(name)
    except PluginBlockedError as exc:
        # A host decision, not plugin-authored text, so it is safe to name. The reason
        # itself is intentionally omitted: it comes from a third-party index and the
        # full text is already available in the plugin listing's `blocked` field.
        logger.warning("blocked plugin load refused name=%s", name)
        raise HTTPException(status_code=403, detail="plugin version is blocked") from exc
    except Exception as exc:
        # Type only. A plugin's exception text is attacker-influenced and lands in
        # a browser; echoing it would be a leak and possibly an XSS vector.
        logger.warning("plugin load failed name=%s err=%s", name, type(exc).__name__)
        raise HTTPException(
            status_code=400, detail=f"load failed: {type(exc).__name__}"
        ) from exc
    return {"ok": True, "name": name, "api": loaded.context.exported_api()}


@router.post("/{name}/reload")
async def reload_plugin(name: str, request: Request) -> dict:
    from soapbot.plugins.loader import PluginBlockedError

    _authorize(request)
    manager = _manager()
    try:
        loaded = await manager.reload(name)
    except PluginBlockedError as exc:
        logger.warning("blocked plugin reload refused name=%s", name)
        raise HTTPException(status_code=403, detail="plugin version is blocked") from exc
    except Exception as exc:
        logger.warning("plugin reload failed name=%s err=%s", name, type(exc).__name__)
        raise HTTPException(
            status_code=400, detail=f"reload failed: {type(exc).__name__}"
        ) from exc
    return {"ok": True, "name": name, "api": loaded.context.exported_api()}


@router.post("/{name}/unload")
async def unload_plugin(name: str, request: Request) -> dict:
    _authorize(request)
    manager = _manager()
    await manager.unload(name)
    return {"ok": True, "name": name}


@router.delete("/{name}")
async def delete_plugin(name: str, request: Request) -> dict:
    """Unload, un-approve, then delete the plugin directory.

    Order is load-bearing. Deleting the directory of a loaded plugin would leave
    its handlers in the command table pointing at code that no longer exists, and
    revoking after the delete would leave an approval record naming a plugin whose
    files are gone — which a later drop-in of the same name would inherit. So:
    unload (stop touching it), revoke (forget the decision), delete (remove it).

    ``remove_from_disk`` had no caller before this endpoint: the containment check
    that refuses to delete outside the plugins root existed, was tested, and
    guarded nothing, because the only way to uninstall a plugin was ``rm -rf``
    from a shell. A path-containment check nobody can reach is not protection.
    """
    _authorize(request)
    manager = _manager()
    loader = manager.loader

    from soapbot.plugins.loader import PluginLoader

    if loader.get(name) is not None:
        await manager.unload(name)
    loader.revoke(name, actor="webui")

    try:
        PluginLoader.remove_from_disk(loader.plugins_dir, name)
    except ValueError as exc:
        # Path traversal attempt, or a symlink escaping the root. Never 500: the
        # refusal is the correct answer and the operator should see it verbatim.
        raise HTTPException(status_code=400, detail=safe_detail(400, exc, "plugins")) from exc
    except OSError as exc:
        logger.warning("plugin delete failed name=%s err=%s", name, type(exc).__name__)
        raise HTTPException(status_code=500, detail="delete failed") from exc
    return {"ok": True, "name": name, "deleted": True}


@router.get("/{name}/errors")
async def plugin_errors(
    name: str, request: Request, limit: int = Query(50, ge=1, le=500)
) -> dict:
    """Audit entries for one plugin. The triage view after an incident."""
    _authorize(request)
    from soapbot.security.audit import get_audit_log

    events = [
        e for e in get_audit_log().recent(limit=1000) if e.get("plugin") == name
    ]
    return {"events": events[-limit:], "count": len(events)}
