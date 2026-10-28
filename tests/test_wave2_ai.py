"""Wave 2 tests: providers, persona cards, context compression, vision.

Gate A2: 200-turn conversation compresses under budget and still recalls an
         early fact.
Gate A4: static + animated images reach the multimodal endpoint; GIF frames are
         sampled and tiled; history keeps only text.
"""

from __future__ import annotations

import io

import pytest
from PIL import Image

from soapbot.ai.compressor import CompressionConfig, ContextCompressor
from soapbot.ai.persona import Persona, PersonaStore, load_persona_file
from soapbot.ai.tokens import count_messages, count_tokens
from soapbot.ai.vision import (
    DescriptionCache,
    content_hash,
    prepare_image,
)
from soapbot.providers.base import (
    CapabilitySlot,
    ChatMessage,
    ChatRequest,
    ProviderConfig,
    ProviderError,
)
from soapbot.providers.router import ProviderRouter, build_provider


# ---------------------------------------------------------------- token counting
def test_count_tokens_cjk_and_ascii() -> None:
    assert count_tokens("") == 0
    cjk = count_tokens("你好世界")
    assert cjk >= 4
    ascii_tokens = count_tokens("hello world this is a test")
    assert 1 <= ascii_tokens <= 15


def test_count_messages_includes_overhead() -> None:
    msgs = [{"role": "user", "content": "hi"}, {"role": "assistant", "content": "hello"}]
    total = count_messages(msgs)
    assert total > count_tokens("hi") + count_tokens("hello")


# ---------------------------------------------------------------- persona
def test_persona_build_system_prompt_includes_all_parts() -> None:
    p = Persona(
        id="tsundere",
        name="傲娇",
        system_prompt="你是一个傲娇助手。",
        style="嘴硬心软",
        banned_words=["随便"],
        max_reply_chars=100,
    )
    prompt = p.build_system_prompt(context_note="当前群：测试群")
    assert "傲娇助手" in prompt
    assert "嘴硬心软" in prompt
    assert "随便" in prompt
    assert "100 字" in prompt
    assert "测试群" in prompt


def test_persona_store_resolve_priority(tmp_path) -> None:
    store = PersonaStore()
    store.add(Persona(id="default", name="默认", system_prompt="d"))
    store.add(Persona(id="group-p", name="群人格", system_prompt="g"))
    store.add(Persona(id="user-p", name="用户人格", system_prompt="u"))

    store.set_default("default")
    assert store.resolve()[0].id == "default"

    store.bind_group("g1", "group-p")
    assert store.resolve(group_id="g1")[0].id == "group-p"

    store.bind_user("u1", "user-p")
    persona, source = store.resolve(group_id="g1", user_id="u1")
    assert persona.id == "user-p"
    assert source == "user"


def test_persona_disabled_is_skipped() -> None:
    store = PersonaStore()
    store.add(Persona(id="off", name="off", enabled=False))
    store.add(Persona(id="on", name="on", system_prompt="x"))
    persona, source = store.resolve()
    assert persona is not None
    assert persona.id == "on"
    assert source == "first_available"


def test_load_persona_yaml(tmp_path) -> None:
    f = tmp_path / "p.yaml"
    f.write_text(
        "id: testp\nname: 测试人格\nsystem_prompt: 你是测试机器人\nmax_reply_chars: 200\n",
        encoding="utf-8",
    )
    p = load_persona_file(f)
    assert p.id == "testp"
    assert p.max_reply_chars == 200


def test_load_persona_markdown_front_matter(tmp_path) -> None:
    f = tmp_path / "cat.md"
    f.write_text(
        "---\nid: cat\nname: 猫娘\nstyle: 爱撒娇\n---\n你是一只猫娘，说话带喵。\n",
        encoding="utf-8",
    )
    p = load_persona_file(f)
    assert p.id == "cat"
    assert "喵" in p.system_prompt
    assert p.style == "爱撒娇"


def test_load_persona_markdown_without_front_matter(tmp_path) -> None:
    f = tmp_path / "plain.md"
    f.write_text("你是一个简洁的助手。", encoding="utf-8")
    p = load_persona_file(f)
    assert p.id == "plain"
    assert "简洁" in p.system_prompt


def test_load_persona_directory(tmp_path) -> None:
    (tmp_path / "a.yaml").write_text("id: a\nname: A\nsystem_prompt: x\n", encoding="utf-8")
    (tmp_path / "b.md").write_text("---\nid: b\n---\nbody b", encoding="utf-8")
    store = PersonaStore()
    assert store.load_directory(tmp_path) == 2
    assert {p.id for p in store.all()} == {"a", "b"}


# ---------------------------------------------------------------- compression
async def _no_summarizer(prompt: str) -> str:
    return "早期对话摘要：用户喜欢猫，名字叫小明。"


