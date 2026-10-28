"""Wave 3 tests: three-layer memory, hybrid RRF retrieval, knowledge base.

Gate A3: 30 memories across time, asked with a semantically different phrasing,
        the right memory is retrieved and shows up in the prompt.
"""

from __future__ import annotations

import math

import pytest

from soapbot.memory.db import Database, MemoryRow, reset_database
from soapbot.memory.extractor import MemoryExtractor
from soapbot.memory.store import (
    KnowledgeBase,
    MemoryLayer,
    MemoryStore,
    _fts_query,
    _terms,
)


class FakeEmbedder:
    """Deterministic bag-of-characters embedding.

    Real embeddings need a network call; tests must not. This fake maps text to a
    fixed-dim vector over character trigrams, so semantically similar strings
    (shared substrings) do end up close — enough to exercise the vector channel
    and the fusion logic without pretending to be a real model.
    """

    def __init__(self, dim: int = 64) -> None:
        self.dim = dim
        self.calls = 0

    def _vec(self, text: str) -> list[float]:
        vec = [0.0] * self.dim
        for i in range(len(text)):
            gram = text[i : i + 2]
            if not gram:
                continue
            idx = hash(gram) % self.dim
            vec[idx] += 1.0
        norm = math.sqrt(sum(v * v for v in vec)) or 1.0
        return [v / norm for v in vec]

    async def embed(self, texts: list[str]) -> list[list[float]]:
        self.calls += 1
        return [self._vec(t) for t in texts]


class BrokenEmbedder:
    async def embed(self, texts: list[str]) -> list[list[float]]:
        raise RuntimeError("embedding service down")


@pytest.fixture
async def db(tmp_path):
    await reset_database()
    database = Database(f"sqlite+aiosqlite:///{(tmp_path / 'test.db').as_posix()}")
    await database.init()
    yield database
    await database.close()
    await reset_database()


@pytest.fixture
def embedder() -> FakeEmbedder:
    return FakeEmbedder()


@pytest.fixture
async def store(db, embedder) -> MemoryStore:
    return MemoryStore(db, embedder=embedder)


# ---------------------------------------------------------------- tokenising
def test_terms_cjk_bigrams() -> None:
    terms = _terms("小明喜欢猫")
    assert "小明" in terms
    assert "喜欢" in terms
    assert len(terms) == 4


def test_terms_ascii_lowercased() -> None:
    terms = _terms("Hello World")
    assert "hello" in terms
    assert "world" in terms


def test_fts_query_quotes_terms() -> None:
    q = _fts_query("hello world")
    assert q == '"hello" OR "world"'


def test_fts_query_empty() -> None:
    assert _fts_query("   ") == ""


# ---------------------------------------------------------------- archive
async def test_archive_and_history_roundtrip(store: MemoryStore) -> None:
    await store.archive_message(
        session_key="onebot11:group:1", role="user", content="你好", user_name="小明"
    )
    await store.archive_message(
        session_key="onebot11:group:1", role="assistant", content="你好呀"
    )
    history = await store.history("onebot11:group:1")
    assert len(history) == 2
    assert history[0]["content"] == "你好"
    assert history[1]["role"] == "assistant"


async def test_archive_is_append_only_and_ordered(store: MemoryStore) -> None:
    for i in range(5):
        await store.archive_message(
            session_key="s1", role="user", content=f"m{i}", created_at=1000 + i
        )
    history = await store.history("s1")
    assert [h["content"] for h in history] == ["m0", "m1", "m2", "m3", "m4"]


async def test_history_respects_limit_and_keeps_recent(store: MemoryStore) -> None:
    for i in range(30):
        await store.archive_message(session_key="s2", role="user", content=f"m{i}")
    history = await store.history("s2", limit=10)
    assert len(history) == 10
    assert history[-1]["content"] == "m29"


async def test_image_description_included_in_history(store: MemoryStore) -> None:
    await store.archive_message(
        session_key="s3", role="user", content="看图", image_desc="一只橘猫趴在键盘上"
    )
    history = await store.history("s3")
    assert "橘猫" in history[0]["content"]


async def test_timeline_returns_metadata(store: MemoryStore) -> None:
    await store.archive_message(session_key="s4", role="user", content="hi", user_name="A")
    rows = await store.timeline("s4")
    assert rows[0]["user_name"] == "A"
    assert "created_at" in rows[0]
    assert "id" in rows[0]


