"""Nine-stage message pipeline.

Stage order is fixed and observable. Each stage may short-circuit by returning
a ``StageResult`` with ``halt=True`` (e.g. not woken, blacklisted, duplicate).

  1. DedupStage        — drop duplicate deliveries from the protocol端
  2. WhitelistStage    — group/private allow-list + blacklist
  3. WakeStage         — @mention / wake-word detection
  4. RecordStage       — persist raw inbound message
  5. PersonaStage      — resolve persona card for this group/user
  6. ContextStage      — load + compress conversation context
  7. ModelStage        — call the provider chain (with tools)
  8. SafetyStage       — output cleaning, length limits
  9. ReplyStage        — deliver via adapter with quota-aware retry

The pipeline is deliberately linear:群聊安全 relies on deterministic checks
running in a known order, not on the model behaving itself.
"""

from __future__ import annotations

import logging
import time
from abc import ABC, abstractmethod
from collections.abc import Awaitable, Callable
from dataclasses import dataclass, field
from typing import Any

from soapbot.core.adapter import Adapter
from soapbot.core.message import IncomingMessage, OutgoingMessage

logger = logging.getLogger(__name__)


@dataclass(slots=True)
class PipelineContext:
    """Mutable state threaded through every stage."""

    event: IncomingMessage
    adapter: Adapter
    started_at: float = field(default_factory=time.time)

    persona_id: str = ""
    persona_prompt: str = ""
    session_id: str = ""
    conversation: list[dict[str, Any]] = field(default_factory=list)
    model_reply: str = ""
    outbound: OutgoingMessage | None = None
    halted: bool = False
    halt_reason: str = ""
    usage: dict[str, Any] = field(default_factory=dict)
    timings: dict[str, float] = field(default_factory=dict)
    extras: dict[str, Any] = field(default_factory=dict)

    def halt(self, reason: str) -> None:
        self.halted = True
        self.halt_reason = reason


@dataclass(slots=True)
class StageResult:
    halt: bool = False
    reason: str = ""


class Stage(ABC):
    name: str = "stage"

    @abstractmethod
    async def run(self, ctx: PipelineContext) -> StageResult:
        """Process the context; return halt=True to stop the chain."""


class Pipeline:
    def __init__(self, stages: list[Stage] | None = None) -> None:
        self.stages: list[Stage] = stages or []
        self._observers: list[Callable[[PipelineContext, Stage, float], Awaitable[None]]] = []

    def add(self, stage: Stage) -> Pipeline:
        self.stages.append(stage)
        return self

    def observe(self, fn: Callable[[PipelineContext, Stage, float], Awaitable[None]]) -> None:
        self._observers.append(fn)

    async def run(self, ctx: PipelineContext) -> PipelineContext:
        for stage in self.stages:
            t0 = time.perf_counter()
            try:
                result = await stage.run(ctx)
            except Exception as exc:
                logger.exception(
                    "stage %s raised for trace=%s: %s", stage.name, ctx.event.trace_id, exc
                )
                ctx.halt(f"stage_error:{stage.name}")
                break
            finally:
                elapsed = (time.perf_counter() - t0) * 1000
                ctx.timings[stage.name] = round(elapsed, 2)
                for obs in self._observers:
                    try:
                        await obs(ctx, stage, elapsed)
                    except Exception:  # pragma: no cover
                        logger.debug("pipeline observer failed", exc_info=True)

            if result.halt:
                ctx.halt(result.reason or stage.name)
                logger.debug(
                    "pipeline halted at %s trace=%s reason=%s",
                    stage.name,
                    ctx.event.trace_id,
                    ctx.halt_reason,
                )
                break
        return ctx
