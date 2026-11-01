"""When every provider is down, stop walking the list on every message.

Per-provider cooldown already stops us hammering one dead endpoint. It does not cover the
case where *all* of them are dead at once — a network partition, a revoked key shared
across configs. Then every message walks the whole list, fails, logs, and pays each
timeout before the user is told nothing. On a busy group that is a retry storm aimed at
endpoints that are already struggling.

The property that matters is that the *second* message does not attempt anything, not
merely that it fails.
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
from soapbot.providers.router import ProviderCooldownError, ProviderRouter


class _DeadProvider(BaseProvider):
    """Fails instantly, so a test measures behaviour rather than timeouts."""

    kind = "dead"
    slots = frozenset({CapabilitySlot.CHAT})

    def __init__(self, config: ProviderConfig, log: list[str]) -> None:
        super().__init__(config)
        self.attempts = log

    async def chat(self, request: ChatRequest) -> ChatResponse:
        self.attempts.append(self.id)
        raise ProviderError(f"{self.id} is down")


def _router(*ids: str) -> tuple[ProviderRouter, list[str]]:
    attempts: list[str] = []
    router = ProviderRouter(cooldown_seconds=0.0)
    for pid in ids:
        router.add(_DeadProvider(ProviderConfig(id=pid, kind="dead", base_url="https://x/v1"), attempts))
    return router, attempts


def _request() -> ChatRequest:
    return ChatRequest(messages=[{"role": "user", "content": "hi"}])


@pytest.mark.asyncio
async def test_the_first_total_failure_tries_every_provider() -> None:
    router, attempts = _router("a", "b")
    with pytest.raises(ProviderError):
        await router.chat(_request())
    assert attempts == ["a", "b"], "failover within one turn is the existing behaviour"


@pytest.mark.asyncio
async def test_the_second_message_attempts_nothing() -> None:
    """This is the whole point: no second walk of the list."""
    router, attempts = _router("a", "b")
    with pytest.raises(ProviderError):
        await router.chat(_request())

    with pytest.raises(ProviderCooldownError):
        await router.chat(_request())

    assert attempts == ["a", "b"], f"providers were retried: {attempts}"


@pytest.mark.asyncio
async def test_the_error_carries_a_retry_hint() -> None:
    """The caller needs to know it is transient, and roughly for how long."""
    router, _attempts = _router("a")
    with pytest.raises(ProviderError):
        await router.chat(_request())

    with pytest.raises(ProviderCooldownError) as excinfo:
        await router.chat(_request())
    assert excinfo.value.retry_after > 0


@pytest.mark.asyncio
async def test_the_pause_grows_then_stops_growing(monkeypatch: pytest.MonkeyPatch) -> None:
    """Exponential with a cap: a long outage must not turn into a long blackout either."""
    from soapbot.config import settings

    monkeypatch.setattr(settings, "breaker_base_seconds", 10.0)
    monkeypatch.setattr(settings, "breaker_max_seconds", 25.0)

    router, _attempts = _router("a")
    delays: list[float] = []
    for _ in range(4):
        router._breaker_until = 0.0  # pretend the pause elapsed
        router._open_breaker("test")
        delays.append(router.breaker_status()["retry_after"])

    assert delays[0] < delays[1] < delays[2], delays
    assert max(delays) <= 25.0, delays


@pytest.mark.asyncio
async def test_a_success_closes_the_breaker() -> None:
    """A recovered provider must be usable immediately, not after the last pause expires."""

    class _Flaky(BaseProvider):
        kind = "flaky"
        slots = frozenset({CapabilitySlot.CHAT})

        def __init__(self, config: ProviderConfig) -> None:
            super().__init__(config)
            self.fail = True

        async def chat(self, request: ChatRequest) -> ChatResponse:
            if self.fail:
                raise ProviderError("down")
            return ChatResponse(content="ok", provider="flaky")

    router = ProviderRouter(cooldown_seconds=0.0)
    provider = _Flaky(ProviderConfig(id="f", kind="flaky", base_url="https://x/v1"))
    router.add(provider)

    with pytest.raises(ProviderError):
        await router.chat(_request())
    assert router.breaker_status()["open"] is True

    provider.fail = False
    router._breaker_until = 0.0  # the pause elapsed
    response = await router.chat(_request())

    assert response.content == "ok"
    assert router.breaker_status()["open"] is False
    assert router.breaker_status()["consecutive_total_failures"] == 0


@pytest.mark.asyncio
async def test_streaming_is_gated_too() -> None:
    """A stream that bypassed the breaker would double the exposure, not halve it."""
    router, attempts = _router("a")

    with pytest.raises(ProviderError):
        async for _piece in router.stream(_request()):
            pass

    before = len(attempts)
    with pytest.raises(ProviderCooldownError):
        async for _piece in router.stream(_request()):
            pass
    assert len(attempts) == before


@pytest.mark.asyncio
async def test_the_stage_speaks_instead_of_going_silent() -> None:
    """Silence during an outage is indistinguishable from a broken bot."""
    from soapbot.ai import stages as stages_module

    class _Engine:
        async def respond(self, _req):
            raise ProviderCooldownError(12.0)

    # Constructed for real rather than stubbing attributes: this test is about the
    # stage's own except clause, and a hand-built object tests whatever the next refactor
    # happens not to rename.
    stage = stages_module.ModelStage(_Engine())

    from soapbot.core.message import IncomingMessage, MessageScene, MessageSegment, Sender
    from soapbot.core.pipeline import PipelineContext

    event = IncomingMessage(
        adapter="onebot11",
        message_id="m1",
        scene=MessageScene.GROUP,
        sender=Sender(user_id="1", nickname="tester"),
        segments=[MessageSegment.text("hi")],
        group_id="9000",
        self_id="10000",
        trace_id="t-breaker",
    )
    ctx = PipelineContext(event=event, adapter=None, locale="zh")

    result = await stage.run(ctx)

    assert result.halt is False, "the turn was dropped instead of answered"
    assert ctx.extras.get("skip_model") is True
    assert ctx.model_reply, "the user got silence"
    assert ctx.extras.get("breaker_open") is True
