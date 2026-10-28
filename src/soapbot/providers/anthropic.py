"""Anthropic Messages API provider.

Notable differences from OpenAI shape:
- system prompt is a top-level ``system`` field, not a message
- images use ``source: {type: base64|url}`` blocks
- auth header is ``x-api-key`` plus ``anthropic-version``
"""

from __future__ import annotations

import logging
from typing import Any

import httpx

from soapbot.providers.base import (
    BaseProvider,
    CapabilitySlot,
    ChatMessage,
    ChatRequest,
    ChatResponse,
    ProviderConfig,
    ProviderError,
)

logger = logging.getLogger(__name__)

_ANTHROPIC_VERSION = "2023-06-01"


class AnthropicProvider(BaseProvider):
    kind = "anthropic"
    slots = frozenset({CapabilitySlot.CHAT, CapabilitySlot.VISION})

    def __init__(self, config: ProviderConfig) -> None:
        super().__init__(config)
        self._base = (config.base_url or "https://api.anthropic.com/v1").rstrip("/")

    def _headers(self) -> dict[str, str]:
        return {
            "content-type": "application/json",
            "x-api-key": self.config.api_key,
            "anthropic-version": _ANTHROPIC_VERSION,
        }

    def _convert(self, messages: list[ChatMessage]) -> tuple[str, list[dict[str, Any]]]:
        system_parts: list[str] = []
        converted: list[dict[str, Any]] = []
        for m in messages:
            if m.role == "system":
                system_parts.append(m.text())
                continue
            converted.append({"role": m.role, "content": _to_anthropic_content(m)})
        return "\n\n".join(p for p in system_parts if p), converted

    async def chat(self, request: ChatRequest) -> ChatResponse:
        system, messages = self._convert(request.messages)
        payload: dict[str, Any] = {
            "model": request.model or self.config.model,
            "max_tokens": request.max_tokens,
            "temperature": request.temperature,
            "messages": messages,
        }
        if system:
            payload["system"] = system
        payload.update(request.extra)

        url = f"{self._base}/messages"
        try:
            async with httpx.AsyncClient(timeout=self.config.timeout) as client:
                resp = await client.post(url, json=payload, headers=self._headers())
            if resp.status_code >= 400:
                raise ProviderError(f"anthropic HTTP {resp.status_code}: {resp.text[:400]}")
            data = resp.json()
        except httpx.HTTPError as exc:
            raise ProviderError(f"anthropic request failed: {exc}") from exc

        blocks = data.get("content") or []
        text = "".join(
            str(b.get("text", "")) for b in blocks if isinstance(b, dict) and b.get("type") == "text"
        )
        usage = data.get("usage") or {}
        return ChatResponse(
            content=text,
            model=str(data.get("model", "")),
            prompt_tokens=int(usage.get("input_tokens", 0) or 0),
            completion_tokens=int(usage.get("output_tokens", 0) or 0),
            finish_reason=str(data.get("stop_reason", "")),
            provider=self.id,
            raw=data,
        )


def _to_anthropic_content(m: ChatMessage) -> Any:
    if isinstance(m.content, str):
        return m.content
    parts: list[dict[str, Any]] = []
    for part in m.content:
        if not isinstance(part, dict):
            continue
        ptype = part.get("type")
        if ptype == "text":
            parts.append({"type": "text", "text": str(part.get("text", ""))})
        elif ptype == "image_url":
            url = ""
            image_url = part.get("image_url")
            if isinstance(image_url, dict):
                url = str(image_url.get("url", ""))
            elif isinstance(image_url, str):
                url = image_url
            if url.startswith("data:"):
                header, _, b64 = url.partition(",")
                media_type = "image/png"
                if ";" in header:
                    media_type = header.split(":", 1)[1].split(";", 1)[0] or "image/png"
                parts.append(
                    {
                        "type": "image",
                        "source": {"type": "base64", "media_type": media_type, "data": b64},
                    }
                )
            elif url:
                parts.append({"type": "image", "source": {"type": "url", "url": url}})
    return parts or ""
