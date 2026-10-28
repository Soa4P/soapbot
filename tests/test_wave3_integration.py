"""Wave 3 integration: memory across the full mock-OneBot chain.

Proves the loop closes: a fact said once is recalled later, and /recall works
in-group without touching the model.
"""

from __future__ import annotations

import asyncio

import pytest

from soapbot.adapters.mock_onebot import MockOneBot11Server
from soapbot.adapters.onebot11 import OneBot11Adapter
from soapbot.ai.persona import Persona, PersonaStore
from soapbot.core.builder import build_memory_stack, build_runtime
from soapbot.memory.db import Database, reset_database
from soapbot.memory.extractor import MemoryExtractor
from soapbot.memory.store import MemoryLayer


@pytest.fixture
async def db(tmp_path):
    await reset_database()
    database = Database(f"sqlite+aiosqlite:///{(tmp_path / 'i.db').as_posix()}")
    await database.init()
    yield database
    await database.close()
    await reset_database()


def _personas() -> PersonaStore:
    store = PersonaStore()
    store.add(
        Persona(
            id="t",
            name="测试",
            system_prompt="你是测试助手。",
            max_reply_chars=400,
            wake_words=["soapbot"],
        )
    )
    store.set_default("t")
    return store


async def _spin_up(provider_router, memory, kb, extractor):
    server = MockOneBot11Server()
    await server.start()
    runtime = build_runtime(
        router=provider_router,
        personas=_personas(),
        memory=memory,
        kb=kb,
        extractor=extractor,
    )
    adapter = OneBot11Adapter(account_id="10000", mode="forward", ws_url=server.url)
    await runtime.add_adapter(adapter)
    await runtime.start()
    await server.wait_connected()
    return server, runtime, adapter


async def _wait_sent(server, count: int = 1, rounds: int = 150):
    for _ in range(rounds):
        if len(server.sent_messages()) >= count:
            return
        await asyncio.sleep(0.02)


async def test_messages_are_archived_to_db(
    mock_llm_router, provider_router, mock_llm, db
) -> None:
    store, kb = build_memory_stack(db, None)
    server, runtime, adapter = await _spin_up(
        provider_router, store, kb, MemoryExtractor()
    )

    mock_llm.push("我记住了")
    await server.push_group_message(
        segments=[
            {"type": "at", "data": {"qq": "10000"}},
            {"type": "text", "data": {"text": " soapbot 记住我喜欢喝美式"}},
        ]
    )
    await _wait_sent(server)

    # The reply is archived *after* the send, so poll for it instead of
    # reading history the instant bytes hit the socket (this was a real flake).
    history: list[dict] = []
    for _ in range(150):
        history = await store.history("onebot11:group:123456")
        if len(history) >= 2:
            break
        await asyncio.sleep(0.02)

    assert any("美式" in h["content"] for h in history), "inbound not archived"
    assert any(h["role"] == "assistant" for h in history), "reply not archived"

    await runtime.stop()
    await server.stop()


async def test_memory_extraction_stores_durable_fact(
    mock_llm_router, provider_router, mock_llm, db
) -> None:
    store, kb = build_memory_stack(db, None)
    server, runtime, adapter = await _spin_up(
        provider_router, store, kb, MemoryExtractor()
    )

    mock_llm.push("好的")
    await server.push_group_message(
        segments=[
            {"type": "at", "data": {"qq": "10000"}},
            {"type": "text", "data": {"text": " soapbot 记住我的生日是7月12日"}},
        ]
    )
    await _wait_sent(server)
    for _ in range(100):
        if await store.count_memories() > 0:
            break
        await asyncio.sleep(0.02)

    assert await store.count_memories() >= 1
    rec = await store.recall("生日", scope="onebot11:group:123456")
    assert any("7月12日" in it.content for it in rec.items)

    await runtime.stop()
    await server.stop()


async def test_recall_command_answers_without_model(
    mock_llm_router, provider_router, mock_llm, db
) -> None:
    """A slash command must not burn a model call."""
    store, kb = build_memory_stack(db, None)
    await store.add_memory(
        content="用户喜欢蓝色",
        layer=MemoryLayer.SEMANTIC,
        scope="onebot11:group:123456",
    )

    server, runtime, adapter = await _spin_up(
        provider_router, store, kb, MemoryExtractor()
    )
    mock_llm.reset()

    await server.push_group_message(
        segments=[
            {"type": "at", "data": {"qq": "10000"}},
            {"type": "text", "data": {"text": " /recall 蓝色"}},
        ]
    )
    await _wait_sent(server)

    reply = server.last_sent_text()
    assert "蓝色" in reply
    assert "记忆" in reply
    assert mock_llm.calls == [], "command should not call the model"

    await runtime.stop()
    await server.stop()


