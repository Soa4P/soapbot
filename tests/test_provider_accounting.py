"""Provider accounting must count every attempt, not only the chat ones.

The inconsistency this pins: ``embed`` and ``transcribe`` incremented ``failures``
without ever incrementing ``calls``, never recorded latency, and never touched the
cooldown. A provider whose embeddings always failed therefore reported
``success_rate == 0`` over zero attempts and ``calls == 0`` while ``failures == 5`` —
numbers that cannot be reconciled with the traffic an operator sees.

The cooldown is deliberately *not* unified: an embedding outage must not take the chat
path out of service. That asymmetry is asserted here so a future "consistency" cleanup
cannot quietly reintroduce it in the other direction.
"""

from __future__ import annotations

import pytest

from soapbot.providers.base import (
    BaseProvider,
    CapabilitySlot,
    ChatRequest,
    ChatResponse,
    ProviderConfig,
    ProviderError,
)
from soapbot.providers.router import ProviderRouter


class _Provider(BaseProvider):
    kind = "fake"
    slots = frozenset({CapabilitySlot.CHAT, CapabilitySlot.EMBED, CapabilitySlot.TRANSCRIBE})

    def __init__(self, config: ProviderConfig) -> None:
        super().__init__(config)
        self.fail_embed = False
        self.fail_chat = False

    async def chat(self, request: ChatRequest) -> ChatResponse:
        if self.fail_chat:
            raise ProviderError("chat down")
        return ChatResponse(
            content="ok", provider=self.id, prompt_tokens=11, completion_tokens=7
        )

    async def embed(self, texts: list[str]):
        if self.fail_embed:
            raise ProviderError("embed down")
        return [0.1, 0.2]

    async def transcribe(self, audio: bytes, *, mime: str = "", language: str = "") -> str:
        return "hello"


def _router() -> tuple[ProviderRouter, _Provider]:
    router = ProviderRouter(cooldown_seconds=60.0)
    provider = _Provider(ProviderConfig(id="fake", kind="fake", model="m"))
    router.add(provider)
    return router, provider


@pytest.mark.asyncio
async def test_embed_failures_are_counted_as_attempts() -> None:
    router, provider = _router()
    provider.fail_embed = True

    with pytest.raises(ProviderError):
        await router.embed(["hi"])

    stat = router.stats()["fake"]
    assert stat["calls"] == 1, "a failed attempt is still an attempt"
    assert stat["failures"] == 1
    assert stat["success_rate"] == 0.0


@pytest.mark.asyncio
async def test_embed_failures_do_not_cool_down_the_chat_path() -> None:
    """Sharing the cooldown would take chat offline because embeddings are broken."""
    router, provider = _router()
    provider.fail_embed = True

    for _ in range(3):
        with pytest.raises(ProviderError):
            await router.embed(["hi"])

    stat = router.stats()["fake"]
    assert stat["calls"] == 3
    assert stat["consecutive_failures"] == 3
    assert stat["cooling_down"] is False


@pytest.mark.asyncio
async def test_chat_still_cools_down_after_repeated_failures() -> None:
    router, provider = _router()
    provider.fail_chat = True

    for _ in range(3):
        with pytest.raises(ProviderError):
            await router.chat(ChatRequest(messages=[]))

    stat = router.stats()["fake"]
    assert stat["calls"] == 3
    assert stat["failures"] == 3
    assert stat["cooling_down"] is True


@pytest.mark.asyncio
async def test_chat_accumulates_tokens_and_reports_latency_percentiles() -> None:
    router, provider = _router()

    for _ in range(2):
        await router.chat(ChatRequest(messages=[]))

    stat = router.stats()["fake"]
    assert stat["calls"] == 2
    assert stat["failures"] == 0
    assert stat["success_rate"] == 1.0
    assert stat["prompt_tokens"] == 22
    assert stat["completion_tokens"] == 14
    assert stat["p50_latency_ms"] >= 0.0
    assert stat["p95_latency_ms"] >= stat["p50_latency_ms"]


@pytest.mark.asyncio
async def test_success_rate_uses_attempts_not_just_successes() -> None:
    """One success and one failure is 50%, not 100%."""
    router, provider = _router()
    await router.chat(ChatRequest(messages=[]))

    provider.fail_chat = True
    with pytest.raises(ProviderError):
        await router.chat(ChatRequest(messages=[]))

    stat = router.stats()["fake"]
    assert stat["calls"] == 2
    assert stat["failures"] == 1
    assert stat["success_rate"] == 0.5
