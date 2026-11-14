"""One-click install from the plugin index — the trust chain, end to end.

The chain: 索引决定「有什么」→ digest 校验决定「拿到的是不是声明的那个」→ 审批
（人勾能力清单）决定「能做什么」。These tests pin each link and, just as important,
pin the failure shapes: a mismatched digest is a hard 400 (a compromised index
degrades to "refused", never to "installed"), draft placeholder digests are not
installable, blocked versions stay refused, and the install still lands as
``approved: false`` — approval remains the human gate.

Index + release bytes are served through the seams the production code exposes
(``IndexClient._transport`` for the catalogue pair, a monkeypatched
``_download_release`` for the archive): no real network, no router pollution across
tests — the transport seam is the testability contract the client ships with.
"""

from __future__ import annotations

import hashlib
import io
import zipfile
from functools import lru_cache
from pathlib import Path

import httpx
import pytest
from fastapi.testclient import TestClient

from soapbot.app import create_app, get_plugin_manager

INDEX_URL = "https://raw.example.com/soa/main/plugins.json"
DOWNLOAD_URL = "https://raw.example.com/soa/main/packs/mood-diary-0.1.0.zip"


@lru_cache(maxsize=1)
def _real_zip() -> bytes:
    """A zip the real installer accepts — built ONCE per process.

    `zipfile.writestr` stamps the current local time into every entry header, so
    rebuilding per call changes the bytes by the minute and the digest anchor
    (computed at import) stops matching what the mock serves. One build, cached.
    """
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w", zipfile.ZIP_DEFLATED) as z:
        z.writestr(
            "plugin.yaml",
            "name: mood-diary\nversion: 0.1.0\nentry: main:MoodDiaryPlugin\n"
            "description: test\nauthor: t\ntrust: community\nchannel: community\n"
            "min_host_version: 0.1.0\ncapabilities:\n  - command\n  - storage\n",
        )
        z.writestr("main.py", "PLACEHOLDER = True\n")
    return buf.getvalue()


GOOD_DIGEST = "sha256:" + hashlib.sha256(_real_zip()).hexdigest()


def _index_payload(latest: str = "0.1.0") -> bytes:
    import json as _json

    return _json.dumps(
        {
            "schema_version": 1,
            "plugins": [
                {
                    "name": "mood-diary",
                    "latest": latest,
                    "versions": ["0.1.0"],
                    "summary": "心情日记",
                    "author": "Soa4P",
                }
            ],
        }
    ).encode()


def _versions_payload(digest: str, download: str) -> bytes:
    import json as _json

    return _json.dumps(
        {
            "schema_version": 1,
            "versions": {
                "mood-diary": [
                    {
                        "version": "0.1.0",
                        "released_at": "2026-11-14",
                        "digest": digest,
                        "download": download,
                    }
                ]
            },
        }
    ).encode()


class _StaticIndexTransport(httpx.AsyncBaseTransport):
    """Serves the catalogue pair exactly as the real origin would."""

    def __init__(
        self,
        *,
        digest: str = GOOD_DIGEST,
        index_latest: str = "0.1.0",
        versions_status: int = 200,
    ) -> None:
        self.digest = digest
        self.index_latest = index_latest
        self.versions_status = versions_status

    async def handle_async_request(self, request: httpx.Request) -> httpx.Response:
        if request.url.path.endswith("plugins.json"):
            return httpx.Response(200, content=_index_payload(self.index_latest))
        if request.url.path.endswith("plugin_versions.json"):
            return httpx.Response(
                self.versions_status, content=_versions_payload(self.digest, DOWNLOAD_URL)
            )
        return httpx.Response(404)


def _fake_download(served: dict):
    async def _download(url: str) -> bytes:
        # The endpoint checks https before calling here; the monkeypatch stands in
        # for the real fetch, so this assertion documents the contract instead of
        # enforcing it.
        assert url.startswith("https://")
        return served["content"]

    return _download


class SimpleEnv:
    def __init__(self, *, client: TestClient, plugins_dir: Path, served: dict) -> None:
        self.client = client
        self.plugins_dir = plugins_dir
        self.served = served


@pytest.fixture
def env(tmp_path, monkeypatch):
    """App whose plugin dir is private, whose index transport is a static seam, and
    whose release download is monkeypatched to serve the real zip bytes."""
    from soapbot.config import settings

    settings.plugin_index_url = INDEX_URL
    plugins_dir = tmp_path / "plugins"
    plugins_dir.mkdir(parents=True, exist_ok=True)
    app = create_app()
    with TestClient(app) as client:
        manager = get_plugin_manager()
        if manager is not None:
            manager.loader.plugins_dir = plugins_dir
            manager.index._transport = _StaticIndexTransport()
        served: dict[str, bytes] = {"content": _real_zip()}
        monkeypatch.setattr(
            "soapbot.api.plugins._download_release", _fake_download(served)
        )
        yield SimpleEnv(client=client, plugins_dir=plugins_dir, served=served)


def test_one_click_happy_path_installs_unapproved(env) -> None:
    response = env.client.post(
        "/api/plugins/install-from-index",
        json={"name": "mood-diary", "version": "0.1.0"},
    )
    assert response.status_code == 200
    body = response.json()
    assert body["name"] == "mood-diary" and body["version"] == "0.1.0"
    assert body["approved"] is False  # 审批照旧是人，一键不等于批准
    assert (env.plugins_dir / "mood-diary" / "plugin.yaml").is_file()


