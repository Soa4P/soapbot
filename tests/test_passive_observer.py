"""Passive mode: read the group, answer only when addressed.

The requirement was "stay passive in speech but read messages, use the knowledge base
and the group's chatter to judge". The pipeline could not do that: the wake gate halts
before ``PersistStage``, so an un-addressed message was never archived and never became
context. These tests pin the split between the read path and the answer path.

The archive is deliberately detached from the message path (it runs as its own task),
so every assertion on stored rows goes through ``drain()`` first. A test that awaited
the observer and then looked at the store would pass or fail depending on scheduling —
the flakiest possible way to assert a correctness property.
"""

from __future__ import annotations

import asyncio
from typing import Any

import pytest

from soapbot.core.message import IncomingMessage, MessageScene, MessageSegment, Sender
from soapbot.core.observer import PassiveObserver
from soapbot.core.pipeline import PipelineContext


class _Recorder:
    """Stands in for MemoryStore: records what was archived, no database."""

    def __init__(self) -> None:
        self.archived: list[dict[str, Any]] = []

    async def archive_message(self, **kwargs: Any) -> None:
        self.archived.append(kwargs)


class _Adapter:
    meta = type("M", (), {"name": "onebot11"})()


def _ctx(
    text: str = "今天群里在聊显卡",
    *,
    scene: MessageScene = MessageScene.GROUP,
    halt_reason: str = "not_woken",
    persisted: bool = False,
) -> PipelineContext:
    event = IncomingMessage(
        adapter="onebot11",
        message_id="m1",
        scene=scene,
        sender=Sender(user_id="10001", nickname="alice"),
        segments=[MessageSegment.text(text)],
        group_id="20001",
        self_id="999",
    )
    ctx = PipelineContext(event=event, adapter=_Adapter())  # type: ignore[arg-type]
    ctx.halt_reason = halt_reason
    if persisted:
        ctx.extras["persisted_inbound"] = True
    return ctx


@pytest.mark.asyncio
async def test_an_unaddressed_group_message_is_read() -> None:
    store = _Recorder()
    observer = PassiveObserver(store)
    ctx = _ctx()

    await observer(ctx)
    await observer.drain()

    assert len(store.archived) == 1
    row = store.archived[0]
    assert row["content"] == "今天群里在聊显卡"
    assert row["session_key"] == "onebot11:group:20001"
    assert row["user_id"] == "10001"
    assert ctx.extras["passive_read"] is True


@pytest.mark.asyncio
async def test_the_message_path_does_not_wait_for_the_write() -> None:
    """The whole point of detaching: a slow archive must not slow the reply.

    Measured on a real group as ``database is locked`` — the passive write and the
    answering write were competing for the same SQLite lock inside the same await.
    """

    class _Slow:
        def __init__(self) -> None:
            self.done = False

        async def archive_message(self, **_kwargs: Any) -> None:
            await asyncio.sleep(0.5)
            self.done = True

    store = _Slow()
    observer = PassiveObserver(store)

    loop = asyncio.get_running_loop()
    started = loop.time()
    await observer(_ctx())
    elapsed = loop.time() - started

    assert elapsed < 0.1, f"observer blocked the message path for {elapsed:.2f}s"
    assert store.done is False
    await observer.drain()
    assert store.done is True


@pytest.mark.asyncio
async def test_a_replied_message_is_not_archived_twice() -> None:
    """PersistStage already wrote it; a second copy would double the transcript."""
    store = _Recorder()
    observer = PassiveObserver(store)
    await observer(_ctx(persisted=True))
    await observer.drain()
    assert store.archived == []


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "reason", ["user_blacklisted", "group_blacklisted", "private_not_allowed", "anonymous"]
)
async def test_dropped_traffic_is_not_remembered(reason: str) -> None:
    """A block that still feeds the memory is a block that can be recalled later."""
    store = _Recorder()
    observer = PassiveObserver(store)
    await observer(_ctx(halt_reason=reason))
    await observer.drain()
    assert store.archived == []


@pytest.mark.asyncio
async def test_private_chat_is_not_read() -> None:
    store = _Recorder()
    observer = PassiveObserver(store)
    await observer(_ctx(scene=MessageScene.PRIVATE))
    await observer.drain()
    assert store.archived == []


@pytest.mark.asyncio
async def test_a_reaction_is_not_worth_an_embedding() -> None:
    store = _Recorder()
    observer = PassiveObserver(store)
    await observer(_ctx(text="草"))
    await observer.drain()
    assert store.archived == []


@pytest.mark.asyncio
async def test_an_image_with_no_caption_is_still_context() -> None:
    """A group's images are exactly what passive mode is for; halting as ``empty_input``
    is the same message as ``not_woken`` seen one stage later."""
    store = _Recorder()
    event = IncomingMessage(
        adapter="onebot11",
        message_id="m2",
        scene=MessageScene.GROUP,
        sender=Sender(user_id="10001", nickname="alice"),
        segments=[MessageSegment.image(url="https://example.invalid/a.png")],
        group_id="20001",
        self_id="999",
    )
    ctx = PipelineContext(event=event, adapter=_Adapter())  # type: ignore[arg-type]
    ctx.halt_reason = "empty_input"

    observer = PassiveObserver(store)
    await observer(ctx)
    await observer.drain()

    assert len(store.archived) == 1
    # ``event.text`` renders the segment; the row keeps that rendering so recall sees
    # the same string the answering path would have archived.
    assert store.archived[0]["content"] == "[图片]"


@pytest.mark.asyncio
async def test_a_failing_store_never_breaks_the_message() -> None:
    class _Broken:
        async def archive_message(self, **_kwargs: Any) -> None:
            raise RuntimeError("db is down")

    ctx = _ctx()
    observer = PassiveObserver(_Broken())
    await observer(ctx)  # must not raise
    await observer.drain()
    assert ctx.extras["passive_read"] is True


@pytest.mark.asyncio
async def test_a_locked_database_is_retried_once() -> None:
    """``database is locked`` is transient by definition; one retry covers it."""

    class _Flaky:
        def __init__(self) -> None:
            self.calls = 0
            self.archived: list[dict[str, Any]] = []

        async def archive_message(self, **kwargs: Any) -> None:
            self.calls += 1
            if self.calls == 1:
                raise RuntimeError("database is locked")
            self.archived.append(kwargs)

    store = _Flaky()
    observer = PassiveObserver(store)
    await observer(_ctx())
    await observer.drain()

    assert store.calls == 2
    assert len(store.archived) == 1


@pytest.mark.asyncio
async def test_a_flood_is_dropped_rather_than_queued() -> None:
    """Passive mode reads everything; on a busy group that is an unbounded write queue
    behind a bot that has to answer in the same process. Dropping the read is the
    cheaper failure — a missed memory costs context, a backlog costs every reply."""

    class _Slow:
        async def archive_message(self, **_kwargs: Any) -> None:
            await asyncio.sleep(0.3)

    observer = PassiveObserver(_Slow(), max_inflight=2)
    for _ in range(5):
        await observer(_ctx())

    assert observer.seen == 2
    assert observer.dropped == 3
    await observer.drain()
