"""Plugin management API: discovery vs. load, approval semantics, error hygiene.

These endpoints are code-execution triggers, so the tests focus on the things that
could turn a management UI into an attack surface:

* listing must not execute anything,
* loading must require prior approval,
* approval must be per-capability and must not grant undeclared capabilities,
* errors must not echo plugin-controlled text into the browser.
"""

from __future__ import annotations

import shutil
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from soapbot.app import create_app, get_plugin_manager
from soapbot.examples import bundled_plugins_dir
from soapbot.security.audit import get_audit_log

#: Bundled examples, not ``data/plugins`` — see ``soapbot.examples``.
PLUGIN_SRC = bundled_plugins_dir()


@pytest.fixture
def client(tmp_path, monkeypatch) -> TestClient:
    """A client whose plugin dir is a private copy of the samples."""
    plugins_dir = tmp_path / "plugins"
    shutil.copytree(PLUGIN_SRC, plugins_dir)

    from soapbot.config import settings

    monkeypatch.setattr(settings, "data_dir", tmp_path)
    get_audit_log().clear()

    app = create_app()
    with TestClient(app) as c:
        manager = get_plugin_manager()
        if manager is not None:
            manager.loader.plugins_dir = plugins_dir
        yield c


def test_listing_does_not_load_anything(client: TestClient) -> None:
    """Discovery must be observation only.

    If listing loaded plugins, merely opening the plugins page would execute
    third-party code — turning a read-only view into the attack itself.
    """
    data = client.get("/api/plugins").json()
    names = {p["name"] for p in data["installed"]}
    assert {"echo", "help", "admin"} <= names
    assert all(p["loaded"] is False for p in data["installed"])
    assert data["loaded"] == []


def test_listing_reports_declared_capabilities(client: TestClient) -> None:
    """The UI must be able to show what it is about to enable."""
    data = client.get("/api/plugins").json()
    echo = next(p for p in data["installed"] if p["name"] == "echo")
    assert "command" in echo["capabilities"]
    assert echo["approved"] is False
    # Everything declared is still pending because nothing was granted.
    assert set(echo["pending"]) == set(echo["capabilities"])


def test_load_without_approval_is_refused(client: TestClient) -> None:
    response = client.post("/api/plugins/echo/load")
    assert response.status_code == 400
    assert "PluginLoadError" in response.json()["detail"]


def test_approve_then_load(client: TestClient) -> None:
    ok = client.post(
        "/api/plugins/echo/approve", json={"capabilities": ["command", "tool"]}
    )
    assert ok.status_code == 200

    loaded = client.post("/api/plugins/echo/load")
    assert loaded.status_code == 200
    body = loaded.json()
    assert body["ok"] is True
    assert "echo" in body["api"]["commands"]

    client.post("/api/plugins/echo/unload")


def test_approve_rejects_undeclared_capability(client: TestClient) -> None:
    """Granting something the plugin never asked for is a no-op that looks like
    success. Refusing makes the mismatch visible instead."""
    response = client.post(
        "/api/plugins/echo/approve", json={"capabilities": ["http"]}
    )
    assert response.status_code == 400
    assert "not declared" in response.json()["detail"]


def test_approve_rejects_unknown_capability(client: TestClient) -> None:
    response = client.post(
        "/api/plugins/echo/approve", json={"capabilities": ["superuser"]}
    )
    assert response.status_code == 400
    assert "unknown capabilities" in response.json()["detail"]


def test_approve_unknown_plugin_is_404(client: TestClient) -> None:
    response = client.post(
        "/api/plugins/nope/approve", json={"capabilities": ["command"]}
    )
    assert response.status_code == 404


def test_error_detail_does_not_echo_plugin_text(client: TestClient, tmp_path: Path) -> None:
    """A plugin's exception message must not reach the browser.

    It is attacker-authored text rendered in a UI, which is both a data-leak and an
    injection vector.
    """
    manager = get_plugin_manager()
    assert manager is not None
    plugin_dir = manager.loader.plugins_dir / "boom"
    plugin_dir.mkdir(parents=True)
    (plugin_dir / "plugin.yaml").write_text(
        "name: boom\nversion: '1.0.0'\nentry: main:P\ntrust: trusted\n"
        "capabilities:\n  - command\n",
        encoding="utf-8",
    )
    (plugin_dir / "main.py").write_text(
        "class P:\n"
        "    def setup(self, ctx):\n"
        "        raise RuntimeError('SECRET-TOKEN-sk-abcdefghijklmnop')\n",
        encoding="utf-8",
    )
    client.post("/api/plugins/boom/approve", json={"capabilities": ["command"]})
    response = client.post("/api/plugins/boom/load")

    assert response.status_code == 400
    assert "SECRET-TOKEN" not in response.text
    assert "sk-abcdefghijklmnop" not in response.text
    # The loader wraps whatever the plugin raised into PluginLoadError, so even the
    # exception *type* is host-controlled. That is stronger than filtering the
    # message: no plugin-chosen string reaches the response at all.
    assert response.json()["detail"] == "load failed: PluginLoadError"
    # The real cause is still available where it belongs — the audit trail.
    events = client.get("/api/plugins/boom/errors").json()["events"]
    assert any("RuntimeError" in e.get("detail", "") for e in events)


def test_plugin_audit_endpoint_is_scoped(client: TestClient) -> None:
    client.post("/api/plugins/echo/approve", json={"capabilities": ["command", "tool"]})
    client.post("/api/plugins/echo/load")
    client.post("/api/plugins/echo/unload")

    events = client.get("/api/plugins/echo/errors").json()["events"]
    assert events
    assert all(e.get("plugin") == "echo" for e in events)

# ------------------------------------------------------------------- upload

_MANIFEST = """\
name: uploaded
version: 1.0.0
description: uploaded in a test
entry: main:Plugin
trust: community
capabilities:
  - command
"""


def _package(extra: dict[str, str] | None = None) -> bytes:
    import io
    import zipfile

    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w") as zf:
        zf.writestr("uploaded/plugin.yaml", _MANIFEST)
        zf.writestr("uploaded/main.py", "class Plugin:\n    pass\n")
        for name, body in (extra or {}).items():
            zf.writestr(name, body)
    return buf.getvalue()


def test_upload_installs_but_does_not_approve(client: TestClient) -> None:
    """If upload approved, uploading a file would be the whole attack."""
    response = client.post(
        "/api/plugins/install",
        files={"file": ("uploaded.zip", _package(), "application/zip")},
    )
    assert response.status_code == 200
    body = response.json()
    assert body["name"] == "uploaded"
    assert body["approved"] is False

    listed = {p["name"]: p for p in client.get("/api/plugins").json()["installed"]}
    assert "uploaded" in listed
    assert listed["uploaded"]["approved"] is False
    assert listed["uploaded"]["loaded"] is False
    assert set(listed["uploaded"]["pending"]) == {"command"}


def test_upload_rejects_traversal_with_a_readable_reason(client: TestClient) -> None:
    response = client.post(
        "/api/plugins/install",
        files={"file": ("evil.zip", _package({"../evil.py": "x"}), "application/zip")},
    )
    assert response.status_code == 400
    assert "traversal" in response.json()["detail"] or "escapes" in response.json()["detail"]


def test_upload_rejects_a_non_zip(client: TestClient) -> None:
    response = client.post(
        "/api/plugins/install",
        files={"file": ("notes.txt", b"not a zip", "text/plain")},
    )
    assert response.status_code == 400