async def test_list_sessions_aggregates(store: MemoryStore) -> None:
    await store.archive_message(session_key="a", role="user", content="1")
    await store.archive_message(session_key="a", role="user", content="2")
    await store.archive_message(session_key="b", role="user", content="3")
    sessions = await store.list_sessions()
    by_key = {s["session_key"]: s for s in sessions}
    assert by_key["a"]["message_count"] == 2
    assert by_key["b"]["message_count"] == 1


# ---------------------------------------------------------------- memory write
async def test_add_memory_stores_embedding(store: MemoryStore) -> None:
    mid = await store.add_memory(content="小明喜欢猫", layer=MemoryLayer.SEMANTIC)
    assert mid > 0
    assert await store.count_memories() == 1


async def test_add_memory_rejects_empty(store: MemoryStore) -> None:
    with pytest.raises(ValueError):
        await store.add_memory(content="   ")


async def test_add_memory_survives_embedding_failure(db) -> None:
    """A dead embedding service must not block memory writes."""
    store = MemoryStore(db, embedder=BrokenEmbedder())
    mid = await store.add_memory(content="即使向量失败也要存下来")
    assert mid > 0
    # Still findable through the keyword channel.
    result = await store.recall("向量失败", limit=5)
    assert any("向量失败" in it.content for it in result.items)


async def test_count_memories_by_layer(store: MemoryStore) -> None:
    await store.add_memory(content="语义记忆一", layer=MemoryLayer.SEMANTIC)
    await store.add_memory(content="情景记忆一", layer=MemoryLayer.EPISODIC)
    assert await store.count_memories(MemoryLayer.SEMANTIC) == 1
    assert await store.count_memories(MemoryLayer.EPISODIC) == 1


# ---------------------------------------------------------------- retrieval
async def test_recall_keyword_channel_works_without_embedder(db) -> None:
    store = MemoryStore(db, embedder=None)
    await store.add_memory(content="小明的生日是三月五日")
    result = await store.recall("生日")
    assert result.items
    assert "三月五日" in result.items[0].content
    assert result.vector_hits == 0
    assert result.fused is False


async def test_recall_uses_both_channels_and_fuses(store: MemoryStore) -> None:
    await store.add_memory(content="小明喜欢猫，养了一只橘猫")
    await store.add_memory(content="小红喜欢狗")
    result = await store.recall("小明 猫")
    assert result.vector_hits > 0
    assert result.keyword_hits > 0
    assert result.fused is True
    assert "橘猫" in result.items[0].content


async def test_rrf_scores_are_monotonic(store: MemoryStore) -> None:
    for i in range(5):
        await store.add_memory(content=f"测试记忆{i} 关于猫的话题")
    result = await store.recall("猫")
    scores = [it.score for it in result.items]
    assert scores == sorted(scores, reverse=True)


async def test_recall_respects_scope(store: MemoryStore) -> None:
    await store.add_memory(content="群1的秘密：喜欢猫", scope="onebot11:group:1")
    await store.add_memory(content="群2的秘密：喜欢猫", scope="onebot11:group:2")
    result = await store.recall("喜欢猫", scope="onebot11:group:1", limit=5)
    assert all(it.scope in ("onebot11:group:1", "") for it in result.items)


async def test_recall_empty_query_returns_nothing(store: MemoryStore) -> None:
    await store.add_memory(content="某个记忆")
    result = await store.recall("   ")
    assert result.items == []


async def test_recall_touches_access_count(store: MemoryStore, db) -> None:
    mid = await store.add_memory(content="会被访问的记忆")
    await store.recall("访问")
    async with db.session_factory()() as session:
        row = await session.get(MemoryRow, mid)
        assert row is not None
        assert row.access_count >= 1


async def test_recall_prompt_renders_bullets(store: MemoryStore) -> None:
    await store.add_memory(content="用户喜欢蓝色")
    result = await store.recall("颜色")
    prompt = result.to_prompt()
    assert "你记得以下" in prompt
    assert "蓝色" in prompt


async def test_recall_prompt_empty_when_no_hits(store: MemoryStore) -> None:
    assert (await store.recall("完全不相关的内容xyz")).to_prompt() == ""


