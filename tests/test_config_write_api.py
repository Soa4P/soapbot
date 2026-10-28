"""HTTP surface of the config write path.

The unit tests in ``test_config_write.py`` cover the merge rules. These cover the
three-step protocol as a client actually drives it, because the dangerous failures
here are all protocol-level:

* the read endpoint must never return a credential, in any field, at any depth;
* the diff endpoint must not write — a client that shows a diff and then navigates
  away must leave the file untouched;
* apply must refuse a stale base and must refuse a diff the operator did not approve;
* a successful apply must report ``restart_required``, because it is true and because
  a panel that implies live reload is lying about what the running process sees.
"""

from __future__ import annotations

from pathlib import Path

import pytest
from fastapi.testclient import TestClient

LITERAL_KEY = "sk-live-do-not-leak-4f81c2"


@pytest.fixture
def client(tmp_path, monkeypatch) -> TestClient:
    from soapbot.app import create_app
    from soapbot.config import settings

    config_dir = tmp_path / "cfg"
    config_dir.mkdir(parents=True, exist_ok=True)
    (config_dir / "providers.yaml").write_text(
        "providers:\n"
        "  - id: primary\n"
        "    kind: openai_compat\n"
        "    label: 主线路\n"
        "    base_url: https://api.example.com/v1\n"
        f"    api_key: {LITERAL_KEY}\n"
        "    model: deepseek-chat\n"
        "  - id: backup\n"
        "    kind: openai_compat\n"
        "    base_url: https://backup.example.com/v1\n"
        "    api_key: env:CONFIG_TEST_KEY\n"
        "    model: gpt-4o-mini\n",
        encoding="utf-8",
    )
    (config_dir / "adapters.yaml").write_text("adapters: []\n", encoding="utf-8")

    monkeypatch.setattr(settings, "config_dir", config_dir)
    monkeypatch.setenv("CONFIG_TEST_KEY", "sk-env-backed")
    return TestClient(create_app())


def _providers_path(tmp_path: Path) -> Path:
    return tmp_path / "cfg" / "providers.yaml"


# ------------------------------------------------------------------- reading


def test_read_masks_the_literal_key(client: TestClient) -> None:
    body = client.get("/api/config/providers").json()
    assert LITERAL_KEY not in str(body)
    assert body["document"]["providers"][0]["api_key"] == body["mask"]


def test_read_shows_env_reference_and_hash(client: TestClient) -> None:
    body = client.get("/api/config/providers").json()
    assert body["document"]["providers"][1]["api_key"] == "env:CONFIG_TEST_KEY"
    assert body["base_hash"]
    assert body["unchanged_sentinel"] == "__UNCHANGED__"


def test_every_config_route_declares_auth() -> None:
    """Every config route must take ``require_api_auth`` as a parameter.

    Checked against the endpoint signature rather than by sending a request:
    TestClient connects from "testclient", which ``api/auth.py`` trusts as loopback on
    purpose, so no request can demonstrate the 401 path. The signature is also the
    place a route added later would forget it — which is the failure this guards.
    """
    import inspect

    from soapbot.api.config_write import router

    for route in router.routes:
        params = inspect.signature(route.endpoint).parameters
        defaults = [repr(p.default) for p in params.values()]
        assert any("require_api_auth" in d for d in defaults), (
            f"{getattr(route, 'path', '?')} 没有声明 require_api_auth"
        )


def _caller(role: str) -> dict:
    return {"mode": "token", "subject": "someone", "role": role}


def test_member_role_is_refused_before_any_file_access(tmp_path) -> None:
    """The permission gate must reject below ADMIN, and must do it by raising."""
    from types import SimpleNamespace

    from fastapi import HTTPException

    from soapbot.api.config_write import _require_permission
    from soapbot.security.principal import Permission

    request = SimpleNamespace(client=SimpleNamespace(host="203.0.113.9"))
    with pytest.raises(HTTPException) as excinfo:
        _require_permission(_caller("member"), request, Permission.MANAGE_CONFIG)
    assert excinfo.value.status_code == 403


def test_admin_role_passes_the_gate() -> None:
    from types import SimpleNamespace

    from soapbot.api.config_write import _require_permission
    from soapbot.security.principal import Permission

    request = SimpleNamespace(client=SimpleNamespace(host="203.0.113.9"))
    _require_permission(_caller("admin"), request, Permission.MANAGE_CONFIG)


def test_owner_role_passes_the_gate() -> None:
    """Loopback callers are owners by construction; they must not be locked out of
    their own single-host deployment."""
    from types import SimpleNamespace

    from soapbot.api.config_write import _require_permission
    from soapbot.security.principal import Permission

    request = SimpleNamespace(client=SimpleNamespace(host="127.0.0.1"))
    _require_permission(_caller("owner"), request, Permission.MANAGE_CONFIG)


# --------------------------------------------------------------------- diff


def test_diff_reports_changes_without_writing(
    client: TestClient, tmp_path: Path
) -> None:
    before = _providers_path(tmp_path).read_text(encoding="utf-8")
    body = client.post(
        "/api/config/providers/diff",
        json={"base_hash": "", "providers": [{"id": "primary", "label": "改名了"}]},
    ).json()

    assert "改名了" in body["diff"]
    assert any("label" in f for f in body["changed_fields"])
    assert _providers_path(tmp_path).read_text(encoding="utf-8") == before, "diff 不应写盘"


