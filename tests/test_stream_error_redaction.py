"""S-MSG-05: a streaming provider error must carry the status, never the body.

``last_error`` is written from the exception text and served to MEMBER via
``GET /api/providers``; a half-trusted relay can echo the prompt, the API key or
another tenant's data in a 4xx/5xx body. The non-streaming path was already fixed
this way; these tests pin the streaming paths so they cannot drift back.
"""
from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

import pytest

from soapbot.providers.base import ChatRequest, ProviderConfig, ProviderError

# Built at runtime: this file must not contain anything shaped like a real key.
_ECHO_MARK = "RELAY-ECHO-" + "9f3a"
SECRET_BODY = '{"error":"invalid key sk-live-' + _ECHO_MARK + ' prompt=<system>内部提示词'


class _FakeResponse:
    def __init__(self) -> None:
        self.status_code = 500
        self.headers: dict[str, str] = {}

    async def aread(self) -> bytes:
        return SECRET_BODY.encode()

    async def aclose(self) -> None:
        return None

    async def aiter_lines(self):  # pragma: no cover - never reached on error
        yield ""


class _FakeStreamCtx:
    async def __aenter__(self):
        return _FakeResponse()

    async def __aexit__(self, *exc):
        return False


class _FakeClient:
    def __init__(self, *a, **k) -> None:
        pass

    def stream(self, *a, **k):
        return _FakeStreamCtx()

    async def __aenter__(self):
        return self

    async def __aexit__(self, *exc):
        return False


@pytest.fixture
def _patch(monkeypatch):
    import soapbot.providers.openai_compat as openai_mod

    monkeypatch.setattr(openai_mod, "outbound_client", lambda **k: _FakeClient())
    yield


def _config(kind: str) -> ProviderConfig:
    return ProviderConfig(
        id="relay", kind=kind, label="relay", base_url="https://relay.example/v1",
        api_key="", model="m",
    )


async def _drain(agen) -> None:
    async for _ in agen:
        pass


async def test_openai_stream_error_carries_no_body(_patch) -> None:
    from soapbot.providers.openai_compat import OpenAICompatProvider

    provider = OpenAICompatProvider(_config("openai_compat"))
    with pytest.raises(ProviderError) as caught:
        await _drain(provider.stream(ChatRequest(messages=[], model="m")))
    text = str(caught.value)
    assert "500" in text
    # The relay's echo (and the prompt inside it) must not ride along.
    assert _ECHO_MARK not in text
    assert "内部提示词" not in text


async def test_ollama_stream_error_carries_no_body(_patch) -> None:
    import soapbot.providers.ollama as ollama_mod

    with pytest.MonkeyPatch.context() as monkey:
        monkey.setattr(ollama_mod, "outbound_client", lambda **k: _FakeClient())
        provider = ollama_mod.OllamaProvider(_config("ollama"))
        with pytest.raises(ProviderError) as caught:
            await _drain(provider.stream(ChatRequest(messages=[], model="m")))
        text = str(caught.value)
        assert "500" in text
        assert _ECHO_MARK not in text
