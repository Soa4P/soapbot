"""Provider router with priority-based failover.

Rules:
- Providers are ordered by ``priority`` (ascending).
- A request asks for a slot (chat/vision/embed); only providers implementing it
  are considered.
- On ``ProviderError`` we move to the next provider and record the failure so the
  WebUI can show provider health. Successful calls reset the failure counter.
- If every provider fails, the aggregated errors are raised — never a silent
  empty reply, because a silent empty reply looks like the bot ignoring you.
"""

from __future__ import annotations

import logging
import time
from dataclasses import dataclass
from typing import Any

from soapbot.providers.base import (
    BaseProvider,
    CapabilitySlot,
    ChatRequest,
    ChatResponse,
    ProviderConfig,
    ProviderError,
)

logger = logging.getLogger(__name__)

_FACTORIES = {}


def register_provider_kind(kind: str, factory) -> None:
    _FACTORIES[kind] = factory


def build_provider(config: ProviderConfig) -> BaseProvider:
    from soapbot.providers.anthropic import AnthropicProvider
    from soapbot.providers.gemini import GeminiProvider
    from soapbot.providers.ollama import OllamaProvider
    from soapbot.providers.openai_compat import OpenAICompatProvider

    mapping = {
        "openai_compat": OpenAICompatProvider,
        "anthropic": AnthropicProvider,
        "gemini": GeminiProvider,
        "ollama": OllamaProvider,
    }
    if config.kind in _FACTORIES:
        return _FACTORIES[config.kind](config)
    cls = mapping.get(config.kind)
    if cls is None:
        raise ValueError(f"unknown provider kind: {config.kind}")
    return cls(config)


@dataclass(slots=True)
class ProviderStat:
    calls: int = 0
    failures: int = 0
    last_error: str = ""
    last_latency_ms: float = 0.0
    consecutive_failures: int = 0
    disabled_until: float = 0.0
    """Cooldown deadline after repeated failures, to stop hammering a dead endpoint."""


class ProviderRouter:
    def __init__(self, cooldown_seconds: float = 60.0) -> None:
        self._providers: dict[str, BaseProvider] = {}
        self._stats: dict[str, ProviderStat] = {}
        self._cooldown = cooldown_seconds

    # ------------------------------------------------------------------ registry
    def add(self, provider: BaseProvider) -> None:
        self._providers[provider.id] = provider
        self._stats.setdefault(provider.id, ProviderStat())

    def remove(self, provider_id: str) -> None:
        self._providers.pop(provider_id, None)
        self._stats.pop(provider_id, None)

    def get(self, provider_id: str) -> BaseProvider | None:
        return self._providers.get(provider_id)

    def list_providers(self) -> list[dict[str, Any]]:
        return [p.describe() for p in self._ordered()]

    def stats(self) -> dict[str, dict[str, Any]]:
        return {
            pid: {
                "calls": s.calls,
                "failures": s.failures,
                "last_error": s.last_error,
                "last_latency_ms": s.last_latency_ms,
                "consecutive_failures": s.consecutive_failures,
                "cooling_down": s.disabled_until > time.time(),
            }
            for pid, s in self._stats.items()
        }

    def _ordered(self) -> list[BaseProvider]:
        return sorted(
            (p for p in self._providers.values() if p.config.enabled),
            key=lambda p: p.config.priority,
        )

    def _available(self, slot: CapabilitySlot) -> list[BaseProvider]:
        now = time.time()
        out: list[BaseProvider] = []
        for p in self._ordered():
            if not p.supports(slot):
                continue
            stat = self._stats.get(p.id)
            if stat and stat.disabled_until > now:
                logger.debug("provider %s cooling down, skipped", p.id)
                continue
            out.append(p)
        return out

    # ------------------------------------------------------------------ calls
    async def chat(
        self, request: ChatRequest, *, slot: CapabilitySlot = CapabilitySlot.CHAT
    ) -> ChatResponse:
        available = self._available(slot)
        if not available:
            raise ProviderError(f"no provider available for slot={slot}")

        errors: list[str] = []
        for provider in available:
            stat = self._stats[provider.id]
            t0 = time.perf_counter()
            try:
                if slot is CapabilitySlot.VISION:
                    resp = await provider.vision(request)
                else:
                    resp = await provider.chat(request)
                latency = (time.perf_counter() - t0) * 1000
                stat.calls += 1
                stat.last_latency_ms = round(latency, 2)
                stat.consecutive_failures = 0
                stat.last_error = ""
                logger.info(
                    "provider=%s ok slot=%s latency=%.0fms tokens=%s/%s",
                    provider.id,
                    slot,
                    latency,
                    resp.prompt_tokens,
                    resp.completion_tokens,
                )
                return resp
            except Exception as exc:
                latency = (time.perf_counter() - t0) * 1000
                stat.calls += 1
                stat.failures += 1
                stat.consecutive_failures += 1
                stat.last_error = str(exc)
                stat.last_latency_ms = round(latency, 2)
                if stat.consecutive_failures >= 3:
                    stat.disabled_until = time.time() + self._cooldown
                    logger.error(
                        "provider=%s disabled for %.0fs after %d consecutive failures",
                        provider.id,
                        self._cooldown,
                        stat.consecutive_failures,
                    )
                errors.append(f"{provider.id}: {exc}")
                logger.warning("provider=%s failed slot=%s: %s", provider.id, slot, exc)

        raise ProviderError("all providers failed: " + " | ".join(errors))

    async def embed(self, texts: list[str]) -> list[float] | list[list[float]]:
        available = self._available(CapabilitySlot.EMBED)
        if not available:
            raise ProviderError("no provider available for embeddings")
        errors: list[str] = []
        for provider in available:
            try:
                vectors = await provider.embed(texts)
                self._stats[provider.id].calls += 1
                return vectors
            except Exception as exc:
                stat = self._stats[provider.id]
                stat.failures += 1
                stat.last_error = str(exc)
                errors.append(f"{provider.id}: {exc}")
        raise ProviderError("all embed providers failed: " + " | ".join(errors))

    def has_capability(self, slot: CapabilitySlot) -> bool:
        return bool(self._available(slot))