def test_diff_hides_the_key(client: TestClient) -> None:
    body = client.post(
        "/api/config/providers/diff",
        json={"base_hash": "", "providers": [{"id": "primary", "label": "x"}]},
    ).json()
    assert LITERAL_KEY not in body["diff"]


def test_diff_rejects_an_unbootable_candidate(client: TestClient, monkeypatch) -> None:
    monkeypatch.delenv("CONFIG_TEST_KEY", raising=False)
    response = client.post(
        "/api/config/providers/diff",
        json={"base_hash": "", "providers": [{"id": "primary", "label": "x"}]},
    )
    assert response.status_code == 422
    assert "CONFIG_TEST_KEY" in response.json()["detail"]


def test_diff_reports_conflict_on_stale_hash(client: TestClient, tmp_path: Path) -> None:
    path = _providers_path(tmp_path)
    path.write_text(path.read_text(encoding="utf-8").replace("主线路", "别人改的"), encoding="utf-8")
    response = client.post(
        "/api/config/providers/diff",
        json={"base_hash": "stale-hash-value", "providers": [{"id": "primary", "label": "x"}]},
    )
    assert response.status_code == 409


# -------------------------------------------------------------------- apply


def test_apply_writes_and_reports_restart(client: TestClient, tmp_path: Path) -> None:
    diff = client.post(
        "/api/config/providers/diff",
        json={"base_hash": "", "providers": [{"id": "primary", "label": "新名字"}]},
    ).json()

    response = client.post(
        "/api/config/providers/apply",
        json={
            "base_hash": diff["base_hash"],
            "approved_hash": diff["new_hash"],
            "providers": [{"id": "primary", "label": "新名字"}],
        },
    )
    body = response.json()

    assert response.status_code == 200
    assert body["written"] is True
    assert body["restart_required"] is True
    assert "新名字" in _providers_path(tmp_path).read_text(encoding="utf-8")


def test_apply_keeps_literal_key_through_the_full_round_trip(
    client: TestClient, tmp_path: Path
) -> None:
    """The end-to-end version of the unit test: read, edit, apply, key survives."""
    read = client.get("/api/config/providers").json()
    entry = dict(read["document"]["providers"][0])
    entry["label"] = "改了标签"
    entry["api_key"] = read["unchanged_sentinel"]

    diff = client.post(
        "/api/config/providers/diff",
        json={"base_hash": read["base_hash"], "providers": [entry]},
    ).json()

    client.post(
        "/api/config/providers/apply",
        json={
            "base_hash": read["base_hash"],
            "approved_hash": diff["new_hash"],
            "providers": [entry],
        },
    )

    on_disk = _providers_path(tmp_path).read_text(encoding="utf-8")
    assert LITERAL_KEY in on_disk, "整个往返流程覆盖了真实密钥"
    assert read["mask"] not in on_disk
    assert "改了标签" in on_disk


def test_apply_refuses_unapproved_diff(client: TestClient, tmp_path: Path) -> None:
    before = _providers_path(tmp_path).read_text(encoding="utf-8")
    response = client.post(
        "/api/config/providers/apply",
        json={
            "base_hash": "",
            "approved_hash": "hash-of-something-else",
            "providers": [{"id": "primary", "label": "偷偷改"}],
        },
    )
    assert response.status_code == 409
    assert _providers_path(tmp_path).read_text(encoding="utf-8") == before


def test_apply_no_op_does_not_touch_the_file(client: TestClient, tmp_path: Path) -> None:
    path = _providers_path(tmp_path)
    read = client.get("/api/config/providers").json()
    mtime = path.stat().st_mtime_ns

    body = client.post(
        "/api/config/providers/apply",
        json={
            "base_hash": read["base_hash"],
            "providers": [{"id": "primary", "label": "主线路"}],
        },
    ).json()

    assert body["written"] is False
    assert path.stat().st_mtime_ns == mtime, "空 patch 也动了文件，会让别人的编辑器失效"


def test_apply_audit_records_names_not_values(client: TestClient) -> None:
    from soapbot.security.audit import get_audit_log

    diff = client.post(
        "/api/config/providers/diff",
        json={"base_hash": "", "providers": [{"id": "primary", "api_key": "sk-brand-new"}]},
    ).json()
    client.post(
        "/api/config/providers/apply",
        json={
            "base_hash": diff["base_hash"],
            "approved_hash": diff["new_hash"],
            "providers": [{"id": "primary", "api_key": "sk-brand-new"}],
        },
    )

    events = [e.to_dict() for e in get_audit_log()._events if e.action == "providers_updated"]
    assert events, "写入没有留下审计记录"
    detail = events[-1]["detail"]
    assert "api_key" in detail
    assert "sk-brand-new" not in detail


def test_malformed_file_is_422_not_an_empty_form(client: TestClient, tmp_path: Path) -> None:
    _providers_path(tmp_path).write_text("providers:\n  - id: [broken\n", encoding="utf-8")
    response = client.get("/api/config/providers")
    assert response.status_code == 422
    assert "YAML" in response.json()["detail"]