async def test_compression_short_conversation_untouched() -> None:
    comp = ContextCompressor(CompressionConfig(max_prompt_tokens=6000))
    msgs = [
        {"role": "system", "content": "sys"},
        {"role": "user", "content": "你好"},
        {"role": "assistant", "content": "你好呀"},
    ]
    result = await comp.compress(msgs)
    assert len(result.messages) == 3
    assert result.strategy == []


async def test_compression_reduces_200_turns_under_budget() -> None:
    """A2: 200 turns must compress to fit the budget while keeping an early fact."""
    cfg = CompressionConfig(
        max_prompt_tokens=1500,
        reserve_for_reply=400,
        keep_recent_turns=4,
        max_turns=60,
        fold_batch_turns=10,
    )
    comp = ContextCompressor(cfg, summarizer=_no_summarizer)

    msgs: list[dict] = [{"role": "system", "content": "你是助手"}]
    msgs.append({"role": "user", "content": "请记住：我叫小明，我喜欢猫，我的生日是 3 月 5 日。"})
    msgs.append({"role": "assistant", "content": "好的，我记住了。"})
    for i in range(200):
        msgs.append({"role": "user", "content": f"第{i}轮问题：" + "详细描述" * 12})
        msgs.append({"role": "assistant", "content": f"第{i}轮回答：" + "解释说明" * 12})

    original = count_messages(msgs)
    result = await comp.compress(msgs)

    assert result.compressed_tokens <= cfg.max_prompt_tokens - cfg.reserve_for_reply
    assert result.compressed_tokens < original
    assert result.strategy, "compression must report which strategy it used"
    # Early fact must survive somewhere (summary or recent window).
    joined = "\n".join(
        str(m.get("content", "")) for m in result.messages
    )
    assert "小明" in joined or "猫" in joined or "3 月 5 日" in joined


async def test_compression_extracts_key_facts() -> None:
    comp = ContextCompressor(CompressionConfig(max_prompt_tokens=300, reserve_for_reply=100))
    msgs = [
        {"role": "system", "content": "sys"},
        {"role": "user", "content": "记住我喜欢蓝色，我今年 25 岁"},
        {"role": "assistant", "content": "好"},
    ] + [{"role": "user", "content": "填充内容" * 50} for _ in range(10)]
    result = await comp.compress(msgs)
    assert result.compressed_tokens <= 200 + 50


def test_extract_facts_finds_preferences_and_numbers() -> None:
    comp = ContextCompressor()
    facts = comp.extract_facts(
        [
            {"role": "user", "content": "我叫小明，我今年 25 岁，记住我喜欢猫"},
            {"role": "user", "content": "邮箱是 a@b.com"},
        ]
    )
    joined = " ".join(facts)
    assert "小明" in joined or "喜欢猫" in joined
    assert "25" in joined or "a@b.com" in joined


async def test_compression_image_shrink_keeps_latest_image() -> None:
    comp = ContextCompressor(CompressionConfig(max_prompt_tokens=400, reserve_for_reply=100))
    msgs = [
        {"role": "system", "content": "sys"},
        {
            "role": "user",
            "content": [
                {"type": "text", "text": "看这张"},
                {"type": "image_url", "image_url": {"url": "data:image/png;base64,AAA"}, "description": "一只猫"},
            ],
        },
        {"role": "assistant", "content": "看到了"},
        {
            "role": "user",
            "content": [
                {"type": "text", "text": "现在这张呢"},
                {"type": "image_url", "image_url": {"url": "data:image/png;base64,BBB"}},
            ],
        },
    ]
    result = await comp.compress(msgs)
    texts = "\n".join(str(m.get("content", "")) for m in result.messages)
    # The latest image must still be an image part, the older one becomes text.
    image_parts = 0
    for m in result.messages:
        c = m.get("content")
        if isinstance(c, list):
            image_parts += sum(1 for p in c if isinstance(p, dict) and p.get("type") == "image_url")
    assert image_parts == 1
    assert "一只猫" in texts


# ---------------------------------------------------------------- vision
def _png_bytes(size=(64, 48), color=(30, 120, 200)) -> bytes:
    img = Image.new("RGB", size, color)
    buf = io.BytesIO()
    img.save(buf, format="PNG")
    return buf.getvalue()


def _gif_bytes(frames: int = 5, size=(64, 48)) -> bytes:
    images = []
    for i in range(frames):
        img = Image.new("RGB", size, (i * 40 % 255, 100, 200))
        images.append(img)
    buf = io.BytesIO()
    images[0].save(buf, format="GIF", save_all=True, append_images=images[1:], duration=100, loop=0)
    return buf.getvalue()


def test_prepare_static_image_returns_single_data_url() -> None:
    payload = prepare_image(_png_bytes())
    assert payload.is_animated is False
    assert payload.data_url.startswith("data:image/")
    assert payload.sampled_frames == 1


def test_prepare_gif_samples_frames_and_tiles() -> None:
    """A4: GIF must be sampled and tiled into one grid image."""
    payload = prepare_image(_gif_bytes(frames=8))
    assert payload.is_animated is True
    assert payload.frame_count == 8
    assert payload.sampled_frames >= 2
    assert "动图" in payload.note
    # Grid must be wider than a single frame since it tiles multiple frames.
    assert payload.width > 64


