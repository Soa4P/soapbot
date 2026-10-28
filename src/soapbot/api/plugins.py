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

import logging

from fastapi import APIRouter, HTTPException, Query, Request
from pydantic import BaseModel, Field

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/api/plugins", tags=["plugins"])

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
    try:
        result = install_from_zip(
            payload,
            loader.plugins_dir,
            host_version=loader.host_version,
        )
    except InstallError as exc:
        logger.warning("plugin install rejected: %s", exc)
        raise HTTPException(status_code=400, detail=str(exc)) from exc

    logger.info("plugin uploaded name=%s bytes=%d", result.name, len(payload))
    return result.to_dict()


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
                        # Digest drift: the manifest changed after approval. Not
                        # enforced (see plugins/approvals.py) but it must be
                        # visible, because "approved v1.0, running v1.1" is
                        # exactly the state an operator wants to notice.
                        "manifest_changed": bool(
                            record.digest
                            and manifest.manifest_digest
                            and record.digest != manifest.manifest_digest
                        ),
                    }
                    if record is not None
                    else None
                ),
            }
        )

    return {
        "installed": installed,
        "rejected": [{"path": p, "reason": r} for p, r in report.rejected],
        "loaded": sorted(loader.loaded),
    }


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
    loader.approve(
        name,
        set(body.capabilities),
        actor="webui",
        manifest_digest=manifest.manifest_digest,
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
    _authorize(request)
    manager = _manager()
    try:
        loaded = await manager.load(name)
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
    _authorize(request)
    manager = _manager()
    try:
        loaded = await manager.reload(name)
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
        raise HTTPException(status_code=400, detail=str(exc)) from exc
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
