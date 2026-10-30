"""The three vendor shapes nothing was watching.

``scripts/check_test_gaps.py`` lists modules no test names. Anthropic, Gemini and Ollama
were all on that list while being the three places where a payload gets translated into
somebody else's schema — the kind of code that keeps working perfectly until the day it
silently stops, because a wrong field name is not an exception.

Each provider builds its own ``httpx.AsyncClient`` inline, so there is no client to
inject. These tests patch the name in the module's namespace and hand it a mock
transport: request building, headers and response parsing all stay on the hook, only the
socket is replaced.
"""

from __future__ import annotations

import json
from types import SimpleNamespace
from typing import Any

import httpx
import pytest

from soapbot.providers import anthropic as anthropic_module
from soapbot.providers import gemini as gemini_module
from soapbot.providers import ollama as ollama_module
from soapbot.providers.anthropic import AnthropicProvider
from soapbot.providers.base import ChatMessage, ChatRequest, ProviderConfig, ProviderError
from soapbot.providers.gemini import GeminiProvider
from soapbot.providers.ollama import OllamaProvider

DATA_URL = "data:image/jpeg;base64,QUJD"


def _route(monkeypatch: pytest.MonkeyPatch, module: Any, handler: Any) -> list[dict[str, Any]]:
    """Send the provider's HTTP through ``handler`` and record what it was asked.

    The module-level ``httpx`` name is replaced by a shim carrying the two attributes the
    providers use. That keeps the real ``AsyncClient`` (and therefore the real request
    serialisation) while removing the socket.
    """
    seen: list[dict[str, Any]] = []
    real = httpx.AsyncClient

    def handler_wrapper(request: httpx.Request) -> httpx.Response:
        seen.append(
            {
                "method": request.method,
                "url": str(request.url),
                "headers": dict(request.headers),
                "json": json.loads(request.content) if request.content else None,
            }
        )
        return handler(request)

    def factory(*args: Any, **kwargs: Any) -> httpx.AsyncClient:
        kwargs.pop("timeout", None)
        return real(*args, transport=httpx.MockTransport(handler_wrapper), timeout=5.0, **kwargs)

    monkeypatch.setattr(
        module,
        "httpx",
        SimpleNamespace(AsyncClient=factory, HTTPError=httpx.HTTPError),
    )
    return seen


def _config(kind: str, **overrides: Any) -> ProviderConfig:
    base = {
        "id": kind,
        "kind": kind,
        "api_key": "sk-test",
        "model": "some-model",
        "base_url": "",
    }
    base.update(overrides)
    return ProviderConfig(**base)


# ------------------------------------------------------------------- anthropic