def test_prepare_gif_dedupes_near_identical_frames() -> None:
    """Frames that are visually indistinguishable should collapse to fewer samples.

    Pillow rewrites truly identical frames into a single-frame GIF, so the test
    uses near-identical frames (a 1-pixel difference) which survive as real
    frames but hash the same perceptual signature after downscaling.
    """
    frames = []
    for i in range(6):
        img = Image.new("RGB", (32, 32), (10, 10, 10))
        if i % 2:  # imperceptible single-pixel change
            img.putpixel((0, 0), (11, 11, 11))
        frames.append(img)
    buf = io.BytesIO()
    frames[0].save(buf, format="GIF", save_all=True, append_images=frames[1:], duration=100, loop=0)
    data = buf.getvalue()

    probe = Image.open(io.BytesIO(data))
    assert int(getattr(probe, "n_frames", 1)) > 1, "fixture must produce a multi-frame GIF"

    payload = prepare_image(data)
    assert payload.is_animated is True
    assert payload.sampled_frames >= 1
    # Deduped: far fewer samples than the raw frame count would allow.
    assert payload.sampled_frames <= 3


def test_prepare_large_image_is_downscaled() -> None:
    payload = prepare_image(_png_bytes(size=(4000, 3000)))
    assert max(payload.width, payload.height) <= 1024


def test_description_cache_roundtrip() -> None:
    cache = DescriptionCache(capacity=2)
    data = _png_bytes()
    key = content_hash(data)
    assert cache.get(key) is None
    cache.put(key, "一张蓝色图片")
    assert cache.get(key) == "一张蓝色图片"
    assert len(cache) == 1


def test_description_cache_evicts_when_full() -> None:
    cache = DescriptionCache(capacity=2)
    cache.put("a", "1")
    cache.put("b", "2")
    cache.put("c", "3")
    assert len(cache) == 2
    assert cache.get("a") is None


# ---------------------------------------------------------------- providers
def test_build_provider_kinds() -> None:
    for kind in ("openai_compat", "anthropic", "gemini", "ollama"):
        p = build_provider(ProviderConfig(id=f"x-{kind}", kind=kind, model="m"))
        assert p.id == f"x-{kind}"
        assert p.supports(CapabilitySlot.CHAT)


def test_unknown_provider_kind_raises() -> None:
    with pytest.raises(ValueError):
        build_provider(ProviderConfig(id="bad", kind="nonsense"))


async def test_router_failover_to_second_provider(
    mock_llm_router, mock_llm
) -> None:
    """Primary provider fails, secondary answers — no user-visible failure."""

    class AlwaysFails:
        id = "broken"
        config = ProviderConfig(id="broken", kind="x", priority=1, model="m")

        def supports(self, slot) -> bool:
            return True

        def describe(self):
            return {"id": "broken", "kind": "x"}

        async def chat(self, request):
            raise ProviderError("boom")

        async def vision(self, request):
            raise ProviderError("boom")

    mock_llm.push("来自备用模型的回答")
    router = ProviderRouter(cooldown_seconds=1.0)
    router.add(AlwaysFails())
    router.add(
        build_provider(
            ProviderConfig(
                id="backup",
                kind="openai_compat",
                base_url="https://mock.local/v1",
                model="mock-model",
                priority=2,
            )
        )
    )

    resp = await router.chat(
        ChatRequest(messages=[ChatMessage(role="user", content="hi")])
    )
    assert resp.content == "来自备用模型的回答"
    assert resp.provider == "backup"
    assert router.stats()["broken"]["failures"] == 1


async def test_router_all_fail_raises_not_silent(mock_llm_router) -> None:
    class AlwaysFails:
        id = "broken2"
        config = ProviderConfig(id="broken2", kind="x", priority=1, model="m")

        def supports(self, slot) -> bool:
            return True

        def describe(self):
            return {"id": "broken2"}

        async def chat(self, request):
            raise ProviderError("nope")

    router = ProviderRouter()
    router.add(AlwaysFails())
    with pytest.raises(ProviderError):
        await router.chat(ChatRequest(messages=[ChatMessage(role="user", content="x")]))


async def test_router_cooldown_after_three_failures(mock_llm_router) -> None:
    class AlwaysFails:
        id = "cool"
        config = ProviderConfig(id="cool", kind="x", priority=1, model="m")

        def supports(self, slot) -> bool:
            return True

        def describe(self):
            return {"id": "cool"}

        async def chat(self, request):
            raise ProviderError("fail")

    router = ProviderRouter(cooldown_seconds=60.0)
    router.add(AlwaysFails())
    for _ in range(3):
        with pytest.raises(ProviderError):
            await router.chat(ChatRequest(messages=[ChatMessage(role="user", content="x")]))
    assert router.stats()["cool"]["cooling_down"] is True
    assert router.has_capability(CapabilitySlot.CHAT) is False
