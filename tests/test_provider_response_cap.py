"""Provider responses are read under a ceiling (S-MSG-11).

The interesting case is not "a large body" — it is a *small* body that expands. A
``Content-Length`` check sees the compressed size; ``resp.json()`` sees the expanded
one. These tests build the compressed case explicitly, because that is the shape a
half-trusted relay would use and the shape a naive size check misses.
"""

from __future__ import annotations

import gzip
import json
from collections.abc import AsyncIterator
from typing import Any

import httpx
import pytest

from soapbot.net import (
    DRAIN_LIMIT_BYTES,
    MAX_RESPONSE_BYTES,
    ResponseTooLargeError,
    drain_capped,
    read_capped,
)
from soapbot.net import client as net_client
from soapbot.providers.base import ProviderConfig, ProviderError
from soapbot.providers.openai_compat import OpenAICompatProvider

BIG_PAYLOAD = json.dumps(
    {"choices": [{"message": {"content": "x" * (MAX_RESPONSE_BYTES + 4096)}}]}
)

#: Compresses to a few kilobytes: far under any Content-Length check, far over the cap.
BOMB = gzip.compress(BIG_PAYLOAD.encode("utf-8"))


def _provider_with(monkeypatch, handler) -> OpenAICompatProvider:
    """Install a mock-transport client as the shared one, restored by monkeypatch.

    ``monkeypatch`` rather than a plain assignment: the registry is process-global, and
    leaving a fake in place made unrelated provider tests fail with "client has been
    closed" depending on file order.
    """
    client = httpx.AsyncClient(transport=httpx.MockTransport(handler), timeout=5.0)

    class _Registry:
        def get(self) -> httpx.AsyncClient:
            return client

        async def aclose(self) -> None:
            await client.aclose()

    monkeypatch.setattr(net_client, "_registry", _Registry())
    return OpenAICompatProvider(
        ProviderConfig(
            id="relay", kind="openai", api_key="k", model="m", base_url="https://x"
        )
    )


@pytest.fixture(autouse=True)
async def _clean_pool():
    yield
    await net_client.reset_outbound()


async def test_a_compressed_body_is_capped_after_decompression(monkeypatch) -> None:
    """The cap applies to decoded bytes, which is why Content-Length is not enough."""

    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(
            200,
            headers={"Content-Encoding": "gzip", "Content-Length": str(len(BOMB))},
            content=BOMB,
        )

    provider = _provider_with(monkeypatch, handler)
    with pytest.raises(ProviderError, match="too large"):
        await provider._request("POST", "https://x/chat/completions", json={})


async def test_a_normal_response_still_parses(monkeypatch) -> None:
    body = json.dumps({"choices": [{"message": {"content": "hi"}}], "model": "m"}).encode()

    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(200, content=body)

    provider = _provider_with(monkeypatch, handler)
    reply = await provider._request("POST", "https://x/chat/completions", json={})
    assert reply.status_code == 200
    assert reply.json()["choices"][0]["message"]["content"] == "hi"


async def test_read_capped_reports_the_limit_it_hit() -> None:
    async def stream() -> AsyncIterator[bytes]:
        yield b"y" * 100

    streamed = httpx.Response(200, content=stream())
    with pytest.raises(ResponseTooLargeError) as caught:
        await read_capped(streamed, limit=10)
    assert caught.value.limit == 10


async def test_draining_an_error_body_stops_at_the_cap() -> None:
    """The error path used to read the whole body just to reuse the socket.

    A relay answering 500 with an endless body held the connection — and this process's
    memory — for as long as it kept writing. The drain now stops after a fixed size, so
    the generator is never exhausted.
    """
    pulled = 0

    async def endless() -> AsyncIterator[bytes]:
        nonlocal pulled
        while True:
            pulled += 1
            yield b"z" * 8192

    response = httpx.Response(500, content=endless())
    await drain_capped(response)

    # It stopped: the loop above would never finish otherwise. And it stopped near the
    # cap rather than after "a few" chunks — bounded by the limit plus one chunk.
    assert pulled <= (DRAIN_LIMIT_BYTES // 8192) + 1


async def test_streaming_deltas_are_not_buffered(monkeypatch) -> None:
    """The streaming path is intentionally outside the cap: it never holds the body.

    Asserting this keeps a later "add the cap everywhere" edit from wrapping the whole
    SSE stream in memory, which would defeat the reason streaming exists.
    """
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(
            200, content=b'data: {"choices":[{"delta":{"content":"a"}}]}\n\ndata: [DONE]\n\n'
        )

    provider = _provider_with(monkeypatch, handler)
    pieces: list[str] = []
    async for piece in provider.stream(_req()):
        pieces.append(piece)
    assert pieces == ["a"]


def _req() -> Any:
    from soapbot.providers.base import ChatMessage, ChatRequest

    return ChatRequest(messages=[ChatMessage(role="user", content="hi")])
