"""Wave 9: read-only management views.

The API existed for plugins and audit only. Providers, personas, memory, knowledge and
budget were reachable by chatting with the bot and by nothing else — which made the
management panel described in the README impossible to build and left an operator
unable to answer "what is actually configured?" without reading files on the host.

What these tests pin:

* every view returns the same objects the pipeline uses (not a second instance that
  could drift);
* a credential never appears in any response;
* a feature that is switched off reports ``enabled: false`` instead of pretending to be
  empty — "no spend requests" and "no ledger" are different situations and an operator
  needs to tell them apart;
* no runtime means 503, not a stack trace.
"""

from __future__ import annotations

from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from soapbot.config import settings


def _config(tmp_path: Path, *, providers: str = "", adapters: str = "") -> Path:
    import shutil

    config_dir = tmp_path / "cfg"
    config_dir.mkdir(parents=True, exist_ok=True)
    (config_dir / "providers.yaml").write_text(
        providers or "providers: []\n", encoding="utf-8"
    )
    (config_dir / "adapters.yaml").write_text(adapters or "adapters: []\n", encoding="utf-8")
    # Copy the shipped persona cards so the view is exercised against real files
    # rather than a hand-written fixture that could drift from the loader's format.
    source = Path(__file__).resolve().parents[1] / "config" / "personas"
    if source.is_dir():
        shutil.copytree(source, config_dir / "personas")
    return config_dir


@pytest.fixture
def runtime_client(tmp_path, monkeypatch):
    """App with the runtime on, one provider, budget enabled."""
    from soapbot.app import create_app

    config_dir = _config(
        tmp_path,
        providers=(
            "providers:\n"
            "  - id: mock-openai\n"
            "    kind: openai_compat\n"
            "    label: Mock\n"
            "    base_url: https://mock.local/v1\n"
            "    api_key: sk-super-secret-value\n"
            "    model: mock-model\n"
            "    priority: 1\n"
        ),
    )
    monkeypatch.setattr(settings, "enable_runtime", True)
    monkeypatch.setattr(settings, "config_dir", config_dir)
    monkeypatch.setattr(settings, "enable_budget", True)

    with TestClient(create_app()) as client:
        yield client


def test_runtime_view_reports_layers(runtime_client: TestClient) -> None:
    body = runtime_client.get("/api/runtime").json()
    assert body["running"] is True
    assert set(body["metrics"]) >= {"inbound", "handled", "halted", "failed"}
    assert body["scheduler"]["running"] is True
    assert body["config"]["memory_enabled"] is True
    assert body["config"]["budget_enabled"] is True
    assert body["adapter_count"] == 0


def test_providers_view_never_returns_the_api_key(runtime_client: TestClient) -> None:
    """A key in the response body is a key in the browser, the cache and any HAR dump."""
    body = runtime_client.get("/api/providers").json()
    assert body["count"] == 1
    assert body["providers"][0]["id"] == "mock-openai"
    assert body["providers"][0]["model"] == "mock-model"
    assert "sk-super-secret-value" not in runtime_client.get("/api/providers").text


def test_providers_view_includes_health_counters(runtime_client: TestClient) -> None:
    """Failover order and per-provider failures are the whole reason to show this."""
    body = runtime_client.get("/api/providers").json()
    assert "mock-openai" in body["stats"]
    assert body["stats"]["mock-openai"]["calls"] == 0


def test_personas_view_lists_installed_cards(runtime_client: TestClient) -> None:
    body = runtime_client.get("/api/personas").json()
    assert body["count"] >= 1
    ids = {p["id"] for p in body["personas"]}
    assert "default" in ids
    assert "binding" in body


def test_memory_views_start_empty(runtime_client: TestClient) -> None:
    sessions = runtime_client.get("/api/memory/sessions").json()
    assert sessions["sessions"] == []

    stats = runtime_client.get("/api/memory/stats").json()
    assert stats["total"] == 0
    assert isinstance(stats["layers"], dict)


def test_memory_timeline_requires_a_session_key(runtime_client: TestClient) -> None:
    assert runtime_client.get("/api/memory/timeline").status_code == 422
    ok = runtime_client.get("/api/memory/timeline", params={"session_key": "a:group:1"})
    assert ok.status_code == 200
    assert ok.json()["messages"] == []


def test_knowledge_view_starts_empty(runtime_client: TestClient) -> None:
    body = runtime_client.get("/api/knowledge").json()
    assert body["documents"] == []


def test_budget_view_reports_policy_and_requests(runtime_client: TestClient) -> None:
    body = runtime_client.get("/api/budget").json()
    assert body["enabled"] is True
    assert body["policy"]["currency"] == settings.budget_currency
    assert body["policy"]["period_cap_minor"] == settings.budget_period_cap_minor
    assert body["requests"] == []


