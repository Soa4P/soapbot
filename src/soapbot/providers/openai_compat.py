"""OpenAI-compatible provider.

One implementation covers a large surface: OpenAI, DeepSeek, Moonshot (Kimi),
Qwen/DashScope compatible mode, Zhipu, SiliconFlow, and self-hosted relays.
If it speaks ``POST /chat/completions`` with a Bearer token, this class works.
"""

from __future__ import annotations

import logging
from collections.abc import AsyncIterator
from typing import Any

import httpx

from soapbot.net import outbound_client
from soapbot.providers.base import (
    BaseProvider,
    CapabilitySlot,
    ChatRequest,
    ChatResponse,
    ProviderConfig,
    ProviderError,
    retry_after_of,
)

logger = logging.getLogger(__name__)


class OpenAICompatProvider(BaseProvider):
    kind = "openai_compat"
    slots = frozenset(
        {CapabilitySlot.CHAT, CapabilitySlot.STREAM, CapabilitySlot.VISION, CapabilitySlot.EMBED}
    )

    def __init__(self, config: ProviderConfig) -> None:
        super().__init__(config)
        self._base = (config.base_url or "https://api.openai.com/v1").rstrip("/")

    def _headers(self) -> dict[str, str]:
        headers = {"Content-Type": "application/json"}
        if self.config.api_key:
            headers["Authorization"] = f"Bearer {self.config.api_key}"
        return headers

    def _payload(self, request: ChatRequest) -> dict[str, Any]:
        payload: dict[str, Any] = {
            "model": request.model or self.config.model,
            "messages": [m.to_openai() for m in request.messages],
            "temperature": request.temperature,
            "max_tokens": request.max_tokens,
        }
        if request.tools:
            payload["tools"] = request.tools
        payload.update(request.extra)
        return payload

    async def chat(self, request: ChatRequest) -> ChatResponse:
        url = f"{self._base}/chat/completions"
        payload = self._payload(request)
        headers = self._headers()

        async def attempt() -> ChatResponse:
            resp = await self._request("POST", url, json=payload, headers=headers)
            if resp.status_code >= 400:
                # The status travels on the exception so the retry policy can tell a
                # 503 (try again) from a 400 (do not).
                raise ProviderError(
                    # Type-only summary. The response body can echo the prompt, the
                    # key or another user's data; it used to land in last_error,
                    # which the admin API returns and the log ring keeps.
                    f"{self.kind} HTTP {resp.status_code}",
                    status=resp.status_code,
                    retry_after=retry_after_of(resp),
                )
            return self._parse(resp.json())

        try:
            return await self._with_retry(attempt, what="chat")
        except ProviderError:
            raise
        except httpx.HTTPError as exc:
            raise ProviderError(f"{self.kind} chat failed: {exc}") from exc
        except ValueError as exc:  # malformed JSON from a relay
            raise ProviderError(f"{self.kind} chat returned invalid JSON: {exc}") from exc

    def _parse(self, data: dict[str, Any]) -> ChatResponse:
        choices = data.get("choices") or []
        if not choices:
            raise ProviderError(f"{self.kind} returned no choices")
        choice = choices[0]
        message = choice.get("message") or {}
        content = message.get("content")
        if isinstance(content, list):
            content = "".join(
                str(p.get("text", "")) for p in content if isinstance(p, dict)
            )
        usage = data.get("usage") or {}
        return ChatResponse(
            content=str(content or ""),
            model=str(data.get("model", "")),
            prompt_tokens=int(usage.get("prompt_tokens", 0) or 0),
            completion_tokens=int(usage.get("completion_tokens", 0) or 0),
            tool_calls=list(message.get("tool_calls") or []),
            finish_reason=str(choice.get("finish_reason", "")),
            provider=self.id,
            raw=data,
        )

    async def stream(self, request: ChatRequest) -> AsyncIterator[str]:
        import json

        url = f"{self._base}/chat/completions"
        payload = self._payload(request)
        payload["stream"] = True
        headers = self._headers()

        async with outbound_client() as client:
            # The response is closed explicitly in ``finally`` rather than by an
            # ``async with`` around the body. The difference matters when the consumer
            # stops early — a caller that breaks out of ``async for``, or a reply that
            # gets cancelled mid-sentence. In that case the generator is closed by
            # ``GeneratorExit``, which unwinds ``finally`` but does *not* run the body
            # of an ``async with`` that has not been entered yet... and more to the
            # point, a half-read response left open holds its socket out of the pool
            # until the server times it out. Closing here returns it immediately.
            try:
                # ``timeout`` is not optional here. Without it the stream inherits the
                # process-wide read timeout instead of the budget this provider was
                # configured with, so a provider told to give up after 20 s would keep
                # a dead stream open for 60. Streaming is the chat hot path, which
                # makes this the one place where the omission is most expensive.
                stream_ctx = client.stream(
                    "POST", url, json=payload, headers=headers, timeout=self._timeout()
                )
                resp = await stream_ctx.__aenter__()
            except httpx.HTTPError as exc:
                raise ProviderError(f"{self.kind} stream failed: {exc}") from exc

            try:
                if resp.status_code >= 400:
                    body = await resp.aread()
                    raise ProviderError(
                        f"{self.kind} stream HTTP {resp.status_code}: {body[:300]!r}",
                        status=resp.status_code,
                        retry_after=retry_after_of(resp),
                    )
                async for line in resp.aiter_lines():
                    if not line or not line.startswith("data:"):
                        continue
                    chunk = line[5:].strip()
                    if chunk == "[DONE]":
                        break
                    try:
                        obj = json.loads(chunk)
                    except json.JSONDecodeError:
                        continue
                    for choice in obj.get("choices") or []:
                        delta = choice.get("delta") or {}
                        piece = delta.get("content")
                        if piece:
                            yield str(piece)
            except httpx.HTTPError as exc:
                raise ProviderError(f"{self.kind} stream failed: {exc}") from exc
            finally:
                # ``aclose`` is idempotent; calling it after a clean [DONE] is free.
                await resp.aclose()
                await stream_ctx.__aexit__(None, None, None)

    async def embed(self, texts: list[str]) -> list[list[float]]:
        url = f"{self._base}/embeddings"
        payload = {
            "model": self.config.embed_model or self.config.model,
            "input": texts,
        }
        headers = self._headers()

        async def attempt() -> dict[str, Any]:
            resp = await self._request("POST", url, json=payload, headers=headers)
            if resp.status_code >= 400:
                raise ProviderError(
                    f"{self.kind} embed HTTP {resp.status_code}",
                    status=resp.status_code,
                    retry_after=retry_after_of(resp),
                )
            return resp.json()

        try:
            data = await self._with_retry(attempt, what="embed")
        except ProviderError:
            raise
        except httpx.HTTPError as exc:
            raise ProviderError(f"{self.kind} embed failed: {exc}") from exc

        items = data.get("data") or []
        vectors = [list(map(float, it.get("embedding") or [])) for it in items]
        if len(vectors) != len(texts):
            raise ProviderError(
                f"{self.kind} embed count mismatch: {len(vectors)} != {len(texts)}"
            )
        return vectors
