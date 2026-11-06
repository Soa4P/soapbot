"""The HTTP error edge returns a stable code, not an exception's own words."""

from __future__ import annotations

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from soapbot.api.errors import (
    SAFE_MESSAGES,
    STATUS_BY_KIND,
    AppError,
    ConfigError,
    RateLimitError,
    UpstreamError,
    install_error_handlers,
    safe_detail,
)


def test_every_kind_has_a_status_and_a_safe_sentence() -> None:
    assert set(STATUS_BY_KIND) == set(SAFE_MESSAGES)
    for status in STATUS_BY_KIND.values():
        assert 400 <= status < 600


def test_safe_detail_does_not_echo_the_exception_text() -> None:
    secret = "/srv/soapbot/data/.env with api_key=sk-live-abcdef123456"
    detail = safe_detail(422, RuntimeError(secret), "test_origin")
    assert "/srv/soapbot" not in detail
    assert "sk-live" not in detail
    assert "无法" in detail or "请求" in detail


def test_safe_detail_names_only_whitelisted_categories() -> None:
    detail = safe_detail(400, RuntimeError("path traversal in archive: ../../evil.py"), "test")
    assert "traversal" in detail
    assert "../../evil.py" not in detail


def test_safe_detail_names_an_unset_variable_not_its_value() -> None:
    detail = safe_detail(
        422,
        RuntimeError("api_key references unset environment variable 'CONFIG_TEST_KEY'."),
        "config_write",
    )
    assert "CONFIG_TEST_KEY" in detail


def test_safe_detail_does_not_reflect_a_variable_name_from_a_plugin_error() -> None:
    detail = safe_detail(
        400,
        RuntimeError("environment variable 'SYSTEM_COMPROMISED_PAY_NOW' in archive"),
        "plugins",
    )
    assert "SYSTEM_COMPROMISED_PAY_NOW" not in detail


def test_app_error_handler_returns_a_stable_code() -> None:
    app = FastAPI()
    install_error_handlers(app)

    @app.get("/config")
    async def _config():
        raise ConfigError("internal: /srv/secret.yaml is broken")

    @app.get("/limit")
    async def _limit():
        raise RateLimitError("internal: bucket overflow")

    @app.get("/upstream")
    async def _upstream():
        raise UpstreamError("internal: provider said something with a path")

    client = TestClient(app, raise_server_exceptions=False)
    for path, kind in (("/config", "config"), ("/limit", "rate_limit"), ("/upstream", "upstream")):
        response = client.get(path)
        assert response.status_code == STATUS_BY_KIND[kind]
        body = response.json()
        assert body["code"] == f"err.{kind}"
        assert body["detail"] == SAFE_MESSAGES[kind]
        assert "internal:" not in body["detail"]


@pytest.mark.parametrize(
    "error",
    [ConfigError("x"), RateLimitError("x"), UpstreamError("x"), AppError("x")],
)
def test_every_app_error_subclass_is_mapped(error: AppError) -> None:
    assert error.kind in STATUS_BY_KIND


def test_strict_startup_aborts_on_a_broken_adapter(monkeypatch) -> None:
    """Fail-fast must be a behaviour, not just a setting that exists."""
    import asyncio
    from types import SimpleNamespace

    import soapbot.adapters
    import soapbot.core.config_files
    from soapbot.app import _attach_adapters
    from soapbot.config import settings

    monkeypatch.setattr(settings, "strict_startup", True)
    monkeypatch.setattr(
        soapbot.core.config_files,
        "load_adapters",
        lambda _path: [SimpleNamespace(enabled=True, kind="broken", options={})],
    )

    def _boom(*_args, **_kwargs):
        raise RuntimeError("adapter unavailable")

    monkeypatch.setattr(soapbot.adapters, "create", _boom)
    with pytest.raises(RuntimeError, match="strict startup refused"):
        asyncio.run(_attach_adapters(SimpleNamespace(add_adapter=lambda _a: None)))