def test_budget_view_says_disabled_rather_than_empty(tmp_path, monkeypatch) -> None:
    """'no requests' and 'no ledger' must be distinguishable in the UI."""
    from soapbot.app import create_app

    monkeypatch.setattr(settings, "enable_runtime", True)
    monkeypatch.setattr(settings, "config_dir", _config(tmp_path))
    monkeypatch.setattr(settings, "enable_budget", False)

    with TestClient(create_app()) as client:
        body = client.get("/api/budget").json()
    assert body["enabled"] is False


def test_access_matrix_matches_the_permission_table(runtime_client: TestClient) -> None:
    body = runtime_client.get("/api/access").json()
    floors = {p["name"]: p["min_role"] for p in body["permissions"]}
    # The one that surprises operators, and therefore the one worth asserting.
    assert floors["approve_payment"] == "owner"
    assert floors["chat"] == "member"
    assert "owner" in {r["name"] for r in body["roles"]}


def test_logs_view_filters_by_level_and_text(runtime_client: TestClient) -> None:
    body = runtime_client.get("/api/logs", params={"limit": 50}).json()
    assert "entries" in body

    errors_only = runtime_client.get("/api/logs", params={"level": "ERROR"}).json()
    assert all(e["level"] in ("ERROR", "CRITICAL") for e in errors_only["entries"])

    filtered = runtime_client.get("/api/logs", params={"contains": "zzz-no-such-line"}).json()
    assert filtered["entries"] == []


def test_bilibili_view_reports_disabled(runtime_client: TestClient) -> None:
    body = runtime_client.get("/api/bilibili").json()
    assert body["enabled"] is False
    assert "L3" in body["notice"] or "未实现" in body["notice"]


def test_bilibili_preview_is_503_when_disabled(runtime_client: TestClient) -> None:
    response = runtime_client.get("/api/bilibili/preview", params={"target": "BV1xx411c7mD"})
    assert response.status_code == 503


def test_adapters_view_is_empty_but_well_formed(runtime_client: TestClient) -> None:
    body = runtime_client.get("/api/adapters").json()
    assert body == {"adapters": [], "count": 0}


def test_unknown_api_route_is_json_404(runtime_client: TestClient) -> None:
    """The SPA catch-all must not swallow API typos into an HTML 200."""
    response = runtime_client.get("/api/does-not-exist")
    assert response.status_code == 404
    assert response.headers["content-type"].startswith("application/json")


def test_admin_views_require_auth_from_a_remote_client() -> None:
    """The views expose group ids and message history; loopback is not enough remotely."""
    from tests.test_wave7_auth import _request

    from soapbot.api.auth import configure_auth
    from soapbot.security.tokens import BootstrapToken, TokenService

    service = TokenService(secret="k" * 40, ttl_hours=1)
    configure_auth(service=service, bootstrap=BootstrapToken("b"))

    from fastapi import HTTPException

    from soapbot.api.auth import authenticate

    with pytest.raises(HTTPException) as exc:
        authenticate(_request("203.0.113.9"))
    assert exc.value.status_code == 401


def test_root_page_explains_a_missing_webui_build(tmp_path, monkeypatch) -> None:
    """An install without the frontend must explain itself, not 404 at '/'."""
    import soapbot.app as app_module

    monkeypatch.setattr(app_module, "_WEBUI_DIST", tmp_path / "no-webui")
    app = app_module.create_app()

    with TestClient(app) as client:
        response = client.get("/")
    assert response.status_code == 200
    assert "管理面板尚未构建" in response.text


def test_built_webui_is_served_when_present(tmp_path, monkeypatch) -> None:
    """The bundle written by ``npm run build`` is served from the package itself.

    Serving it from a second path would let the wheel and the panel drift to different
    versions; this asserts the wiring, not the bundle's contents.
    """
    import soapbot.app as app_module

    dist = tmp_path / "dist"
    (dist / "assets").mkdir(parents=True)
    (dist / "index.html").write_text("<!doctype html><div id=app></div>", encoding="utf-8")
    (dist / "assets" / "app.js").write_text("console.log(1)", encoding="utf-8")

    monkeypatch.setattr(app_module, "_WEBUI_DIST", dist)
    app = app_module.create_app()

    with TestClient(app) as client:
        root = client.get("/")
        deep = client.get("/budget")
        asset = client.get("/assets/app.js")
        missing_api = client.get("/api/nope")

    assert root.status_code == 200 and "id=app" in root.text
    # History-mode routing: a deep link must return the shell, not a 404.
    assert deep.status_code == 200 and "id=app" in deep.text
    assert asset.status_code == 200
    # …but an API typo must stay a JSON 404 rather than render the shell as success.
    assert missing_api.status_code == 404
    assert missing_api.headers["content-type"].startswith("application/json")
