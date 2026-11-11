"""Three signals that used to be implicit: boot scope, log writes, advisory AI.

These are small on purpose. None of them adds a subsystem; each makes an existing
boundary say what it actually guarantees, and pins that statement with a test.
"""

from __future__ import annotations

import importlib.util
import sys
from pathlib import Path
from typing import Any

import pytest

from soapbot.core.trace import TraceStore
from soapbot.plugins.surfaces import LOG_WRITES_PER_MINUTE, SurfaceRouter

ROOT = Path(__file__).resolve().parents[1]
GATE_PATH = ROOT / "scripts" / "check_security_boundaries.py"


class _Audit:
    def __init__(self) -> None:
        self.records: list[dict[str, Any]] = []

    def record(self, **kwargs: Any) -> None:
        self.records.append(kwargs)


def _router(audit: _Audit) -> SurfaceRouter:
    # ``log.write`` is deliberately not capability-gated, so the guard is never
    # consulted by this path. An opaque object makes that fact visible in the test.
    return SurfaceRouter(guard=object(), plugin="demo", audit=audit)  # type: ignore[arg-type]


def _load_gate():
    spec = importlib.util.spec_from_file_location("check_security_boundaries", GATE_PATH)
    assert spec and spec.loader
    gate = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = gate
    spec.loader.exec_module(gate)
    return gate


def test_trace_summary_names_its_boot_and_denies_recoverability() -> None:
    summary = TraceStore().summary()
    assert summary["historical"] is False
    assert summary["recoverable"] is False
    assert summary["boot_id"]
    assert "不可回放" in summary["note"]


def test_two_stores_share_one_process_boot_id() -> None:
    from soapbot.core import trace as module

    assert TraceStore().boot_id == TraceStore().boot_id == module._BOOT_ID


@pytest.mark.asyncio
async def test_log_write_is_attributed_in_the_audit_stream() -> None:
    audit = _Audit()
    router = _router(audit)
    assert await router.dispatch("log.write", {"message": "hello"}, None) is True
    assert len(audit.records) == 1
    event = audit.records[0]
    assert event["action"] == "surface:log.write"
    assert event["plugin"] == "demo"
    assert event["outcome"] == "allow"
    assert "hello" not in event["detail"], "the message body must not land in the audit log"


@pytest.mark.asyncio
async def test_log_write_is_deterministically_rate_limited() -> None:
    audit = _Audit()
    router = _router(audit)
    for _ in range(LOG_WRITES_PER_MINUTE):
        assert await router.dispatch("log.write", {"message": "x"}, None) is True
    assert await router.dispatch("log.write", {"message": "x"}, None) is False
    assert audit.records[-1]["outcome"] == "deny"
    assert "rate limited" in audit.records[-1]["detail"]


def test_the_ai_review_stays_advisory_and_the_gate_knows_it() -> None:
    gate = _load_gate()
    results = gate.checks()
    details = [result.detail for result in results]
    assert "AI review states it is not a gate" in details
    assert "AI review never approves or merges" in details
    assert "the backend gates never consult the AI verdict" in details
    assert "settings writes keep their inline permission floor" in details
    assert "revoke-all keeps its inline OWNER floor" in details
    failed = [result.detail for result in results if not result.ok]
    assert not failed, f"the deterministic gate is not green: {failed}"