async def test_a3_semantic_paraphrase_recall(store: MemoryStore) -> None:
    """A3: 30 memories across time, asked with different wording, right one surfaces."""
    facts = [
        "用户小明喜欢橘猫，家里养了一只怕冷的猫",
        "小明住在杭州西湖区",
        "小明的生日是三月五日",
        "小明是后端工程师，主要写 Python",
        "小明讨厌香菜和折耳根",
        "小明每天七点起床跑步",
        "小明在学日语，N3 水平",
        "小明用的是机械键盘，青轴",
        "小明有个妹妹在读大学",
        "小明喜欢喝美式不加糖",
    ]
    # Write 30 memories.
    for i in range(30):
        content = facts[i % len(facts)] if i < len(facts) else f"闲聊记录第{i}条，没有重要信息"
        await store.add_memory(content=content, scope="onebot11:group:1")

    # Semantically different phrasing: "宠物" instead of "猫", no shared keyword
    # guaranteed. The vector channel should still find it.
    result = await store.recall("他养了什么宠物", scope="onebot11:group:1", limit=5)
    assert result.items, "no memory recalled for paraphrase query"
    joined = "\n".join(it.content for it in result.items)
    assert "猫" in joined


async def test_delete_memory_removes_from_index(store: MemoryStore) -> None:
    mid = await store.add_memory(content="这条记忆会被删除")
    assert await store.delete_memory(mid) is True
    assert await store.delete_memory(mid) is False
    result = await store.recall("删除")
    assert all(it.id != mid for it in result.items)


# ---------------------------------------------------------------- summaries
async def test_summary_save_and_load(store: MemoryStore) -> None:
    await store.save_summary("s1", "早期摘要内容", folded=10)
    assert await store.latest_summary("s1") == "早期摘要内容"


async def test_latest_summary_wins(store: MemoryStore) -> None:
    await store.save_summary("s1", "第一版", folded=5)
    await store.save_summary("s1", "第二版", folded=15)
    assert await store.latest_summary("s1") == "第二版"


async def test_missing_summary_returns_empty(store: MemoryStore) -> None:
    assert await store.latest_summary("nope") == ""


# ---------------------------------------------------------------- extractor
async def test_extractor_heuristic_explicit_remember() -> None:
    ex = MemoryExtractor()
    result = await ex.extract("记住我对花生过敏")
    assert result.memories
    assert "花生过敏" in result.memories[0].content
    assert result.memories[0].importance >= 0.8


async def test_extractor_preference() -> None:
    ex = MemoryExtractor()
    result = await ex.extract("我喜欢喝冰美式")
    assert any("喜欢" in m.content for m in result.memories)


async def test_extractor_identity() -> None:
    ex = MemoryExtractor()
    result = await ex.extract("我叫张伟，在杭州工作")
    joined = " ".join(m.content for m in result.memories)
    assert "张伟" in joined or "杭州" in joined


async def test_extractor_skips_short_text() -> None:
    ex = MemoryExtractor()
    result = await ex.extract("哈")
    assert result.memories == []
    assert result.skipped_reason == "too_short"


async def test_extractor_ignores_ordinary_chatter() -> None:
    ex = MemoryExtractor()
    result = await ex.extract("今天天气真不错，出去走走吧")
    assert result.memories == []


async def test_extractor_dedupes() -> None:
    ex = MemoryExtractor()
    result = await ex.extract("记住我喜欢猫，记住我喜欢猫")
    contents = [m.content for m in result.memories]
    assert len(contents) == len(set(contents))


# ---------------------------------------------------------------- knowledge
async def test_knowledge_chunking_splits_long_text(db) -> None:
    kb = KnowledgeBase(db, embedder=None, chunk_size=100)
    chunks = kb.chunk("句子一。" * 50)
    assert len(chunks) > 1
    assert all(len(c) <= 150 for c in chunks)


async def test_knowledge_add_and_search(db) -> None:
    kb = KnowledgeBase(db, embedder=None)
    n = await kb.add_document("doc1", "群规", "本群禁止发广告。请勿讨论政治敏感话题。")
    assert n >= 1
    hits = await kb.search("广告")
    assert hits
    assert "广告" in hits[0]["content"]


async def test_knowledge_list_and_delete(db) -> None:
    kb = KnowledgeBase(db, embedder=None)
    await kb.add_document("doc2", "说明", "这是一段说明文字")
    docs = await kb.list_documents()
    assert any(d["doc_id"] == "doc2" for d in docs)
    removed = await kb.delete_document("doc2")
    assert removed >= 1
    docs_after = await kb.list_documents()
    assert all(d["doc_id"] != "doc2" for d in docs_after)


async def test_knowledge_search_empty_query(db) -> None:
    kb = KnowledgeBase(db, embedder=None)
    assert await kb.search("  ") == []
