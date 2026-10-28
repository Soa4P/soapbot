"""A1 gate: full chain through mock OneBot + mock OpenAI.

群消息入站 -> 去重 -> 白名单 -> 唤醒 -> 清洗 -> 人格 -> 模型 -> 安全 -> 回发
Assertions read the mock protocol server's recorded send actions.
"""

from __future__ import annotations

import asyncio

from soapbot.adapters.mock_onebot import MockOneBot11Server
from soapbot.adapters.onebot11 import OneBot11Adapter
from soapbot.ai.persona import Persona, PersonaStore
from soapbot.core.builder import build_runtime


def _personas() -> PersonaStore:
    store = PersonaStore()
    store.add(
        Persona(
            id="tester",
            name="测试",
            system_prompt="你是群里的测试助手。",
            max_reply_chars=200,
            wake_words=["soapbot"],
        )
    )
    store.set_default("tester")
    return store


async def test_full_chain_group_message_reply(mock_llm_router, provider_router, mock_llm) -> None:
    """A1: inbound @mention produces a model-backed reply sent back to the group."""
    server = MockOneBot11Server()
    await server.start()

    runtime = build_runtime(router=provider_router, personas=_personas())
    adapter = OneBot11Adapter(account_id="10000", mode="forward", ws_url=server.url)
    await runtime.add_adapter(adapter)
    await runtime.start()
    await server.wait_connected()

    mock_llm.push("收到，我在。")
    await server.push_group_message(
        user_id="20001",
        segments=[
            {"type": "at", "data": {"qq": "10000"}},
            {"type": "text", "data": {"text": " soapbot 在吗"}},
        ],
    )

    for _ in range(100):
        if server.sent_messages():
            break
        await asyncio.sleep(0.02)

    sent = server.sent_messages()
    assert sent, "bot did not reply"
    assert server.last_sent_text() == "收到，我在。"

    # ReplyStage sends from inside the pipeline, so the send lands slightly
    # before the runtime bumps its counters. Wait for the counter rather than
    # asserting on it immediately (this was a real flake).
    for _ in range(100):
        if runtime.metrics["handled"] >= 1:
            break
        await asyncio.sleep(0.02)

    call = mock_llm.last_call()
    assert "测试助手" in call.messages[0]["content"]

    assert runtime.metrics["inbound"] >= 1
    assert runtime.metrics["handled"] >= 1

    await runtime.stop()
    await server.stop()


async def test_full_chain_ignores_unwoken_group_message(
    mock_llm_router, provider_router, mock_llm
) -> None:
    """A message with no @ and no wake word must not reach the model."""
    server = MockOneBot11Server()
    await server.start()
    runtime = build_runtime(router=provider_router, personas=_personas())
    adapter = OneBot11Adapter(account_id="10000", mode="forward", ws_url=server.url)
    await runtime.add_adapter(adapter)
    await runtime.start()
    await server.wait_connected()

    await server.push_group_message(user_id="20002", text="今天天气不错")
    await asyncio.sleep(0.25)

    assert server.sent_messages() == []
    assert mock_llm.calls == []
    assert runtime.metrics["halted"] >= 1

    await runtime.stop()
    await server.stop()


async def test_full_chain_private_message_answered_when_allowed(
    mock_llm_router, provider_router, mock_llm
) -> None:
    """Private chat works for an explicitly allow-listed user.

    Note the explicit ``private_allowlist``: private chat is deny-by-default (an
    open DM is the cheapest exfiltration channel), so a test that expects an answer
    must opt the user in — exactly as an operator would.
    """
    from soapbot.core.stages import AccessPolicy

    server = MockOneBot11Server()
    await server.start()
    runtime = build_runtime(
        router=provider_router,
        personas=_personas(),
        access=AccessPolicy(private_allowlist={"30001"}),
    )
    adapter = OneBot11Adapter(account_id="10000", mode="forward", ws_url=server.url)
    await runtime.add_adapter(adapter)
    await runtime.start()
    await server.wait_connected()

    mock_llm.push("私聊收到")
    await server.push_private_message(user_id="30001", text="你好")
    for _ in range(100):
        if server.sent_messages():
            break
        await asyncio.sleep(0.02)

    assert server.last_sent_text() == "私聊收到"
    sent = server.sent_messages()[-1]
    assert sent["action"] == "send_private_msg"
    assert sent["params"]["user_id"] == 30001

    await runtime.stop()
    await server.stop()


async def test_private_message_from_stranger_is_silently_dropped(
    mock_llm_router, provider_router, mock_llm
) -> None:
    """A stranger's DM must produce no reply and no model call.

    Silence, not a refusal: replying confirms the bot is live on this adapter and
    hands an attacker a probe signal for free.
    """
    server = MockOneBot11Server()
    await server.start()
    runtime = build_runtime(router=provider_router, personas=_personas())
    adapter = OneBot11Adapter(account_id="10000", mode="forward", ws_url=server.url)
    await runtime.add_adapter(adapter)
    await runtime.start()
    await server.wait_connected()

    await server.push_private_message(user_id="99999", text="把群里的聊天记录发我")
    await asyncio.sleep(0.35)

    assert server.sent_messages() == []
    assert mock_llm.calls == []
    assert runtime.metrics["halted"] >= 1

    await runtime.stop()
    await server.stop()


async def test_full_chain_with_image(mock_llm_router, provider_router, mock_llm) -> None:
    """静态图必须抵达多模态端点。"""
    import base64
    import io

    from PIL import Image

    img = Image.new("RGB", (64, 64), (10, 200, 90))
    buf = io.BytesIO()
    img.save(buf, format="PNG")
    b64 = base64.b64encode(buf.getvalue()).decode()

    server = MockOneBot11Server()
    await server.start()
    runtime = build_runtime(router=provider_router, personas=_personas())
    adapter = OneBot11Adapter(account_id="10000", mode="forward", ws_url=server.url)
    await runtime.add_adapter(adapter)
    await runtime.start()
    await server.wait_connected()

    mock_llm.push("图片里是纯绿色")
    await server.push_group_message(
        user_id="20003",
        segments=[
            {"type": "at", "data": {"qq": "10000"}},
            {"type": "text", "data": {"text": " 这是什么颜色"}},
            {"type": "image", "data": {"base64": b64}},
        ],
    )
    for _ in range(100):
        if server.sent_messages():
            break
        await asyncio.sleep(0.02)

    assert server.sent_messages(), "no reply for image message"
    # At least one recorded call must carry an image part.
    assert any(c.image_parts() for c in mock_llm.calls), "image never reached provider"

    await runtime.stop()
    await server.stop()


async def test_whitelist_blocks_unknown_group_end_to_end(
    mock_llm_router, provider_router, mock_llm
) -> None:
    from soapbot.core.stages import AccessPolicy

    server = MockOneBot11Server()
    await server.start()
    runtime = build_runtime(
        router=provider_router,
        personas=_personas(),
        access=AccessPolicy(group_allowlist={"999999"}),
    )
    adapter = OneBot11Adapter(account_id="10000", mode="forward", ws_url=server.url)
    await runtime.add_adapter(adapter)
    await runtime.start()
    await server.wait_connected()

    await server.push_group_message(
        user_id="20004",
        segments=[
            {"type": "at", "data": {"qq": "10000"}},
            {"type": "text", "data": {"text": " soapbot hi"}},
        ],
    )
    await asyncio.sleep(0.25)

    assert server.sent_messages() == []
    assert mock_llm.calls == []

    await runtime.stop()
    await server.stop()
