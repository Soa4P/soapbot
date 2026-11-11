"""The bus has no queue, and these tests say so on purpose.

``EventBus`` used to accept a ``queue_size`` argument, store it, and never use it while
its module docstring promised "asyncio queues per subscriber ... and a hard cap". Nothing
was queued and nothing was capped. These tests pin the real contract, so the next person
who needs isolation between publisher and subscriber has to change the tests and the
docstring together instead of adding a parameter that lies.
"""

from __future__ import annotations

import asyncio

import pytest

from soapbot.core.bus import EventBus


async def test_publish_returns_only_after_every_handler_finished() -> None:
    bus = EventBus()
    seen: list[str] = []

    async def slow(payload: str) -> None:
        await asyncio.sleep(0.05)
        seen.append(f"slow:{payload}")

    async def fast(payload: str) -> None:
        seen.append(f"fast:{payload}")

    bus.subscribe("topic", slow)
    bus.subscribe("topic", fast)

    await bus.publish("topic", "x")

    # If publish were fire-and-forget, "slow:x" would still be missing here.
    assert seen == ["fast:x", "slow:x"]


async def test_handlers_run_concurrently_not_in_sequence() -> None:
    """A slow subscriber must not delay its siblings by its own duration."""

    bus = EventBus()
    order: list[str] = []

    async def first(payload: str) -> None:
        await asyncio.sleep(0.05)
        order.append("first")

    async def second(payload: str) -> None:
        order.append("second")

    bus.subscribe("topic", first)
    bus.subscribe("topic", second)

    started = asyncio.get_running_loop().time()
    await bus.publish("topic", None)
    elapsed = asyncio.get_running_loop().time() - started

    assert order == ["second", "first"], "订阅者被串行执行了"
    assert elapsed < 0.2, "并发执行不该累加各自的等待时间"


async def test_one_failing_handler_does_not_stop_the_others() -> None:
    bus = EventBus()
    seen: list[str] = []

    async def boom(payload: str) -> None:
        raise RuntimeError("subscriber is broken")

    async def healthy(payload: str) -> None:
        seen.append(payload)

    bus.subscribe("topic", boom)
    bus.subscribe("topic", healthy)

    await bus.publish("topic", "still-delivered")  # must not raise

    assert seen == ["still-delivered"]


async def test_publish_to_a_topic_with_no_subscribers_is_a_no_op() -> None:
    bus = EventBus()
    await bus.publish("nobody-listening", {"a": 1})
    assert bus.subscriber_count("nobody-listening") == 0


def test_unsupported_arguments_are_rejected() -> None:
    """``queue_size`` was accepted and ignored; it must not be accepted at all.

    Keeping a no-op keyword would let a caller (or a reviewer) believe the bus bounds
    memory per subscriber. It does not: delivery is awaited, so there is no queue.
    """
    with pytest.raises(TypeError):
        EventBus(queue_size=10)  # type: ignore[call-arg]
