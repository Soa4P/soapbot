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

from soapbot.providers.base import (
    BaseProvider,
    CapabilitySlot,
    ChatRequest,
    ChatResponse,
    ProviderConfig,
    ProviderError,
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
        last_error: Exception | None = None

        for attempt in range(self.config.max_retries + 1):
            try:
                async with httpx.AsyncClient(timeout=self.config.timeout) as client:
                    resp = await client.post(url, json=self._payload(request), headers=self._headers())
                if resp.status_code >= 400:
                    raise ProviderError(
                        f"{self.kind} HTTP {resp.status_code}: {resp.text[:400]}"
                    )
                data = resp.json()
                return self._parse(data)
            except (httpx.HTTPError, ProviderError) as exc:
                last_error = exc
                logger.warning(
                    "provider %s chat attempt %s failed: %s", self.id, attempt + 1, exc
                )
        raise ProviderError(f"{self.kind} chat failed after retries: {last_error}")

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
        try:
            async with httpx.AsyncClient(timeout=self.config.timeout) as client:
                stream_ctx = client.stream(
                    "POST", url, json=payload, headers=self._headers()
                )
                async with stream_ctx as resp:
                    if resp.status_code >= 400:
                        body = await resp.aread()
                        raise ProviderError(
                            f"{self.kind} stream HTTP {resp.status_code}: {body[:300]!r}"
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

    async def embed(self, texts: list[str]) -> list[list[float]]:
        url = f"{self._base}/embeddings"
        payload = {
            "model": self.config.embed_model or self.config.model,
            "input": texts,
        }
        try:
            async with httpx.AsyncClient(timeout=self.config.timeout) as client:
                resp = await client.post(url, json=payload, headers=self._headers())
            if resp.status_code >= 400:
                raise ProviderError(f"{self.kind} embed HTTP {resp.status_code}")
            data = resp.json()
        except httpx.HTTPError as exc:
            raise ProviderError(f"{self.kind} embed failed: {exc}") from exc

        items = data.get("data") or []
        vectors = [list(map(float, it.get("embedding") or [])) for it in items]
        if len(vectors) != len(texts):
            raise ProviderError(
                f"{self.kind} embed count mismatch: {len(vectors)} != {len(texts)}"
            )
        return vectors
