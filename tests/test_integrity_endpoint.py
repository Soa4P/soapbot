"""One honest read-only answer to "what was approved, and is it still true"."""

from __future__ import annotations

from types import SimpleNamespace

import pytest
from fastapi.testclient import TestClient

from soapbot.api.security import integrity_signals
from soapbot.app import create_app


class _Traces:
    def summary(self) -> dict:
        return {"boot_id": "boot-abc", "recoverable": False, "historical": False}


class _Mcp:
    def status(self) -> dict:
        return {
            "servers": [
                {
                    "name": "filesystem",
                    "pinned_tools_digest": "a" * 64,
                    "tools_digest": "a" * 64,
                },
                {
                    "name": "changed",
                    "pinned_tools_digest": "b" * 64,
                    "tools_digest": "c" * 64,
                },
                {"name": "unpinned", "pinned_tools_digest": "", "tools_digest": "d" * 64},
            ]
        }


class _Loader:
    def attestation_verdicts(self) -> dict:
        return {"demo": {"ok": True, "reason": "ok"}}


def _runtime():
    return SimpleNamespace(traces=_Traces(), mcp=_Mcp(), plugins=_Loader())


@pytest.mark.asyncio
async def test_integrity_view_aggregates_the_three_signal_sources(monkeypatch) -> None:
    from soapbot import app as app_module

    monkeypatch.setattr(app_module, "get_runtime", _runtime)
    body = await integrity_signals({})
    assert body["available"] is True
    assert body["trace"] == {
        "boot_id": "boot-abc",
        "recoverable": False,
        "historical": False,
    }
    assert body["plugins"] == {"demo": {"ok": True, "reason": "ok"}}
    rows = {row["name"]: row for row in body["mcp"]}
    assert rows["filesystem"]["metadata_approved"] is True
    assert rows["changed"]["metadata_approved"] is False
    # An empty pin is "recorded, not approved" — it must never read as a pass.
    assert rows["unpinned"]["metadata_approved"] is False
    assert body["verification"]["ai_review_is_gate"] is False


@pytest.mark.asyncio
async def test_a_missing_runtime_is_unavailable_not_green(monkeypatch) -> None:
    from soapbot import app as app_module

    monkeypatch.setattr(app_module, "get_runtime", lambda: None)
    body = await integrity_signals({})
    assert body["available"] is False
    assert body["trace"] is None
    assert body["mcp"] == []
    assert body["plugins"] == {}
    assert body["verification"]["ai_review_is_gate"] is False


def test_the_endpoint_is_read_only_and_leaks_no_credentials() -> None:
    # Loopback read-only views are intentionally reachable without a session (the
    # same rule as /api/security/permissions). What matters here is that the view is
    # a GET that reports state only: no runtime means "unavailable", not "all green",
    # and nothing credential-shaped is echoed back.
    with TestClient(create_app()) as client:
        response = client.get("/api/security/integrity")
        assert response.status_code == 200
        body = response.json()
        assert body["available"] is False
        assert body["trace"] is None
        assert body["verification"]["ai_review_is_gate"] is False
        lowered = response.text.lower()
        assert "access_token" not in lowered
        assert "secret.key" not in lowered
        assert client.post("/api/security/integrity").status_code == 405
