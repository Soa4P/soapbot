"""Release-download redirect discipline (validated single hop).

GitHub 发布包下载必然 302（github.com/releases/download →
objects.githubusercontent.com），盲跟 Location 是 SSRF 面，一刀切禁跟又装不了
任何发布包。契约：**验证后单跳**——Location 必须 https、主机命中 GitHub 资产
白名单、不带凭据；白名单外的目标一律拒绝。
"""

from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

import pytest

from soapbot.api.plugins import _redirect_target_allowed


def test_github_asset_redirect_is_allowed() -> None:
    assert _redirect_target_allowed(
        "https://objects.githubusercontent.com/some/path/pkg-0.1.0.zip?token=x")
    assert _redirect_target_allowed(
        "https://release-assets.githubusercontent.com/path/pkg.zip")


def test_non_github_or_insecure_redirects_are_refused() -> None:
    # 内网/环回/任意第三方主机——SSRF 面的实体
    assert not _redirect_target_allowed("http://objects.githubusercontent.com/x")
    assert not _redirect_target_allowed("https://evil.example/pkg.zip")
    assert not _redirect_target_allowed("https://127.0.0.1/pkg.zip")
    assert not _redirect_target_allowed("https://169.254.169.254/latest/meta-data")
    # 凭据内嵌
    assert not _redirect_target_allowed(
        "https://user:pass@objects.githubusercontent.com/x")


def test_garbage_location_is_refused() -> None:
    assert not _redirect_target_allowed("")
    assert not _redirect_target_allowed("not a url \x00")


@pytest.mark.asyncio
async def test_download_follows_one_validated_hop(monkeypatch, tmp_path) -> None:
    """301/302 后只跟一跳，且跳前先过白名单；非 200 照旧抛错。"""
    import httpx

    from soapbot.api.plugins import _download_release

    seen: list[str] = []

    def handler(request: httpx.Request) -> httpx.Response:
        seen.append(str(request.url))
        if str(request.url).startswith("https://github.com/"):
            return httpx.Response(302, headers={
                "location": "https://objects.githubusercontent.com/pkg.zip"})
        return httpx.Response(200, content=b"zip-bytes")

    transport = httpx.MockTransport(handler)
    real_client = httpx.AsyncClient

    class _FakeClient:
        def __init__(self, *a, **k):
            self._client = real_client(transport=transport)

        async def __aenter__(self):
            return self._client

        async def __aexit__(self, *exc):
            await self._client.aclose()

    monkeypatch.setattr("httpx.AsyncClient", _FakeClient)
    data = await _download_release("https://github.com/Soa4P/soapbot-plugins/releases/download/x-0.1.0/x-0.1.0.zip")
    assert data == b"zip-bytes"
    assert len(seen) == 2  # 一跳，且只有一跳


@pytest.mark.asyncio
async def test_download_refuses_non_allowlisted_redirect(monkeypatch) -> None:
    import httpx

    from soapbot.api.plugins import _download_release

    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(302, headers={"location": "https://evil.example/pkg.zip"})

    transport = httpx.MockTransport(handler)
    real_client = httpx.AsyncClient

    class _FakeClient:
        def __init__(self, *a, **k):
            self._client = real_client(transport=transport)

        async def __aenter__(self):
            return self._client

        async def __aexit__(self, *exc):
            await self._client.aclose()

    monkeypatch.setattr("httpx.AsyncClient", _FakeClient)
    with pytest.raises(RuntimeError, match="non-allowlisted"):
        await _download_release("https://github.com/Soa4P/soapbot-plugins/releases/download/x/x.zip")