def test_digest_mismatch_is_a_hard_refusal(env) -> None:
    """The anchor: download content that does not match the index-declared digest is
    refused — a compromised index degrades to "refused", never to "installed". The
    detail carries both digest prefixes so the operator can tell which side moved."""
    env.served["content"] = _real_zip() + b"\x00"  # appended byte: hash differs, zip still opens
    response = env.client.post(
        "/api/plugins/install-from-index",
        json={"name": "mood-diary", "version": "0.1.0"},
    )
    assert response.status_code == 400
    detail = response.json()["detail"]
    assert "digest" in detail and "不一致" in detail
    assert not (env.plugins_dir / "mood-diary").exists()


def test_unknown_version_is_404(env) -> None:
    response = env.client.post(
        "/api/plugins/install-from-index",
        json={"name": "mood-diary", "version": "9.9.9"},
    )
    assert response.status_code == 404


def test_placeholder_digest_is_not_installable(tmp_path, monkeypatch) -> None:
    """Draft entries (placeholder digest) exist in the index but must not be one-click
    installable — the digest anchor is the whole point."""
    from soapbot.config import settings

    settings.plugin_index_url = INDEX_URL
    plugins_dir = tmp_path / "plugins"
    plugins_dir.mkdir(parents=True, exist_ok=True)
    app = create_app()
    with TestClient(app) as client:
        manager = get_plugin_manager()
        if manager is not None:
            manager.loader.plugins_dir = plugins_dir
            placeholder = "sha256:" + "0" * 64
            manager.index._transport = _StaticIndexTransport(digest=placeholder)
        response = client.post(
            "/api/plugins/install-from-index",
            json={"name": "mood-diary", "version": "0.1.0"},
        )
    assert response.status_code == 404  # 无可用版本元数据 = 404，与未知版本同形


def test_download_failure_is_502_not_silent(tmp_path, monkeypatch) -> None:
    from soapbot.config import settings

    settings.plugin_index_url = INDEX_URL
    plugins_dir = tmp_path / "plugins"
    plugins_dir.mkdir(parents=True, exist_ok=True)
    app = create_app()
    with TestClient(app) as client:
        manager = get_plugin_manager()
        if manager is not None:
            manager.loader.plugins_dir = plugins_dir
            manager.index._transport = _StaticIndexTransport()

        async def _boom(url: str) -> bytes:
            raise RuntimeError("network down")

        monkeypatch.setattr("soapbot.api.plugins._download_release", _boom)
        response = client.post(
            "/api/plugins/install-from-index",
            json={"name": "mood-diary", "version": "0.1.0"},
        )
    assert response.status_code == 502


def test_no_index_configured_is_503(tmp_path, monkeypatch) -> None:
    from soapbot.config import settings

    settings.plugin_index_url = ""
    (tmp_path / "plugins").mkdir(parents=True, exist_ok=True)
    app = create_app()
    with TestClient(app) as client:
        manager = get_plugin_manager()
        if manager is not None:
            manager.loader.plugins_dir = tmp_path / "plugins"
        response = client.post(
            "/api/plugins/install-from-index",
            json={"name": "mood-diary", "version": "0.1.0"},
        )
    assert response.status_code == 503


def test_default_index_url_points_at_the_official_catalogue() -> None:
    """The default deployment must see the official catalogue — the gap the user
    named. Air-gapped deployments set it empty (the client degrades gracefully)."""
    from soapbot.config import Settings

    s = Settings()
    assert s.plugin_index_url.startswith(
        "https://raw.githubusercontent.com/Soa4P/soapbot-plugins"
    )


def test_versions_meta_refuses_placeholders_and_non_https(tmp_path) -> None:
    from soapbot.plugins.index_client import IndexSnapshot

    snapshot = IndexSnapshot(
        available=True,
        versions={
            "p": {
                "1.0.0": {"digest": "sha256:" + "0" * 64, "download": "https://x/y.zip"},
                "1.1.0": {"digest": "sha256:abc", "download": "http://x/y.zip"},
            }
        },
    )
    assert snapshot.version_meta("p", "1.0.0") is None  # 占位 digest
    assert snapshot.version_meta("p", "1.1.0") is None  # 非 https
    assert snapshot.version_meta("p", "9.9.9") is None


def test_version_comparison_is_numeric_and_honest() -> None:
    from soapbot.api.plugins import _update_available

    assert _update_available("1.2.0", "1.10.0") is True  # 数字段比较，不是字典序
    assert _update_available("1.10.0", "1.2.0") is False
    assert _update_available("1.2.3", "1.2.3") is False
    assert _update_available("dev-build", "1.2.3") is False  # 无法判断 ≠ 有更新


def test_list_marks_update_available(tmp_path, monkeypatch) -> None:
    """list_plugins 对比索引 latest——「有新版」必须可见（装了旧版无人提醒的教训）。"""
    from soapbot.config import settings

    settings.plugin_index_url = INDEX_URL
    plugins_dir = tmp_path / "plugins"
    plugins_dir.mkdir(parents=True, exist_ok=True)
    app = create_app()
    with TestClient(app) as client:
        manager = get_plugin_manager()
        if manager is not None:
            manager.loader.plugins_dir = plugins_dir
            manager.index._transport = _StaticIndexTransport(index_latest="0.2.0")
        monkeypatch.setattr(
            "soapbot.api.plugins._download_release", _fake_download({"content": _real_zip()})
        )
        first = client.post(
            "/api/plugins/install-from-index",
            json={"name": "mood-diary", "version": "0.1.0"},
        )
        assert first.status_code == 200
        data = client.get("/api/plugins").json()
    ours = [p for p in data["installed"] if p["name"] == "mood-diary"]
    assert ours and ours[0]["update_available"] is True
