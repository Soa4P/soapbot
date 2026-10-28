"""Google Gemini provider (generateContent REST)."""

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

_DEFAULT_BASE = "https://generativelanguage.googleapis.com/v1beta"


class GeminiProvider(BaseProvider):
    kind = "gemini"
    slots = frozenset({CapabilitySlot.CHAT, CapabilitySlot.VISION, CapabilitySlot.EMBED})

    def __init__(self, config: ProviderConfig) -> None:
        super().__init__(config)
        self._base = (config.base_url or _DEFAULT_BASE).rstrip("/")

    def _convert(
        self, messages: list[ChatMessage]
    ) -> tuple[dict[str, Any], list[dict[str, Any]]]:
        system_text = ""
        contents: list[dict[str, Any]] = []
        for m in messages:
            if m.role == "system":
                system_text = m.text() if not system_text else f"{system_text}\n\n{m.text()}"
                continue
            role = "user" if m.role == "user" else "model"
            contents.append({"role": role, "parts": _to_parts(m)})
        system = {"parts": [{"text": system_text}]} if system_text else {}
        return system, contents

    async def chat(self, request: ChatRequest) -> ChatResponse:
        system, contents = self._convert(request.messages)
        payload: dict[str, Any] = {
            "contents": contents,
            "generationConfig": {
                "temperature": request.temperature,
                "maxOutputTokens": request.max_tokens,
            },
        }
        if system:
            payload["systemInstruction"] = system
        payload.update(request.extra)

        model = request.model or self.config.model or "gemini-2.0-flash"
        url = f"{self._base}/models/{model}:generateContent"
        headers = {"Content-Type": "application/json", "x-goog-api-key": self.config.api_key}
        try:
            async with httpx.AsyncClient(timeout=self.config.timeout) as client:
                resp = await client.post(url, json=payload, headers=headers)
            if resp.status_code >= 400:
                raise ProviderError(f"gemini HTTP {resp.status_code}: {resp.text[:400]}")
            data = resp.json()
        except httpx.HTTPError as exc:
            raise ProviderError(f"gemini request failed: {exc}") from exc

        candidates = data.get("candidates") or []
        if not candidates:
            raise ProviderError("gemini returned no candidates")
        parts = (candidates[0].get("content") or {}).get("parts") or []
        text = "".join(str(p.get("text", "")) for p in parts if isinstance(p, dict))
        usage = data.get("usageMetadata") or {}
        return ChatResponse(
            content=text,
            model=model,
            prompt_tokens=int(usage.get("promptTokenCount", 0) or 0),
            completion_tokens=int(usage.get("candidatesTokenCount", 0) or 0),
            finish_reason=str(candidates[0].get("finishReason", "")),
            provider=self.id,
            raw=data,
        )

    async def embed(self, texts: list[str]) -> list[list[float]]:
        model = self.config.embed_model or "text-embedding-004"
        url = f"{self._base}/models/{model}:batchEmbedContents"
        headers = {"Content-Type": "application/json", "x-goog-api-key": self.config.api_key}
        payload = {
            "requests": [{"model": f"models/{model}", "content": {"parts": [{"text": t}]}} for t in texts]
        }
        try:
            async with httpx.AsyncClient(timeout=self.config.timeout) as client:
                resp = await client.post(url, json=payload, headers=headers)
            if resp.status_code >= 400:
                raise ProviderError(f"gemini embed HTTP {resp.status_code}")
            data = resp.json()
        except httpx.HTTPError as exc:
            raise ProviderError(f"gemini embed failed: {exc}") from exc

        embeddings = data.get("embeddings") or []
        vectors = [list(map(float, e.get("values") or [])) for e in embeddings]
        if len(vectors) != len(texts):
            raise ProviderError("gemini embed count mismatch")
        return vectors


def _to_parts(m: ChatMessage) -> list[dict[str, Any]]:
    if isinstance(m.content, str):
        return [{"text": m.content}]
    parts: list[dict[str, Any]] = []
    for part in m.content:
        if not isinstance(part, dict):
            continue
        ptype = part.get("type")
        if ptype == "text":
            parts.append({"text": str(part.get("text", ""))})
        elif ptype == "image_url":
            url = ""
            image_url = part.get("image_url")
            if isinstance(image_url, dict):
                url = str(image_url.get("url", ""))
            elif isinstance(image_url, str):
                url = image_url
            if url.startswith("data:"):
                header, _, b64 = url.partition(",")
                mime = "image/png"
                if ";" in header:
                    mime = header.split(":", 1)[1].split(";", 1)[0] or "image/png"
                parts.append({"inline_data": {"mime_type": mime, "data": b64}})
            elif url:
                parts.append({"file_data": {"mime_type": "image/png", "file_uri": url}})
    return parts or [{"text": ""}]
