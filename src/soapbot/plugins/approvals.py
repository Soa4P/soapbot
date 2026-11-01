"""Persistent record of which plugin capabilities an operator approved.

The defect this closes
----------------------
``PluginLoader._approved`` was a plain ``dict`` in memory. Consequences, all
observed:

* every restart forgot every approval, so a deployment could not come back up
  with a working plugin — the operator had to re-approve through the WebUI after
  each deploy, and a headless deployment had no way to do it at all;
* the WebUI showed "enabled" for a plugin that would refuse to load;
* an approval was indistinguishable from a mistake, because nothing durable
  recorded that a human had made the decision.

Why a separate file and not the manifest
----------------------------------------
The manifest is written by the plugin author; the approval is written by the
operator. Storing the approval *inside* the manifest would mean a plugin update
carries its own authorisation forward — a plugin that adds ``http`` to its
manifest would arrive pre-approved. Keeping them in different files, owned by
different parties, is the entire point. See :meth:`PluginLoader.approve`.

Where the file lives, and why it is not under ``data/plugins/``
--------------------------------------------------------------
``data/plugins/<name>/`` is replaced wholesale when a plugin is upgraded or
removed, and ``PluginLoader.remove_from_disk`` deletes that directory. An
approval file inside it would disappear with it (silently revoking) or be
restored from an attacker-supplied archive (silently granting). It also keeps
this single decision record readable at a fixed path for ``soapbot doctor`` and
for operators who back up one file.

Two digests, and why changing the code now revokes the approval
---------------------------------------------------------------
This file used to say: *"Changing a plugin's code does not revoke its approval. That is a
real gap."* It was — ``digest`` covers ``plugin.yaml``, so replacing ``main.py`` left the
manifest byte-identical and the plugin kept loading as approved. Approval was a decision
about a directory name.

:attr:`ApprovalRecord.content_digest` records the code as well, and
:meth:`soapbot.plugins.loader.PluginLoader.load` compares it before importing anything.
Both are kept, not merged: a manifest edit and a code edit are different events and an
operator reading this file should be able to tell which one happened.

Enforcement lives on the *load* path, not here. :meth:`ApprovalStore.code_drift` and
:meth:`ApprovalStore.drift` stay report-only so that a panel can show what drifted without
the page failing to render. Refusing to execute is the loader's job, and it is governed by
``SOAPBOT_PLUGIN_INTEGRITY_MODE`` — ``block`` by default, ``warn`` to keep running while
an upgrade is being rolled out, ``off`` to disable the check entirely.

Capability *gaps* (a newly declared capability) still require re-approval independently,
enforced by ``CapabilityGrant.effective`` regardless of what this file says.
"""

from __future__ import annotations

import json
import logging
import os
import tempfile
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

logger = logging.getLogger(__name__)

FILENAME = "plugin-approvals.json"
"""Fixed filename under the data directory."""

_SCHEMA = 1


@dataclass(slots=True)
class ApprovalRecord:
    """One operator decision about one plugin."""

    plugin: str
    capabilities: frozenset[str] = field(default_factory=frozenset)
    digest: str = ""
    """Manifest digest (``sha256:...``) of the bytes that were approved.

    Covers ``plugin.yaml`` only, which is why it rides alongside
    :attr:`content_digest` rather than replacing it: the manifest answers "did the
    declared capabilities change", the content digest answers "did the code change".
    """

    content_digest: str = ""
    """Digest of the plugin's *code*, not its manifest.

    Recorded at approval time and checked before every load. Without it, approval was a
    decision about a directory name: ``digest`` stays identical while ``main.py`` is
    replaced, so a plugin that was reviewed once could execute anything later. The two
    digests are separate fields on purpose — a manifest edit (new capability) needs
    re-approval through the capability gap, while a code edit needs re-approval through
    this one, and an operator reading the file should be able to tell which happened.

    Empty for approvals written before this field existed; see
    :func:`soapbot.plugins.integrity.compare`, where empty means ``unknown`` rather than
    ``changed``.
    """

    approved_at: float = 0.0
    approved_by: str = ""
    """Free-form label for the audit trail (``webui``, ``cli``, an operator id)."""

    def to_dict(self) -> dict[str, Any]:
        return {
            "capabilities": sorted(self.capabilities),
            "digest": self.digest,
            "content_digest": self.content_digest,
            "approved_at": self.approved_at,
            "approved_by": self.approved_by,
        }

    @classmethod
    def from_dict(cls, plugin: str, raw: dict[str, Any]) -> ApprovalRecord:
        caps = raw.get("capabilities") or []
        # Defensive parsing: the file is operator-editable and may be hand-edited
        # or truncated by a crash. A malformed entry must degrade to "no
        # capabilities" (the closed direction), never raise and take startup down.
        return cls(
            plugin=plugin,
            capabilities=frozenset(str(c) for c in caps if isinstance(c, str)),
            digest=str(raw.get("digest") or ""),
            content_digest=str(raw.get("content_digest") or ""),
            approved_at=float(raw.get("approved_at") or 0.0),
            approved_by=str(raw.get("approved_by") or ""),
        )


