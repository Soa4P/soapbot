"""Ollama provider for fully local inference.

Uses ``/api/chat`` with ``images`` as bare base64 (Ollama's convention differs
from OpenAI's ``image_url`` part shape).
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
        try:
            async with httpx.AsyncClient(timeout=self.config.timeout) as client:
                resp = await client.post(url, json=payload)
            if resp.status_code >= 400:
                raise ProviderError(f"ollama HTTP {resp.status_code}: {resp.text[:300]}")
            data = resp.json()
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
        try:
            async with httpx.AsyncClient(timeout=self.config.timeout) as client:
                stream_ctx = client.stream("POST", url, json=payload)
                async with stream_ctx as resp:
                    if resp.status_code >= 400:
                        body = await resp.aread()
                        raise ProviderError(f"ollama stream HTTP {resp.status_code}: {body[:200]!r}")
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
