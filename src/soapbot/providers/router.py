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
import math
import time
from collections import deque
from collections.abc import AsyncIterator, Callable
from dataclasses import dataclass, field
from typing import Any

from soapbot.config import settings
from soapbot.providers.base import (
    BaseProvider,
    CapabilitySlot,
    ChatRequest,
    ChatResponse,
    ProviderConfig,
    ProviderError,
)
from soapbot.security.injection import redact, scrub_prompt_echo

logger = logging.getLogger(__name__)

_FACTORIES = {}


async def _chat_once(provider: BaseProvider, request: ChatRequest) -> AsyncIterator[str]:
    resp = await provider.chat(request)
    yield resp.content


def _stream_of(provider: BaseProvider, request: ChatRequest) -> AsyncIterator[str]:
    """Return a piece iterator for this provider.

    A provider that does not subclass :class:`BaseProvider` — a plugin-supplied one,
    or a test double — has no inherited ``stream``. Applying the fallback here keeps
    the failover loop from confusing an ``AttributeError`` with a provider outage.
    """
    stream_fn = getattr(provider, "stream", None)
    if callable(stream_fn):
        return stream_fn(request)
    return _chat_once(provider, request)


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
    prompt_tokens: int = 0
    completion_tokens: int = 0
    latencies: deque[float] = field(default_factory=lambda: deque(maxlen=256))
    """Recent latencies for p50/p95.

    Bounded on purpose: an unbounded sample list is a slow memory leak in a process
    that is meant to run for weeks, and the operator only ever looks at the recent
    distribution. 256 samples covers a useful window without growing.
    """

    def percentile(self, fraction: float) -> float:
        """Nearest-rank percentile; ``0.0`` when nothing has been recorded yet."""
        if not self.latencies:
            return 0.0
        ordered = sorted(self.latencies)
        index = min(len(ordered) - 1, max(0, math.ceil(fraction * len(ordered)) - 1))
        return round(ordered[index], 2)


class ProviderCooldownError(ProviderError):
    """Every provider is in cooldown; nothing was attempted.

    A distinct type because the caller's correct response differs from a normal failure:
    there is nothing to retry and no second provider to fail over to, so the turn should
    degrade to a spoken notice rather than proceed and fail again.
    """

    def __init__(self, retry_after: float, detail: str = "") -> None:
        super().__init__(
            f"all providers are cooling down; retry in {max(0.0, retry_after):.0f}s"
            + (f" ({detail})" if detail else "")
        )
        self.retry_after = max(0.0, retry_after)