class ApprovalStore:
    """Read/write the approval file. Safe to use without a file existing."""

    def __init__(self, path: Path) -> None:
        self.path = Path(path)
        self._records: dict[str, ApprovalRecord] = {}
        self._loaded = False

    # ------------------------------------------------------------------ load/save
    def load(self) -> dict[str, ApprovalRecord]:
        """Read the file into memory. Missing file means "nothing approved"."""
        if self._loaded:
            return dict(self._records)
        self._loaded = True

        if not self.path.exists():
            self._records = {}
            return {}

        try:
            raw = json.loads(self.path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError) as exc:
            # Start closed and say so loudly. A corrupt approval file silently
            # treated as "empty" would look like every plugin lost its approval,
            # which is the correct outcome but not the obvious one to debug.
            logger.error(
                "plugin approval file is unreadable (%s); treating every plugin as "
                "unapproved. Fix or delete %s.",
                exc,
                self.path,
            )
            self._records = {}
            return {}

        plugins = raw.get("plugins")
        if not isinstance(plugins, dict):
            logger.warning("plugin approval file has no 'plugins' object: %s", self.path)
            plugins = {}

        self._records = {
            str(name): ApprovalRecord.from_dict(str(name), entry)
            for name, entry in plugins.items()
            if isinstance(entry, dict)
        }
        return dict(self._records)

    def _flush(self) -> None:
        payload = {
            "schema": _SCHEMA,
            "plugins": {name: rec.to_dict() for name, rec in sorted(self._records.items())},
        }
        data = json.dumps(payload, ensure_ascii=False, indent=2, sort_keys=True) + "\n"

        # Atomic replace: a crash mid-write must not leave a truncated file, since
        # a truncated file revokes every plugin at the next start. The temp file is
        # created in the same directory so os.replace stays on one filesystem.
        self.path.parent.mkdir(parents=True, exist_ok=True)
        fd, tmp_name = tempfile.mkstemp(
            prefix=".plugin-approvals-", dir=str(self.path.parent)
        )
        tmp = Path(tmp_name)
        try:
            with os.fdopen(fd, "w", encoding="utf-8") as handle:
                handle.write(data)
                handle.flush()
                os.fsync(handle.fileno())
            os.replace(tmp, self.path)
        finally:
            tmp.unlink(missing_ok=True)
        # Owner-only on POSIX, so another account on a shared host cannot edit
        # which plugins are approved. Done inline rather than through
        # ``security.files.tighten`` because that helper's warning is about key
        # material ("mount the master key from a secret store") and would send an
        # operator looking for a key that does not exist. This file is not a
        # secret; it is a permission record that must not be writable by others.
        if os.name == "posix":
            try:
                os.chmod(self.path, 0o600)
            except OSError:  # pragma: no cover - exotic filesystem
                logger.warning("could not restrict permissions on %s", self.path)

    # ------------------------------------------------------------------ mutation
    def approve(
        self,
        plugin: str,
        capabilities: set[str] | frozenset[str] | None = None,
        *,
        digest: str = "",
        content_digest: str = "",
        actor: str = "",
    ) -> ApprovalRecord:
        import time

        record = ApprovalRecord(
            plugin=plugin,
            capabilities=frozenset(str(c) for c in (capabilities or ())),
            digest=digest,
            content_digest=content_digest,
            approved_at=time.time(),
            approved_by=actor,
        )
        self.load()
        self._records[plugin] = record
        self._flush()
        return record

    def revoke(self, plugin: str) -> bool:
        self.load()
        if plugin not in self._records:
            return False
        del self._records[plugin]
        self._flush()
        return True

    # ------------------------------------------------------------------ queries
    def get(self, plugin: str) -> ApprovalRecord | None:
        self.load()
        return self._records.get(plugin)

    def is_approved(self, plugin: str) -> bool:
        return self.get(plugin) is not None

    def capabilities_for(self, plugin: str) -> frozenset[str]:
        record = self.get(plugin)
        return record.capabilities if record is not None else frozenset()

    def all(self) -> dict[str, ApprovalRecord]:
        return self.load()

    def code_drift(self, digests: dict[str, str]) -> dict[str, str]:
        """Plugins whose approved *code* digest no longer matches ``digests``.

        Report-only, like :meth:`drift`, and for the same reason: raising here would
        make the panel page unusable after a legitimate upgrade. Enforcement happens on
        the load path (:meth:`soapbot.plugins.loader.PluginLoader.load`), where refusing
        to execute is meaningful and where the policy setting applies. Keeping the two
        separate means an operator can *see* drift before it is ever loaded.

        ``digests`` maps plugin name -> current :func:`soapbot.plugins.integrity.digest_tree`.
        A plugin with no recorded content digest is not reported: approved-before-this-
        existed is not the same claim as modified.
        """
        out: dict[str, str] = {}
        for name, current in digests.items():
            record = self.get(name)
            if record is None or not record.content_digest:
                continue
            if record.content_digest != current:
                out[name] = record.content_digest
        return out

    def drift(self, manifests: dict[str, str]) -> dict[str, str]:
        """Plugins whose approved manifest digest no longer matches ``manifests``.

        ``manifests`` maps plugin name -> current digest. A plugin with no
        recorded digest (approved before digests were stored, or approved by a
        caller that did not supply one) is not reported: "unknown" is not the same
        claim as "changed", and reporting it would make the first run after an
        upgrade look like an incident.
        """
        out: dict[str, str] = {}
        for name, current in manifests.items():
            record = self.get(name)
            if record is None or not record.digest:
                continue
            if record.digest != current:
                out[name] = record.digest
        return out


def default_path(data_dir: Path) -> Path:
    """Conventional location of the approval file for a given data directory."""
    return Path(data_dir) / FILENAME


__all__ = ["FILENAME", "ApprovalRecord", "ApprovalStore", "default_path"]