async def test_anthropic_moves_the_system_prompt_out_of_the_message_list(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """The Messages API rejects a ``system`` role in ``messages``.

    Passing it through unchanged looks correct in the request we build and earns a 400
    from the vendor, which is the least informative place to find out.
    """

    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(
            200,
            json={
                "model": "claude-3",
                "stop_reason": "end_turn",
                "content": [{"type": "text", "text": "hello "}, {"type": "text", "text": "there"}],
                "usage": {"input_tokens": 11, "output_tokens": 7},
            },
        )

    seen = _route(monkeypatch, anthropic_module, handler)
    provider = AnthropicProvider(_config("anthropic", api_key="sk-anthropic"))

    reply = await provider.chat(
        ChatRequest(
            messages=[
                ChatMessage(role="system", content="be brief"),
                ChatMessage(role="user", content="hi"),
            ]
        )
    )

    payload = seen[0]["json"]
    assert payload["system"] == "be brief"
    assert [m["role"] for m in payload["messages"]] == ["user"]
    # Auth is a header here, not a bearer token, and the version header is mandatory.
    assert seen[0]["headers"]["x-api-key"] == "sk-anthropic"
    assert seen[0]["headers"]["anthropic-version"]

    # Text blocks are concatenated, not overwritten: a reply split across blocks is
    # normal, and keeping only the last one truncates it silently.
    assert reply.content == "hello there"
    assert (reply.prompt_tokens, reply.completion_tokens) == (11, 7)
    assert reply.finish_reason == "end_turn"


async def test_anthropic_converts_a_data_url_into_a_base64_block(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(200, json={"content": [], "usage": {}})

    seen = _route(monkeypatch, anthropic_module, handler)
    provider = AnthropicProvider(_config("anthropic"))

    await provider.chat(
        ChatRequest(
            messages=[
                ChatMessage(
                    role="user",
                    content=[
                        {"type": "text", "text": "what is this"},
                        {"type": "image_url", "image_url": {"url": DATA_URL}},
                    ],
                )
            ]
        )
    )

    parts = seen[0]["json"]["messages"][0]["content"]
    assert parts[0] == {"type": "text", "text": "what is this"}
    assert parts[1] == {
        "type": "image",
        "source": {"type": "base64", "media_type": "image/jpeg", "data": "QUJD"},
    }


# ---------------------------------------------------------------------- ollama


async def test_ollama_sends_bare_base64_without_the_data_prefix(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Ollama's ``images`` array takes raw base64, not a data URL.

    Sending the URL through unchanged is not an error on this side and not a useful one
    on theirs — the model simply receives a broken image.
    """

    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(200, json={"message": {"content": "ok"}, "model": "llama3.1"})

    seen = _route(monkeypatch, ollama_module, handler)
    # No model anywhere: the provider has to fall back to its own default rather than
    # sending an empty string, which the server answers with a 400.
    provider = OllamaProvider(_config("ollama", base_url="http://127.0.0.1:11434", model=""))

    await provider.chat(
        ChatRequest(
            messages=[
                ChatMessage(
                    role="user",
                    content=[
                        {"type": "text", "text": "look"},
                        {"type": "image_url", "image_url": {"url": DATA_URL}},
                    ],
                )
            ],
            model="",
        )
    )

    payload = seen[0]["json"]
    assert payload["messages"][0]["images"] == ["QUJD"]
    assert payload["messages"][0]["content"] == "look"
    assert payload["model"] == "llama3.1"
    assert seen[0]["url"] == "http://127.0.0.1:11434/api/chat"


async def test_ollama_maps_its_own_token_field_names(monkeypatch: pytest.MonkeyPatch) -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(
            200,
            json={
                "model": "llama3.1",
                "done_reason": "stop",
                "prompt_eval_count": 21,
                "eval_count": 9,
                "message": {"content": "sure"},
            },
        )

    _route(monkeypatch, ollama_module, handler)
    provider = OllamaProvider(_config("ollama"))

    reply = await provider.chat(ChatRequest(messages=[ChatMessage(role="user", content="hi")]))

    assert reply.content == "sure"
    assert (reply.prompt_tokens, reply.completion_tokens) == (21, 9)
    assert reply.finish_reason == "stop"


async def test_ollama_stream_stops_at_done_rather_than_at_eof(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """The final ``done`` frame carries no text, and servers may keep the pipe open.

    Reading until EOF would hang a reply that is already complete — the failure mode
    shows up as a turn that never ends rather than as an error.
    """
    body = "\n".join(
        [
            json.dumps({"message": {"content": "a"}, "done": False}),
            json.dumps({"message": {"content": "b"}, "done": False}),
            json.dumps({"message": {"content": ""}, "done": True}),
            json.dumps({"message": {"content": "never"}, "done": False}),
        ]
    )

    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(200, content=body.encode("utf-8"))

    _route(monkeypatch, ollama_module, handler)
    provider = OllamaProvider(_config("ollama"))

    pieces = [
        piece
        async for piece in provider.stream(
            ChatRequest(messages=[ChatMessage(role="user", content="hi")])
        )
    ]

    assert pieces == ["a", "b"]


# ---------------------------------------------------------------------- gemini


async def test_gemini_renames_roles_and_hides_the_system_turn(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Gemini has no ``assistant`` role and no system message.

    Mapping is ``user``/``model`` plus a separate ``systemInstruction``; getting it wrong
    produces a 400 that names the offending role and nothing about the real cause.
    """

    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(
            200,
            json={
                "candidates": [
                    {"content": {"parts": [{"text": "hi "}, {"text": "back"}]}, "finishReason": "STOP"}
                ],
                "usageMetadata": {"promptTokenCount": 4, "candidatesTokenCount": 2},
            },
        )

    seen = _route(monkeypatch, gemini_module, handler)
    provider = GeminiProvider(_config("gemini", api_key="goog"))

    reply = await provider.chat(
        ChatRequest(
            messages=[
                ChatMessage(role="system", content="be nice"),
                ChatMessage(role="user", content="hello"),
                ChatMessage(role="assistant", content="hello yourself"),
            ]
        )
    )

    payload = seen[0]["json"]
    assert payload["systemInstruction"] == {"parts": [{"text": "be nice"}]}
    assert [c["role"] for c in payload["contents"]] == ["user", "model"]
    assert payload["contents"][0]["parts"] == [{"text": "hello"}]
    assert ":generateContent" in seen[0]["url"]
    assert seen[0]["headers"]["x-goog-api-key"] == "goog"

    assert reply.content == "hi back"
    assert (reply.prompt_tokens, reply.completion_tokens) == (4, 2)
    assert reply.finish_reason == "STOP"


async def test_a_vendor_error_becomes_a_provider_error_with_the_status(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """The router fails over on ``ProviderError`` and on nothing else.

    A raw ``httpx`` exception escaping here would take down the turn instead of trying
    the next provider — the whole failover design rests on this translation.
    """

    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(429, text="slow down")

    _route(monkeypatch, anthropic_module, handler)
    provider = AnthropicProvider(_config("anthropic"))

    with pytest.raises(ProviderError, match="429"):
        await provider.chat(ChatRequest(messages=[ChatMessage(role="user", content="hi")]))