class ProviderRouter:
    def __init__(self, cooldown_seconds: float = 60.0) -> None:
        self._providers: dict[str, BaseProvider] = {}
        self._stats: dict[str, ProviderStat] = {}
        self._cooldown = cooldown_seconds
        self._breaker_until: float = 0.0
        """When the router as a whole stops trying.

        Per-provider cooldown already stops us hammering one dead endpoint. It does not
        cover the case where *every* provider is dead at once — a network partition, a
        revoked key shared across configs — and then every message walks the whole list,
        fails, logs, and pays the full timeout before the user is told nothing. On a busy
        group that is a retry storm aimed at endpoints that are already struggling.
        """
        self._breaker_strikes: int = 0

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
        now = time.time()
        return {
            pid: {
                "calls": s.calls,
                "failures": s.failures,
                # Derived rather than stored: a stored rate and the two counters it comes
                # from can disagree after a partial update.
                "success_rate": round((s.calls - s.failures) / s.calls, 4) if s.calls else 0.0,
                "last_error": s.last_error,
                "last_latency_ms": s.last_latency_ms,
                "p50_latency_ms": s.percentile(0.50),
                "p95_latency_ms": s.percentile(0.95),
                "prompt_tokens": s.prompt_tokens,
                "completion_tokens": s.completion_tokens,
                "consecutive_failures": s.consecutive_failures,
                "cooling_down": s.disabled_until > now,
            }
            for pid, s in self._stats.items()
        }

    # ------------------------------------------------------------------ accounting
    def _record_ok(
        self,
        provider_id: str,
        latency_ms: float,
        *,
        prompt_tokens: int = 0,
        completion_tokens: int = 0,
    ) -> None:
        stat = self._stats[provider_id]
        stat.calls += 1
        stat.consecutive_failures = 0
        stat.last_error = ""
        stat.last_latency_ms = round(latency_ms, 2)
        stat.latencies.append(latency_ms)
        stat.prompt_tokens += max(0, prompt_tokens)
        stat.completion_tokens += max(0, completion_tokens)

    def _record_failure(
        self, provider_id: str, exc: BaseException, latency_ms: float, *, cooldown: bool
    ) -> str:
        """Record one failed attempt; return the scrubbed detail for the error message.

        ``cooldown`` separates counting from punishing. Every slot must count its
        attempts or the numbers misreport traffic — ``embed``/``transcribe`` used to
        skip even that. But only the chat path may put a provider into cooldown: an
        embedding endpoint being down says nothing about whether the model can still
        answer a message, and sharing the cooldown would take chat offline for an
        unrelated reason.
        """
        stat = self._stats[provider_id]
        stat.calls += 1
        stat.failures += 1
        stat.consecutive_failures += 1
        stat.last_latency_ms = round(latency_ms, 2)
        stat.latencies.append(latency_ms)
        detail = redact(scrub_prompt_echo(str(exc)))[:200]
        stat.last_error = detail
        if cooldown and stat.consecutive_failures >= 3:
            stat.disabled_until = time.time() + self._cooldown
            logger.error(
                "provider=%s disabled for %.0fs after %d consecutive failures",
                provider_id,
                self._cooldown,
                stat.consecutive_failures,
            )
        return detail

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
        self._check_breaker()
        available = self._available(slot)
        if not available:
            # Distinguish "nothing configured for this capability" (a configuration
            # problem an operator must see) from "everything is cooling down" (transient,
            # and the breaker should handle it quietly).
            if self._all_cooling_down():
                self._open_breaker("all providers cooling down")
            raise ProviderError(f"no provider available for slot={slot}")

        errors: list[str] = []
        for provider in available:
            t0 = time.perf_counter()
            try:
                if slot is CapabilitySlot.VISION:
                    resp = await provider.vision(request)
                else:
                    resp = await provider.chat(request)
                latency = (time.perf_counter() - t0) * 1000
                self._record_ok(
                    provider.id,
                    latency,
                    prompt_tokens=resp.prompt_tokens,
                    completion_tokens=resp.completion_tokens,
                )
                self._close_breaker()
                # A line per successful call used to make the log ring a list of
                # numbers. Only a call that crossed the threshold is worth a warning;
                # the rest are debug so the threshold keeps its meaning.
                if latency >= settings.slow_call_ms:
                    logger.warning(
                        "slow provider call provider=%s latency=%.0fms threshold=%dms",
                        provider.id,
                        latency,
                        settings.slow_call_ms,
                    )
                else:
                    logger.debug(
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
                # Scrubbing lives in _record_failure: provider errors are built from the
                # *upstream response body*, and a relay or debugging proxy that echoes
                # the request would otherwise put our own system prompt into
                # ``stats.last_error`` (returned by /api/admin/providers) and into the
                # log ring the WebUI streams.
                detail = self._record_failure(provider.id, exc, latency, cooldown=True)
                errors.append(f"{provider.id}: {detail}")
                # Same scrubbed text, not ``exc``: this line lands in the ring buffer that
                # the WebUI streams and in the log file an operator ships elsewhere.
                logger.warning("provider=%s failed slot=%s: %s", provider.id, slot, detail)

        # Every configured provider was tried and every one failed. That is the condition
        # the breaker exists for: opening it here means the next message is refused in
        # microseconds instead of paying N timeouts to learn the same thing.
        self._open_breaker(" | ".join(errors)[:300])
        raise ProviderError("all providers failed: " + " | ".join(errors))

    # ------------------------------------------------------------------ breaker
    def _all_cooling_down(self) -> bool:
        now = time.time()
        stats = [self._stats.get(p.id) for p in self._ordered()]
        return bool(stats) and all(s is not None and s.disabled_until > now for s in stats)

    def _check_breaker(self) -> None:
        remaining = self._breaker_until - time.time()
        if remaining > 0:
            raise ProviderCooldownError(remaining)

    def _open_breaker(self, detail: str) -> None:
        self._breaker_strikes += 1
        threshold = max(1, settings.breaker_threshold)
        if self._breaker_strikes < threshold:
            # Deliberately not opening yet. A single total failure is one bad turn — a
            # stream that produced nothing still has a fallback worth trying, and a
            # breaker that fires here would block it.
            logger.warning(
                "all providers failed (%d/%d before pausing). %s",
                self._breaker_strikes,
                threshold,
                detail,
            )
            return

        over = self._breaker_strikes - threshold + 1
        delay = min(
            settings.breaker_max_seconds,
            settings.breaker_base_seconds * (2 ** (over - 1)),
        )
        self._breaker_until = time.time() + delay
        logger.error(
            "all providers failed (%d in a row); pausing model calls for %.0fs. %s",
            self._breaker_strikes,
            delay,
            detail,
        )

    def _close_breaker(self) -> None:
        if self._breaker_until or self._breaker_strikes:
            logger.info("provider recovered; circuit breaker closed")
        self._breaker_until = 0.0
        self._breaker_strikes = 0

    def breaker_status(self) -> dict[str, Any]:
        """What the panel shows. Counts and deadlines only, never provider secrets."""
        remaining = max(0.0, self._breaker_until - time.time())
        return {
            "open": remaining > 0,
            "retry_after": round(remaining, 1),
            "consecutive_total_failures": self._breaker_strikes,
        }

    def _stream_candidates(self) -> list[BaseProvider]:
        """Streaming providers first, then chat-only ones as a last resort.

        A provider whose ``stream`` is the inherited default still *works* — it
        yields the whole answer once — so it is a better fallback than "no reply at
        all". Ordering by priority within each group keeps the operator's intent.
        """
        now = time.time()
        usable = [
            p
            for p in self._ordered()
            if (p.supports(CapabilitySlot.STREAM) or p.supports(CapabilitySlot.CHAT))
            and not (self._stats.get(p.id) and self._stats[p.id].disabled_until > now)
        ]
        usable.sort(key=lambda p: (not p.supports(CapabilitySlot.STREAM), p.config.priority))
        return usable

    async def stream(
        self,
        request: ChatRequest,
        *,
        slot: CapabilitySlot = CapabilitySlot.STREAM,
        on_pick: Callable[[str], None] | None = None,
    ) -> AsyncIterator[str]:
        """Yield pieces from the first provider that produces one.

        Failover stops at the first token. Once part of an answer has reached a group,
        switching providers would splice two completions together — visible to every
        reader, and worse than finishing a mediocre one. A provider that fails
        *before* its first yield is still replaced, which is the case that matters in
        practice: bad key, dead host, 429 on connect.
        """
        self._check_breaker()
        candidates = self._stream_candidates()
        if not candidates:
            if self._all_cooling_down():
                self._open_breaker("all providers cooling down")
            raise ProviderError(f"no provider available for slot={slot}")

        errors: list[str] = []
        for provider in candidates:
            stat = self._stats[provider.id]
            t0 = time.perf_counter()
            produced = False
            try:
                async for piece in _stream_of(provider, request):
                    if not produced:
                        produced = True
                        stat.calls += 1
                        stat.last_latency_ms = round((time.perf_counter() - t0) * 1000, 2)
                        stat.consecutive_failures = 0
                        stat.last_error = ""
                        self._close_breaker()
                        if on_pick is not None:
                            on_pick(provider.id)
                        logger.debug(
                            "provider=%s stream first-token latency=%.0fms",
                            provider.id,
                            stat.last_latency_ms,
                        )
                    yield piece
                if not produced:
                    raise ProviderError("stream produced no content")
                return
            except Exception as exc:
                stat.calls += 1 if not produced else 0
                stat.failures += 1
                stat.consecutive_failures += 1
                stat.last_error = redact(scrub_prompt_echo(str(exc)))[:200]
                errors.append(f"{provider.id}: {stat.last_error}")
                if produced:
                    # Half an answer is already in the group. A second provider would
                    # continue someone else's sentence; surfacing the break is honest.
                    raise
                logger.warning(
                    "provider=%s stream failed: %s", provider.id, stat.last_error
                )

        self._open_breaker(" | ".join(errors)[:300])
        raise ProviderError("all stream providers failed: " + " | ".join(errors))

    async def embed(self, texts: list[str]) -> list[float] | list[list[float]]:
        available = self._available(CapabilitySlot.EMBED)
        if not available:
            raise ProviderError("no provider available for embeddings")
        errors: list[str] = []
        for provider in available:
            t0 = time.perf_counter()
            try:
                vectors = await provider.embed(texts)
                self._record_ok(provider.id, (time.perf_counter() - t0) * 1000)
                return vectors
            except Exception as exc:
                # cooldown=False: an embedding outage says nothing about whether chat
                # still works, so it must not share the cooldown. The attempt is still
                # counted — this path used to increment `failures` without `calls`,
                # which made the success rate below the true value forever.
                detail = self._record_failure(
                    provider.id, exc, (time.perf_counter() - t0) * 1000, cooldown=False
                )
                errors.append(f"{provider.id}: {detail}")
        raise ProviderError("all embed providers failed: " + " | ".join(errors))

    async def transcribe(
        self, audio: bytes, *, mime: str = "audio/silk", language: str = ""
    ) -> str:
        """Speech to text, with the same failover shape as ``embed``.

        Only providers that *declared* the slot are tried. Offering the call to a
        chat-only provider would depend on the default ``transcribe`` raising, which
        is correct but turns a configuration gap into a per-message error.
        """
        available = self._available(CapabilitySlot.TRANSCRIBE)
        if not available:
            raise ProviderError("no provider available for transcription")
        errors: list[str] = []
        for provider in available:
            t0 = time.perf_counter()
            try:
                text = await provider.transcribe(audio, mime=mime, language=language)
                self._record_ok(provider.id, (time.perf_counter() - t0) * 1000)
                return text
            except Exception as exc:
                # Same reasoning as embed: count the attempt, do not touch chat cooldown.
                detail = self._record_failure(
                    provider.id, exc, (time.perf_counter() - t0) * 1000, cooldown=False
                )
                errors.append(f"{provider.id}: {detail}")
        raise ProviderError("all transcribe providers failed: " + " | ".join(errors))

    def has_capability(self, slot: CapabilitySlot) -> bool:
        return bool(self._available(slot))
