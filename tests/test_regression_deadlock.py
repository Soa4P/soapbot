"""Regression: adapters must not deadlock when a handler sends a message.

The bug this guards against was real and severe: ``emit()`` awaited handlers
inline, so a handler calling ``send()`` waited for an API acknowledgement that
only the same reader loop could deliver -> permanent self-deadlock. The bot
looked like it replied (bytes left the socket) but every subsequent message hung.

The symptom in production would be "the bot answers once, then goes silent",
which is extremely hard to diagnose from logs. Hence an explicit test.
"""

from __future__ import annotations

import asyncio

from soapbot.adapters.mock_onebot import MockOneBot11Server
from soapbot.adapters.onebot11 import OneBot11Adapter
from soapbot.core.message import MessageScene, MessageSegment, OutgoingMessage


async def test_handler_sending_does_not_deadlock() -> None:
    """A handler that sends a reply must complete, not hang forever."""
    server = MockOneBot11Server()
    await server.start()
    adapter = OneBot11Adapter(account_id="10000", mode="forward", ws_url=server.url)

    done = asyncio.Event()

    async def echo_handler(event) -> None:
        await adapter.send(
            OutgoingMessage(
                scene=MessageScene.GROUP,
                segments=[MessageSegment.text(f"echo:{event.text}")],
                group_id=event.group_id,
            )
        )
        done.set()

    adapter.on_event(echo_handler)
    await adapter.start()
    await server.wait_connected()

    await server.push_group_message(text="hello")

    # If the handler ran inline inside the reader loop this would never be set.
    await asyncio.wait_for(done.wait(), timeout=5.0)
    assert server.last_sent_text() == "echo:hello"

    await adapter.stop()
    await server.stop()


async def test_multiple_concurrent_messages_all_answered() -> None:
    """Several rapid messages must all be handled (no lock leak, no stall)."""
    server = MockOneBot11Server()
    await server.start()
    adapter = OneBot11Adapter(account_id="10000", mode="forward", ws_url=server.url)

    handled: list[str] = []

    async def handler(event) -> None:
        await adapter.send(
            OutgoingMessage(
                scene=MessageScene.GROUP,
                segments=[MessageSegment.text(f"ack:{event.text}")],
                group_id=event.group_id,
            )
        )
        handled.append(event.text)

    adapter.on_event(handler)
    await adapter.start()
    await server.wait_connected()

    for i in range(5):
        await server.push_group_message(text=f"m{i}", message_id=f"id-{i}")

    for _ in range(150):
        if len(handled) == 5:
            break
        await asyncio.sleep(0.02)

    assert sorted(handled) == ["m0", "m1", "m2", "m3", "m4"]
    assert len(server.sent_messages()) == 5

    await adapter.stop()
    await server.stop()
