"""The QQ allow-list editor: owner-only, validated, and impossible to lock yourself out of.

Measured flow this serves: the operator sees ADMIN/MEMBER 未配置 on page 04 and has to ssh
in to fix it. These tests pin the behaviours that make the button safe to press.
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from soapbot.api.security import router as security_router
from soapbot.security.audit import get_audit_log


@pytest.fixture()
def env_file(tmp_path: Path) -> Path:
    path = tmp_path / ".env"
    path.write_text("# operator notes stay\nSOAPBOT_LOG_LEVEL=INFO\n", encoding="utf-8")
    return path


@pytest.fixture()
def client(env_file: Path, monkeypatch: pytest.MonkeyPatch) -> TestClient:
    import soapbot.api.settings as settings_api

    monkeypatch.setenv("SOAPBOT_ENV_FILE", str(env_file))
    monkeypatch.setattr(settings_api, "_env_path", lambda: env_file)

    app = FastAPI()
    app.include_router(security_router)
    test_client = TestClient(app)
    return test_client


def _post(client: TestClient, payload: dict[str, Any], role: str = "owner"):
    client.headers["Authorization"] = "Bearer x"
    original = client.app.dependency_overrides.copy()  # type: ignore[attr-defined]

    from soapbot.api.auth import require_api_auth

    client.app.dependency_overrides[require_api_auth] = lambda: {"role": role}  # type: ignore[attr-defined]
    try:
        return client.post("/api/security/authority", json=payload)
    finally:
        client.app.dependency_overrides.clear()  # type: ignore[attr-defined]
        client.app.dependency_overrides.update(original)  # type: ignore[attr-defined]


def test_non_owner_is_refused(client: TestClient) -> None:
    response = _post(client, {"owners": ["123"], "admins": [], "members": []}, role="admin")
    assert response.status_code == 403
    deny = [
        e
        for e in get_audit_log().recent(limit=50)
        if e["action"] == "authority_write" and e["outcome"] == "deny"
    ]
    assert deny, "a refused escalation must land in the audit trail"


def test_writes_env_and_normalises(client: TestClient, env_file: Path) -> None:
    response = _post(
        client,
        {"owners": [" １２３４５６ ", "123456"], "admins": ["0007"], "members": []},
    )
    assert response.status_code == 200
    body = response.json()
    # Full-width digits fold onto the same number; the duplicate disappears. Leading zeros
    # too: "0007" and "7" are the same account.
    assert body["owners"] == ["123456"]
    assert body["admins"] == ["7"]
    text = env_file.read_text(encoding="utf-8")
    assert "SOAPBOT_OWNER_IDS=123456" in text
    assert "SOAPBOT_ADMIN_IDS=7" in text
    assert "SOAPBOT_LOG_LEVEL=INFO" in text, "the operator's other lines must survive"
    assert "# operator notes stay" in text


def test_a_non_numeric_id_is_rejected(client: TestClient) -> None:
    response = _post(client, {"owners": ["owner: fooled you"], "admins": [], "members": []})
    assert response.status_code == 400


def test_the_last_owner_cannot_be_removed(
    client: TestClient, monkeypatch: pytest.MonkeyPatch
) -> None:
    from soapbot.config import settings

    monkeypatch.setattr(settings, "first_run_owner", "")
    response = _post(client, {"owners": [], "admins": [], "members": []})
    assert response.status_code == 400
    text = json.dumps(response.json(), ensure_ascii=False)
    assert "owner" in text.lower()


def test_first_run_owner_survives_the_first_save(
    client: TestClient, monkeypatch: pytest.MonkeyPatch
) -> None:
    """build_authority consults first_run_owner only while owner_ids is empty — so a save
    that drops it would silently demote the one person who can undo the mistake."""
    from soapbot.config import settings

    monkeypatch.setattr(settings, "first_run_owner", "123456789")
    response = _post(client, {"owners": ["555"], "admins": [], "members": []})
    assert response.status_code == 200
    assert response.json()["owners"] == ["123456789", "555"]
