"""Portable runtime attestation for a loaded plugin.

What an approval digest does not say
------------------------------------
``plugins.integrity`` already re-hashes the tree on every load and reload. That
answers "are these the bytes the operator approved?". It does not produce anything an
operator or another process can carry away: no record of *which policy* was in force,
no record of *what actually executed*, and no way to re-check the whole combination
later without trusting the process that made the claim.

A :class:`RuntimeAttestation` binds four things into one JSON-portable record:

* ``artifact_digest``  — the SHA-256 tree digest at load time;
* ``policy_version``   — a stable fingerprint of the policy inputs in force
  (host version, capability set, integrity mode), so a policy change is visible;
* ``execution``        — what actually happened: integrity verdict, whether a process
  boundary was used, whether import/setup succeeded, declared and approved capabilities;
* ``record_digest``    — a canonical hash of the record itself.

Boundaries, stated plainly
--------------------------
The record is **detectably tamper-evident, not cryptographically signed**. ``signature``
and :meth:`RuntimeAttestation.signable_payload` exist so a keyed backend can be added
without changing the schema; today ``signature`` is empty. Hardware-rooted
attestation is out of scope for an in-repo Python service and is not claimed here.

``verify`` re-hashes the tree and re-computes the policy fingerprint against whatever
policy the caller passes in. It is meant to run at runtime composition time (load,
reload, and any later consistency sweep), not once at install.
"""

from __future__ import annotations

import hashlib
import json
import time
from dataclasses import dataclass, replace
from pathlib import Path
from typing import Any

from soapbot.plugins.integrity import digest_tree, forget

SCHEMA_VERSION = 1


def host_policy() -> dict[str, Any]:
    """The policy inputs an attestation is bound to.

    Deliberately a plain mapping: the record must be verifiable by a process that has
    this repository but not the loader's in-memory state.
    """
    from soapbot import __version__
    from soapbot.config import settings
    from soapbot.plugins.manifest import Capability

    return {
        "host_version": __version__,
        "capabilities": sorted(c.value for c in Capability),
        "integrity_mode": str(settings.plugin_integrity_mode),
    }


def _policy_version(policy: dict[str, Any]) -> str:
    raw = json.dumps(policy, sort_keys=True, separators=(",", ":")).encode("utf-8")
    return "sha256:" + hashlib.sha256(raw).hexdigest()[:16]


def _canonical(payload: dict[str, Any]) -> bytes:
    return json.dumps(payload, sort_keys=True, separators=(",", ":")).encode("utf-8")


@dataclass(frozen=True, slots=True)
class ExecutionEvidence:
    """Facts observed while the plugin was actually loaded."""

    integrity_state: str
    isolated: bool
    import_succeeded: bool
    capabilities: tuple[str, ...]
    approved: tuple[str, ...]
    loaded_at: float


@dataclass(frozen=True, slots=True)
class AttestationVerdict:
    ok: bool
    reason: str
    current_digest: str = ""
    current_policy: str = ""


@dataclass(frozen=True, slots=True)
class RuntimeAttestation:
    plugin: str
    version: str
    artifact_digest: str
    policy_version: str
    execution: ExecutionEvidence
    schema_version: int = SCHEMA_VERSION
    signature: str = ""
    record_digest: str = ""

    def payload(self) -> dict[str, Any]:
        """Everything covered by ``record_digest`` (and by a future signature)."""
        return {
            "schema_version": self.schema_version,
            "plugin": self.plugin,
            "version": self.version,
            "artifact_digest": self.artifact_digest,
            "policy_version": self.policy_version,
            "execution": {
                "integrity_state": self.execution.integrity_state,
                "isolated": self.execution.isolated,
                "import_succeeded": self.execution.import_succeeded,
                "capabilities": list(self.execution.capabilities),
                "approved": list(self.execution.approved),
                "loaded_at": self.execution.loaded_at,
            },
        }

    def signable_payload(self) -> bytes:
        """Canonical bytes a keyed backend would sign. No key is used today."""
        return _canonical(self.payload())

    def to_dict(self) -> dict[str, Any]:
        return {**self.payload(), "signature": self.signature, "record_digest": self.record_digest}

    @classmethod
    def from_dict(cls, raw: dict[str, Any]) -> RuntimeAttestation:
        execution = raw["execution"]
        return cls(
            plugin=str(raw["plugin"]),
            version=str(raw["version"]),
            artifact_digest=str(raw["artifact_digest"]),
            policy_version=str(raw["policy_version"]),
            execution=ExecutionEvidence(
                integrity_state=str(execution["integrity_state"]),
                isolated=bool(execution["isolated"]),
                import_succeeded=bool(execution["import_succeeded"]),
                capabilities=tuple(execution["capabilities"]),
                approved=tuple(execution["approved"]),
                loaded_at=float(execution["loaded_at"]),
            ),
            schema_version=int(raw["schema_version"]),
            signature=str(raw.get("signature", "")),
            record_digest=str(raw.get("record_digest", "")),
        )

    def _expected_record_digest(self) -> str:
        return "sha256:" + hashlib.sha256(self.signable_payload()).hexdigest()

    def verify(
        self, root: Path, *, policy: dict[str, Any] | None = None
    ) -> AttestationVerdict:
        """Re-verify the bound triple at runtime, not from a cached verdict."""
        if self.schema_version != SCHEMA_VERSION:
            return AttestationVerdict(False, "schema_mismatch")
        if self.record_digest != self._expected_record_digest():
            return AttestationVerdict(False, "record_tampered")
        if not self.execution.import_succeeded:
            return AttestationVerdict(False, "execution_incomplete")

        active = host_policy() if policy is None else policy
        current_policy = _policy_version(active)
        if current_policy != self.policy_version:
            return AttestationVerdict(
                False, "policy_drift", current_policy=current_policy
            )

        root = Path(root)
        if not root.is_dir():
            return AttestationVerdict(False, "artifact_missing", current_policy=current_policy)
        forget(root)
        current_digest = digest_tree(root)
        if current_digest != self.artifact_digest:
            return AttestationVerdict(
                False, "artifact_changed", current_digest, current_policy
            )
        return AttestationVerdict(True, "ok", current_digest, current_policy)


def build_attestation(
    *,
    plugin: str,
    version: str,
    directory: Path,
    integrity_state: str,
    capabilities: tuple[str, ...],
    approved: tuple[str, ...],
    isolated: bool,
    policy: dict[str, Any] | None = None,
) -> RuntimeAttestation:
    """Create a record from what actually happened during a successful load.

    Callers must invoke this only after import and setup succeeded. The tree is hashed
    here rather than reused from ``_enforce_integrity`` so the digest in the record is
    the digest of the bytes that are about to execute, not of an earlier scan.
    """
    directory = Path(directory)
    forget(directory)
    base = RuntimeAttestation(
        plugin=plugin,
        version=version,
        artifact_digest=digest_tree(directory),
        policy_version=_policy_version(host_policy() if policy is None else policy),
        execution=ExecutionEvidence(
            integrity_state=integrity_state,
            isolated=isolated,
            import_succeeded=True,
            capabilities=tuple(sorted(capabilities)),
            approved=tuple(sorted(approved)),
            loaded_at=time.time(),
        ),
    )
    return replace(
        base,
        record_digest="sha256:"
        + hashlib.sha256(base.signable_payload()).hexdigest(),
    )


__all__ = [
    "SCHEMA_VERSION",
    "AttestationVerdict",
    "ExecutionEvidence",
    "RuntimeAttestation",
    "build_attestation",
    "host_policy",
]
