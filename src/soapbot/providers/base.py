"""Provider contract.

Five capability slots: ``chat`` / ``stream`` / ``vision`` / ``embed`` / ``transcribe``.
A provider declares which slots it actually implements; the router picks a
provider that satisfies the request rather than assuming every provider can do
everything (Ollama cannot embed images, many relay endpoints cannot stream).

We talk to vendor REST endpoints directly with httpx instead of binding to heavy
SDKs: fewer transitive dependencies, and the OpenAI-compatible surface alone
covers DeepSeek / Qwen / Moonshot / most relay services.
"""

from __future__ import annotations

import logging
from abc import ABC, abstractmethod
from collections.abc import AsyncIterator
from dataclasses import dataclass, field
from enum import StrEnum
from typing import Any

logger = logging.getLogger(__name__)


class CapabilitySlot(StrEnum):
    CHAT = "chat"
    STREAM = "stream"
    VISION = "vision"
    EMBED = "embed"
    TRANSCRIBE = "transcribe"


@dataclass(slots=True)
class ChatMessage:
    role: str
    content: str | list[dict[str, Any]]
    """String for text, or an OpenAI-style parts list for vision."""

    name: str = ""
    tool_call_id: str = ""

    def to_openai(self) -> dict[str, Any]:
        payload: dict[str, Any] = {"role": self.role, "content": self.content}
        if self.name:
            payload["name"] = self.name
        if self.tool_call_id:
            payload["tool_call_id"] = self.tool_call_id
        return payload

    def text(self) -> str:
        if isinstance(self.content, str):
            return self.content
        parts = [
            str(p.get("text", ""))
            for p in self.content
            if isinstance(p, dict) and p.get("type") == "text"
        ]
        return "".join(parts)


@dataclass(slots=True)
class ChatRequest:
    messages: list[ChatMessage]
    model: str = ""
    temperature: float = 0.8
    max_tokens: int = 1024
    tools: list[dict[str, Any]] = field(default_factory=list)
    extra: dict[str, Any] = field(default_factory=dict)


@dataclass(slots=True)
class ChatResponse:
    content: str
    model: str = ""
    prompt_tokens: int = 0
    completion_tokens: int = 0
    tool_calls: list[dict[str, Any]] = field(default_factory=list)
    finish_reason: str = ""
    provider: str = ""
    raw: dict[str, Any] = field(default_factory=dict)


@dataclass(slots=True)
class ProviderConfig:
    """Runtime configuration for one provider instance."""

    id: str
    kind: str
    label: str = ""
    base_url: str = ""
    api_key: str = ""
    model: str = ""
    embed_model: str = ""
    vision_model: str = ""
    timeout: float = 60.0
    max_retries: int = 2
    priority: int = 100
    """Lower number is tried first in the fallback chain."""

    enabled: bool = True
    extra: dict[str, Any] = field(default_factory=dict)


class ProviderError(RuntimeError):
    """Raised for any provider failure that should trigger failover."""


class BaseProvider(ABC):
    kind: str = "base"
    slots: frozenset[CapabilitySlot] = frozenset({CapabilitySlot.CHAT})

    def __init__(self, config: ProviderConfig) -> None:
        self.config = config

    @property
    def id(self) -> str:
        return self.config.id

    def supports(self, slot: CapabilitySlot) -> bool:
        return slot in self.slots

    @abstractmethod
    async def chat(self, request: ChatRequest) -> ChatResponse:
        """Non-streaming completion."""

    async def stream(self, request: ChatRequest) -> AsyncIterator[str]:
        """Yield the answer as it is produced. Default: one chunk, from ``chat``.

        Deliberately *not* abstract. A provider that cannot stream should still work,
        and the fallback belongs in the contract: as a merely-missing method it
        surfaced as ``AttributeError`` at call time, which the caller could not tell
        apart from a genuine provider failure, so it failed over to another provider
        that lacked the same method. Declaring ``STREAM`` and not implementing it is
        no longer expressible.
        """
        resp = await self.chat(request)
        yield resp.content

    async def vision(self, request: ChatRequest) -> ChatResponse:
        """Image understanding. Defaults to chat (multimodal endpoints accept parts)."""
        return await self.chat(request)

    async def embed(self, texts: list[str]) -> list[list[float]]:
        raise ProviderError(f"{self.kind} does not implement embed")

    async def transcribe(
        self, audio: bytes, *, mime: str = "audio/silk", language: str = ""
    ) -> str:
        """Speech to text. Default: refuse, explicitly.

        ``stream`` could get an honest default because a non-streaming call still
        produces the same answer. There is no such fallback here: a chat call cannot
        turn audio into words. A placeholder would put invented words into the
        conversation, attributed to a user who never typed them — worse than admitting
        the gap. The caller degrades to ``[语音]``, which is visible to everyone.
        """
        raise ProviderError(f"{self.kind} does not implement transcribe")

    def describe(self) -> dict[str, Any]:
        return {
            "id": self.config.id,
            "kind": self.kind,
            "label": self.config.label or self.config.id,
            "model": self.config.model,
            "slots": sorted(str(s) for s in self.slots),
            "enabled": self.config.enabled,
            "priority": self.config.priority,
        }