async def test_help_command(mock_llm_router, provider_router, mock_llm, db) -> None:
    store, kb = build_memory_stack(db, None)
    server, runtime, _ = await _spin_up(provider_router, store, kb, MemoryExtractor())
    mock_llm.reset()

    await server.push_group_message(
        segments=[
            {"type": "at", "data": {"qq": "10000"}},
            {"type": "text", "data": {"text": " /help"}},
        ]
    )
    await _wait_sent(server)
    reply = server.last_sent_text()
    assert "/recall" in reply
    assert mock_llm.calls == []

    await runtime.stop()
    await server.stop()


async def test_recall_command_no_results(mock_llm_router, provider_router, mock_llm, db) -> None:
    store, kb = build_memory_stack(db, None)
    server, runtime, _ = await _spin_up(provider_router, store, kb, MemoryExtractor())

    await server.push_group_message(
        segments=[
            {"type": "at", "data": {"qq": "10000"}},
            {"type": "text", "data": {"text": " /recall 完全不存在的东西xyz"}},
        ]
    )
    await _wait_sent(server)
    assert "没有找到" in server.last_sent_text()

    await runtime.stop()
    await server.stop()


async def test_history_provider_feeds_model(
    mock_llm_router, provider_router, mock_llm, db
) -> None:
    """Prior turns must reach the model so follow-ups work."""
    store, kb = build_memory_stack(db, None)
    await store.archive_message(
        session_key="onebot11:group:123456", role="user", content="我叫小明"
    )
    await store.archive_message(
        session_key="onebot11:group:123456", role="assistant", content="你好小明"
    )

    server, runtime, _ = await _spin_up(provider_router, store, kb, MemoryExtractor())
    mock_llm.push("你叫小明")
    await server.push_group_message(
        segments=[
            {"type": "at", "data": {"qq": "10000"}},
            {"type": "text", "data": {"text": " soapbot 我叫什么"}},
        ]
    )
    await _wait_sent(server)

    call = mock_llm.last_call()
    joined = call.all_text()
    assert "我叫小明" in joined, "history not passed to model"
    assert "你好小明" in joined

    await runtime.stop()
    await server.stop()


async def test_knowledge_injected_into_prompt(
    mock_llm_router, provider_router, mock_llm, db
) -> None:
    store, kb = build_memory_stack(db, None)
    await kb.add_document("rules", "群规", "本群禁止发广告，违者踢出。")

    server, runtime, _ = await _spin_up(provider_router, store, kb, MemoryExtractor())
    mock_llm.push("本群禁止广告")
    await server.push_group_message(
        segments=[
            {"type": "at", "data": {"qq": "10000"}},
            {"type": "text", "data": {"text": " soapbot 群里能发广告吗"}},
        ]
    )
    await _wait_sent(server)

    call = mock_llm.last_call()
    assert "禁止发广告" in call.all_text(), "knowledge snippet not injected"

    await runtime.stop()
    await server.stop()


async def test_recall_injects_memory_into_prompt(
    mock_llm_router, provider_router, mock_llm, db
) -> None:
    store, kb = build_memory_stack(db, None)
    await store.add_memory(
        content="用户小明喜欢喝冰美式不加糖",
        scope="onebot11:group:123456",
    )

    server, runtime, _ = await _spin_up(provider_router, store, kb, MemoryExtractor())
    mock_llm.push("你爱喝冰美式")
    await server.push_group_message(
        segments=[
            {"type": "at", "data": {"qq": "10000"}},
            {"type": "text", "data": {"text": " soapbot 我喜欢喝什么咖啡"}},
        ]
    )
    await _wait_sent(server)

    call = mock_llm.last_call()
    everything = call.all_text()
    assert "冰美式" in everything, "recalled memory not injected"
    assert "仅作事实参考" in everything, "memory must be marked advisory"
    # The recalled text must arrive inside the untrusted-data envelope, otherwise a
    # poisoned memory reads exactly like operator instruction text.
    assert "zq7-untrusted-boundary:memory" in everything
    assert "无效" in everything

    await runtime.stop()
    await server.stop()


async def test_timeline_command(mock_llm_router, provider_router, mock_llm, db) -> None:
    store, kb = build_memory_stack(db, None)
    await store.archive_message(
        session_key="onebot11:group:123456", role="user", content="第一条历史", user_name="小明"
    )
    server, runtime, _ = await _spin_up(provider_router, store, kb, MemoryExtractor())
    mock_llm.reset()

    await server.push_group_message(
        segments=[
            {"type": "at", "data": {"qq": "10000"}},
            {"type": "text", "data": {"text": " /timeline 5"}},
        ]
    )
    await _wait_sent(server)
    reply = server.last_sent_text()
    assert "最近" in reply
    assert mock_llm.calls == []

    await runtime.stop()
    await server.stop()
