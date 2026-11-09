"""A loaded plugin needs portable proof of what ran, under which policy.

``plugins.integrity`` already re-hashes the tree on load and reload. What was missing is
a record that binds that digest to the policy in force and to the execution facts, and
that a later caller can re-verify without trusting the process that produced it.
"""

from __future__ import annotations

import json
from dataclasses import replace
from pathlib import Path

from soapbot.plugins.attestation import (
    SCHEMA_VERSION,
    RuntimeAttestation,
    build_attestation,
)

POLICY = {"host_version": "0.1.0", "capabilities": ["http"], "integrity_mode": "block"}


def _tree(tmp_path: Path) -> Path:
    root = tmp_path / "plugin"
    root.mkdir()
    (root / "main.py").write_text("def setup(ctx):\n    return None\n", encoding="utf-8")
    return root


def _record(root: Path) -> RuntimeAttestation:
    return build_attestation(
        plugin="demo",
        version="1.2.3",
        directory=root,
        integrity_state="ok",
        capabilities=("http", "memory"),
        approved=("http",),
        isolated=True,
        policy=POLICY,
    )


def test_the_record_binds_artifact_policy_and_execution(tmp_path: Path) -> None:
    root = _tree(tmp_path)
    record = _record(root)

    assert record.schema_version == SCHEMA_VERSION
    assert record.artifact_digest.startswith("sha256:")
    assert record.policy_version.startswith("sha256:")
    assert record.execution.import_succeeded is True
    assert record.execution.integrity_state == "ok"
    assert record.execution.isolated is True
    assert record.execution.capabilities == ("http", "memory")
    assert record.execution.approved == ("http",)
    assert record.verify(root, policy=POLICY).ok


def test_the_record_survives_a_json_round_trip(tmp_path: Path) -> None:
    root = _tree(tmp_path)
    record = _record(root)
    revived = RuntimeAttestation.from_dict(json.loads(json.dumps(record.to_dict())))

    assert revived == record
    assert revived.signable_payload() == record.signable_payload()
    assert revived.verify(root, policy=POLICY).ok


def test_verify_detects_a_changed_artifact(tmp_path: Path) -> None:
    root = _tree(tmp_path)
    record = _record(root)
    (root / "main.py").write_text("# tampered after load\n", encoding="utf-8")

    verdict = record.verify(root, policy=POLICY)
    assert not verdict.ok
    assert verdict.reason == "artifact_changed"
    assert verdict.current_digest != record.artifact_digest


def test_verify_detects_policy_drift(tmp_path: Path) -> None:
    root = _tree(tmp_path)
    record = _record(root)

    verdict = record.verify(root, policy={**POLICY, "integrity_mode": "warn"})
    assert not verdict.ok
    assert verdict.reason == "policy_drift"
    assert verdict.current_policy != record.policy_version


def test_verify_detects_a_tampered_record(tmp_path: Path) -> None:
    root = _tree(tmp_path)
    record = _record(root)
    tampered = replace(record, version="9.9.9")

    verdict = tampered.verify(root, policy=POLICY)
    assert not verdict.ok
    assert verdict.reason == "record_tampered"


def test_an_incomplete_execution_is_never_verified(tmp_path: Path) -> None:
    root = _tree(tmp_path)
    record = _record(root)
    incomplete = replace(
        record,
        execution=replace(record.execution, import_succeeded=False),
    )
    # Rebuild the record digest so the failure under test is the execution evidence,
    # not the tamper check.
    from hashlib import sha256

    incomplete = replace(
        incomplete,
        record_digest="sha256:" + sha256(incomplete.signable_payload()).hexdigest(),
    )
    assert incomplete.verify(root, policy=POLICY).reason == "execution_incomplete"


def test_the_signature_boundary_is_explicit(tmp_path: Path) -> None:
    """Not signed today; the signable payload exists so a keyed backend can be added."""
    record = _record(_tree(tmp_path))
    assert record.signature == ""
    assert record.signable_payload()
    assert record.record_digest.startswith("sha256:")


def test_loader_produces_and_can_reverify_at_runtime() -> None:
    """Wiring check: both load paths must attest, and a public re-verify must exist."""
    source = (
        Path(__file__).resolve().parents[1]
        / "src"
        / "soapbot"
        / "plugins"
        / "loader.py"
    ).read_text(encoding="utf-8")
    assert "self._attest(name, directory, manifest, integrity, isolated=True)" in source
    assert "self._attest(name, directory, manifest, integrity, isolated=False)" in source
    assert "def verify_attestation(" in source
    assert "return record.verify(loaded.path)" in source
