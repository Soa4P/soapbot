"""The rolling summary must outlive the request that produced it.

Why this file exists
--------------------
``ContextCompressor.compress`` already accepts ``prior_summary`` and returns an updated
``CompressionResult.summary``; ``MemoryStore`` already has ``latest_summary`` /
``save_summary``; ``MemoryStage`` already injects ``【会话摘要】``. What was missing was an
owner: ``AIEngine._prepare`` called ``compress(messages)`` with no prior and threw the
result away. Every turn therefore re-summarised from scratch, folded history lived for
exactly one request, and the L1 table had a reader and an injector but no writer.

The tests below pin the two halves of that loop. They deliberately drive ``_prepare``
directly: the property under test is what reaches the compressor and what is persisted,
not what a provider answers.

The failure policy is part of the contract. A summary is an improvement to context, not a
precondition for replying — a broken store must never become a message with no answer.
"""

from __future__ import annotations

from pathlib import Path
from typing import Any

from soapbot.ai.compressor import CompressionResult
from soapbot.ai.engine import AIEngine, AIRequest
from soapbot.ai.persona import Persona, PersonaStore
from soapbot.ai.vision import DescriptionCache


class _RecordingCompressor:
    """Records the prior summary it was handed and returns a predictable new one."""

    def __init__(self, summary: str = "folded") -> None:
        self.prior: list[str] = []
        self.summary = summary

    async def compress(
        self, messages: list[dict[str, Any]], *, prior_summary: str = ""
    ) -> CompressionResult:
        self.prior.append(prior_summary)
        return CompressionResult(
            messages=messages,
            summary=self.summary,
            original_tokens=10,
            compressed_tokens=5,
            folded_turns=1,
        )


def _engine(
    compressor: Any, *, loader: Any = None, saver: Any = None
) -> AIEngine:
    personas = PersonaStore()
    personas.add(Persona(id="t", name="测试", system_prompt="你是测试助手。"))
    personas.set_default("t")
    return AIEngine(
        router=object(),  # _prepare never touches the router
        personas=personas,
        compressor=compressor,
        descriptions=DescriptionCache(),
        summary_loader=loader,
        summary_saver=saver,
    )


def _request() -> AIRequest:
    return AIRequest(session_key="session-1", user_text="继续", persona=None)


async def test_summary_round_trips_across_turns() -> None:
    """Turn 2 must be told what turn 1 folded away."""
    saved: dict[str, tuple[str, int]] = {}

    async def saver(key: str, summary: str, folded: int) -> None:
        saved[key] = (summary, folded)

    async def loader(key: str) -> str:
        return saved.get(key, ("", 0))[0]

    recorder = _RecordingCompressor("第一轮的折叠摘要")
    engine = _engine(recorder, loader=loader, saver=saver)

    await engine._prepare(_request())
    assert saved == {"session-1": ("第一轮的折叠摘要", 1)}
    assert recorder.prior == [""], "the first turn has no prior to load"

    recorder.summary = "第二轮带着旧摘要的新摘要"
    await engine._prepare(_request())
    assert recorder.prior[-1] == "第一轮的折叠摘要"
    assert saved["session-1"][0] == "第二轮带着旧摘要的新摘要"


async def test_an_unchanged_summary_is_not_written_again() -> None:
    """A turn that folds nothing must not append a duplicate L1 row."""
    writes: list[str] = []

    async def saver(_key: str, summary: str, _folded: int) -> None:
        writes.append(summary)

    async def loader(_key: str) -> str:
        return "已存在的摘要"

    recorder = _RecordingCompressor("已存在的摘要")
    engine = _engine(recorder, loader=loader, saver=saver)

    await engine._prepare(_request())
    assert writes == []
    assert recorder.prior == ["已存在的摘要"]


async def test_a_failed_summary_load_cannot_break_the_turn() -> None:
    async def broken_loader(_key: str) -> str:
        raise RuntimeError("database unavailable")

    recorder = _RecordingCompressor("folded anyway")
    engine = _engine(recorder, loader=broken_loader, saver=None)

    result = await engine._prepare(_request())
    assert recorder.prior == [""]
    assert result[-1].messages, "the request was still assembled"


async def test_a_failed_summary_save_cannot_break_the_turn() -> None:
    async def broken_saver(_key: str, _summary: str, _folded: int) -> None:
        raise RuntimeError("database unavailable")

    recorder = _RecordingCompressor("folded anyway")
    engine = _engine(recorder, loader=None, saver=broken_saver)

    result = await engine._prepare(_request())
    assert recorder.prior == [""]
    assert result[-1].messages, "a write failure must not discard the assembled request"


def test_builder_wires_the_store_to_the_engine() -> None:
    """A reader/writer with no wiring is the exact bug this file was written for.

    Static on purpose: constructing the full runtime needs a database, providers and a
    persona store, and the thing that can silently disappear here is two keyword
    arguments — not a behaviour.
    """
    source = (
        Path(__file__).resolve().parents[1] / "src" / "soapbot" / "core" / "builder.py"
    ).read_text(encoding="utf-8")
    assert "summary_loader=memory.latest_summary" in source, "summary reader is unwired"
    assert "summary_saver=memory.save_summary" in source, "summary writer is unwired"
