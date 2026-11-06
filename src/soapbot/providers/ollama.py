"""Ollama provider for fully local inference.

Uses ``/api/chat`` with ``images`` as bare base64 (Ollama's convention differs
from OpenAI's ``image_url`` part shape).
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


class OllamaProvider(BaseProvider):
    kind = "ollama"
    slots = frozenset({CapabilitySlot.CHAT, CapabilitySlot.STREAM, CapabilitySlot.VISION})

    def __init__(self, config: ProviderConfig) -> None:
        super().__init__(config)
        self._base = (config.base_url or "http://127.0.0.1:11434").rstrip("/")

    def _messages(self, request: ChatRequest) -> list[dict[str, Any]]:
        out: list[dict[str, Any]] = []
        for m in request.messages:
            if isinstance(m.content, str):
                out.append({"role": m.role, "content": m.content})
                continue
            text_parts: list[str] = []
            images: list[str] = []
            for part in m.content:
                if not isinstance(part, dict):
                    continue
                if part.get("type") == "text":
                    text_parts.append(str(part.get("text", "")))
                elif part.get("type") == "image_url":
                    url = ""
                    iu = part.get("image_url")
                    if isinstance(iu, dict):
                        url = str(iu.get("url", ""))
                    elif isinstance(iu, str):
                        url = iu
                    if url.startswith("data:"):
                        images.append(url.partition(",")[2])
            payload: dict[str, Any] = {"role": m.role, "content": "".join(text_parts)}
            if images:
                payload["images"] = images
            out.append(payload)
        return out

    async def chat(self, request: ChatRequest) -> ChatResponse:
        payload = {
            "model": request.model or self.config.model or "llama3.1",
            "messages": self._messages(request),
            "stream": False,
            "options": {"temperature": request.temperature, "num_predict": request.max_tokens},
        }
        url = f"{self._base}/api/chat"

        async def attempt() -> dict[str, Any]:
            resp = await self._request("POST", url, json=payload)
            if resp.status_code >= 400:
                raise ProviderError(
                    f"ollama HTTP {resp.status_code}",
                    status=resp.status_code,
                    retry_after=retry_after_of(resp),
                )
            return resp.json()

        try:
            data = await self._with_retry(attempt, what="chat")
        except ProviderError:
            raise
        except httpx.HTTPError as exc:
            raise ProviderError(f"ollama request failed: {exc}") from exc

        message = data.get("message") or {}
        return ChatResponse(
            content=str(message.get("content", "")),
            model=str(data.get("model", "")),
            prompt_tokens=int(data.get("prompt_eval_count", 0) or 0),
            completion_tokens=int(data.get("eval_count", 0) or 0),
            finish_reason=str(data.get("done_reason", "")),
            provider=self.id,
            raw=data,
        )

    async def stream(self, request: ChatRequest) -> AsyncIterator[str]:
        import json

        payload = {
            "model": request.model or self.config.model or "llama3.1",
            "messages": self._messages(request),
            "stream": True,
            "options": {"temperature": request.temperature, "num_predict": request.max_tokens},
        }
        url = f"{self._base}/api/chat"

        async with outbound_client() as client:
            try:
                stream_ctx = client.stream("POST", url, json=payload, timeout=self._timeout())
                resp = await stream_ctx.__aenter__()
            except httpx.HTTPError as exc:
                raise ProviderError(f"ollama stream failed: {exc}") from exc

            try:
                if resp.status_code >= 400:
                    body = await resp.aread()
                    raise ProviderError(
                        f"ollama stream HTTP {resp.status_code}: {body[:200]!r}",
                        status=resp.status_code,
                        retry_after=retry_after_of(resp),
                    )
                async for line in resp.aiter_lines():
                    if not line.strip():
                        continue
                    try:
                        obj = json.loads(line)
                    except json.JSONDecodeError:
                        continue
                    piece = (obj.get("message") or {}).get("content")
                    if piece:
                        yield str(piece)
                    if obj.get("done"):
                        break
            except httpx.HTTPError as exc:
                raise ProviderError(f"ollama stream failed: {exc}") from exc
            finally:
                await resp.aclose()
                await stream_ctx.__aexit__(None, None, None)
