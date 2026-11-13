"""The light slot: cheap-model designation for host-side lightweight tasks.

The compressor's docstring always promised "a cheap model can be used for
summaries while an expensive one handles the actual reply" — but the summariser
was wired to the same CHAT chain, so the promise had no configuration surface.
The light slot is that surface: an operator marks one provider instance with
``extra: {light: true}`` and the summariser's requests go there.

The two invariants the tests pin:

* designation is additive — marking a provider ``light`` never removes it from
  the main chat chain, so a single-provider setup cannot break its own replies;
* no designation at all falls back to the CHAT chain, so the default deployment
  behaves exactly as before.
"""

from __future__ import annotations

import pytest

from soapbot.providers.base import (
    BaseProvider,
    CapabilitySlot,
    ChatRequest,
    ChatResponse,
    ProviderConfig,
)
from soapbot.providers.router import ProviderRouter


class _Provider(BaseProvider):
    kind = "fake"
    slots = frozenset({CapabilitySlot.CHAT, CapabilitySlot.STREAM})

    async def chat(self, request: ChatRequest) -> ChatResponse:
        return ChatResponse(
            content=f"from:{self.id}",
            provider=self.id,
            prompt_tokens=1,
            completion_tokens=1,
        )


def _router(*providers: _Provider) -> ProviderRouter:
    router = ProviderRouter(cooldown_seconds=60.0)
    for p in providers:
        router.add(p)
    return router


def _provider(pid: str, *, light: bool = False, priority: int = 100) -> _Provider:
    extra = {"light": True} if light else {}
    return _Provider(ProviderConfig(id=pid, kind="fake", model="m", extra=extra, priority=priority))


async def test_light_slot_routes_to_the_designated_cheap_provider() -> None:
    expensive = _provider("expensive", priority=10)
    cheap = _provider("cheap", light=True, priority=90)
    router = _router(expensive, cheap)
    # 主聊仍按 priority 走贵的（designation 是加选，不是摘除）
    reply = await router.chat(ChatRequest(messages=[]), slot=CapabilitySlot.CHAT)
    assert reply.content == "from:expensive"
    # 轻任务走到被指派的便宜实例
    light = await router.chat(ChatRequest(messages=[]), slot=CapabilitySlot.LIGHT)
    assert light.content == "from:cheap"


async def test_designation_does_not_remove_a_provider_from_the_chat_chain() -> None:
    only = _provider("only", light=True)
    router = _router(only)
    reply = await router.chat(ChatRequest(messages=[]), slot=CapabilitySlot.CHAT)
    assert reply.content == "from:only"


async def test_no_designation_falls_back_to_the_chat_chain() -> None:
    provider = _provider("solo")
    router = _router(provider)
    light = await router.chat(ChatRequest(messages=[]), slot=CapabilitySlot.LIGHT)
    assert light.content == "from:solo"


async def test_light_preference_follows_priority_within_designated_providers() -> None:
    a = _provider("a", light=True, priority=50)
    b = _provider("b", light=True, priority=10)
    router = _router(a, b)
    light = await router.chat(ChatRequest(messages=[]), slot=CapabilitySlot.LIGHT)
    assert light.content == "from:b"


@pytest.mark.parametrize("truthy", [True, "yes", 1])
async def test_truthy_designations_are_accepted_and_falsy_are_not(truthy: object) -> None:
    provider = _Provider(ProviderConfig(id="p", kind="fake", model="m", extra={"light": truthy}))
    assert provider.supports(CapabilitySlot.LIGHT) is True
    off = _Provider(ProviderConfig(id="p", kind="fake", model="m", extra={"light": False}))
    assert off.supports(CapabilitySlot.LIGHT) is False
    absent = _Provider(ProviderConfig(id="p", kind="fake", model="m"))
    assert absent.supports(CapabilitySlot.LIGHT) is False


async def test_the_summarizer_runs_on_the_light_slot() -> None:
    """engine._summarize 是轻任务的第一个消费者：摘要必须走 LIGHT 槽。"""
    import inspect

    from soapbot.ai import engine as engine_module

    source = inspect.getsource(engine_module.AIEngine._summarize)
    assert "CapabilitySlot.LIGHT" in source
