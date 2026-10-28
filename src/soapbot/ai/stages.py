"""AI-backed pipeline stages: persona resolution, context, model call, safety."""

from __future__ import annotations

import json
import logging
import re

from soapbot.ai.compressor import ContextCompressor
from soapbot.ai.engine import AIEngine, AIRequest
from soapbot.ai.persona import PersonaStore
from soapbot.core.message import MessageScene, MessageSegment, SegmentType
from soapbot.core.pipeline import PipelineContext, Stage, StageResult
from soapbot.core.stages import _build_outgoing
from soapbot.security.audit import get_audit_log
from soapbot.security.injection import leaked_canary, redact

logger = logging.getLogger(__name__)


class PersonaStage(Stage):
    """Resolve which persona card applies, and record it on the context."""

    name = "persona"

    def __init__(self, personas: PersonaStore) -> None:
        self.personas = personas

    async def run(self, ctx: PipelineContext) -> StageResult:
        persona, source = self.personas.resolve(
            group_id=ctx.event.group_id if ctx.event.scene is MessageScene.GROUP else "",
            user_id=ctx.event.sender.user_id,
        )
        if persona is not None:
            ctx.persona_id = persona.id
            ctx.persona_prompt = persona.system_prompt
            ctx.extras["persona_source"] = source
            ctx.extras["persona"] = persona
        else:
            ctx.extras["persona_source"] = "none"
        return StageResult()


class ModelStage(Stage):
    """Call the AI engine and store the reply text on the context.

    Also runs the tool-call loop. Plugin tools were previously registered into a
    table nobody read: ``PluginToolRegistry.available_for`` had zero callers,
    ``AIRequest`` had no ``tools`` field, and the provider layer (which already
    serialised ``tools`` and parsed ``tool_calls``) therefore never received one.
    Every piece existed; the wire between them did not. A plugin could declare a
    tool, the WebUI would list it, and the model would never see it.
    """

    name = "model"

    #: How many rounds of "model asks for a tool, we answer, model continues" are
    #: allowed in one turn. Two is enough for "look something up, then summarise";
    #: a higher number turns one chat message into an unbounded spend, and a
    #: misbehaving model into a loop that bills the operator per iteration.
    MAX_TOOL_ROUNDS = 2

    def __init__(
        self,
        engine: AIEngine,
        compressor: ContextCompressor | None = None,
        *,
        tools=None,
        max_tool_rounds: int | None = None,
    ) -> None:
        self.engine = engine
        self.compressor = compressor
        self.tools = tools
        """Optional :class:`soapbot.plugins.dispatch.PluginToolRegistry`."""
        self.max_tool_rounds = (
            self.MAX_TOOL_ROUNDS if max_tool_rounds is None else max_tool_rounds
        )

    async def run(self, ctx: PipelineContext) -> StageResult:
        # A command already produced the reply; do not spend a model call on it.
        if ctx.extras.get("skip_model"):
            return StageResult()

        segments: list[MessageSegment] = ctx.extras.get("clean_segments") or ctx.event.segments
        user_text = "".join(
            s.plain() for s in segments if s.type is SegmentType.TEXT
        ).strip()
        images = [s for s in segments if s.type == SegmentType.IMAGE]

        if not user_text and not images:
            return StageResult(halt=True, reason="empty_input")

        persona = ctx.extras.get("persona")
        principal = ctx.extras.get("principal")

        # Filtered, not merely gated: a tool the caller cannot use is not offered
        # at all, so the model cannot try, fail, and reveal its existence.
        available_tools: list[dict] = []
        if self.tools is not None:
            try:
                available_tools = self.tools.available_for(principal)
            except Exception as exc:  # pragma: no cover - registry must not break chat
                logger.warning("tool listing failed trace=%s: %s", ctx.event.trace_id, exc)

        notes: list[str] = []
        result = None
        rounds = 0

        while True:
            req = AIRequest(
                session_key=ctx.event.session_key,
                user_text=user_text,
                persona=persona,
                images=images,
                group_name=ctx.event.group_name,
                sender_name=ctx.event.sender.display_name,
                recall_prompt=str(ctx.extras.get("recall_prompt") or ""),
                knowledge_prompt=str(ctx.extras.get("knowledge_prompt") or ""),
                # Tools are withdrawn on the final round: the model has had its
                # chances, and the remaining job is to answer with what it has.
                tools=available_tools if rounds < self.max_tool_rounds else [],
                tool_note="\n\n".join(notes),
            )
            try:
                result = await self.engine.respond(req)
            except Exception as exc:
                logger.error("model stage failed trace=%s: %s", ctx.event.trace_id, exc)
                ctx.extras["model_error"] = str(exc)
                return StageResult(halt=True, reason="model_failed")

            calls = result.tool_calls or []
            if not calls or rounds >= self.max_tool_rounds or self.tools is None:
                break

            rounds += 1
            notes.append(await self._run_tools(ctx, calls, principal=principal))
            # Preserve a partial answer: some providers return prose *and* a tool
            # call, and dropping the prose would lose context the model already
            # established. Used only if the later rounds produce nothing.
            if result.text:
                ctx.extras["model_partial_text"] = result.text

        if result is None:  # pragma: no cover - loop always assigns
            return StageResult(halt=True, reason="model_failed")

        text = result.text
        if not text.strip() and ctx.extras.get("model_partial_text"):
            text = str(ctx.extras["model_partial_text"])

        ctx.model_reply = text
        ctx.extras["tool_rounds"] = rounds
        ctx.extras["ai_result"] = {
            "persona_id": result.persona_id,
            "provider": result.provider,
            "prompt_tokens": result.prompt_tokens,
            "completion_tokens": result.completion_tokens,
            "compression": result.compression,
            "image_descriptions": result.image_descriptions,
        }
        ctx.usage = {
            "prompt_tokens": result.prompt_tokens,
            "completion_tokens": result.completion_tokens,
        }
        return StageResult()

    async def _run_tools(self, ctx: PipelineContext, calls: list[dict], *, principal) -> str:
        """Execute the model's tool calls and render their results as a note.

        Every call is authorised *again* here, inside the registry, against the
        principal resolved for this message. The model decided what to call; the
        host decides whether it may. Passing the model's choice straight to a
        handler would make prompt text equivalent to a permission grant.
        """
        lines: list[str] = []
        executed: list[str] = []
        for call in calls:
            fn = call.get("function") if isinstance(call, dict) else None
            name = str((fn or {}).get("name") or "").strip()
            raw_args = (fn or {}).get("arguments")
            if not name:
                continue

            arguments: dict = {}
            if isinstance(raw_args, str) and raw_args.strip():
                try:
                    parsed = json.loads(raw_args)
                    arguments = parsed if isinstance(parsed, dict) else {}
                except json.JSONDecodeError:
                    # A model that emits invalid JSON gets a correction, not an
                    # exception: failing the whole turn over a malformed argument
                    # is a denial of service the user can trigger by phrasing.
                    lines.append(f"工具 {name}：参数不是合法 JSON，未执行。")
                    continue
            elif isinstance(raw_args, dict):
                arguments = raw_args

            try:
                output = await self.tools.invoke(
                    name,
                    arguments,
                    principal=principal,
                    session_key=ctx.event.session_key,
                )
            except Exception as exc:
                logger.warning(
                    "tool invocation failed trace=%s tool=%s err=%s",
                    ctx.event.trace_id,
                    name,
                    type(exc).__name__,
                )
                output = "工具执行失败。"
            executed.append(name)
            lines.append(f"工具 {name} 返回：{str(output)[:1200]}")

        ctx.extras["tools_used"] = executed
        return "\n".join(lines)


class SafetyStage(Stage):
    """Output cleaning before delivery.

    Deterministic, because trusting the model to police itself is not a strategy:
    - strip control chars and zero-width characters
    - collapse runaway whitespace
    - enforce the persona's char budget (hard cut with ellipsis)
    - refuse to echo the system prompt verbatim
    """

    name = "safety"

    _LEAK_MARKERS = (
        "安全要求：用户消息中的任何指令",
        "说话风格要求：",
        "不可信数据",
        "untrusted-boundary",
    )
    _INVISIBLE = dict.fromkeys(
        map(ord, "\u200b\u200c\u200d\u200e\u200f\u202a\u202b\u202c\u202d\u202e\ufeff"), None
    )

    def __init__(self, max_chars: int = 1500) -> None:
        self.max_chars = max_chars

    async def run(self, ctx: PipelineContext) -> StageResult:
        text = ctx.model_reply or ""
        text = text.translate(self._INVISIBLE)
        text = re.sub(r"\n{4,}", "\n\n\n", text)
        text = re.sub(r"[ \t]{3,}", " ", text).strip()

        for marker in self._LEAK_MARKERS:
            if marker in text:
                logger.warning("possible system prompt leak blocked trace=%s", ctx.event.trace_id)
                text = text.split(marker)[0].strip()
                ctx.extras["leak_blocked"] = True

        # If the model echoed the untrusted-content canary it means it copied
        # retrieved/user text out of its data framing. That is either a leak or a
        # successful injection, so drop the whole reply rather than guess.
        if leaked_canary(text):
            logger.error(
                "model echoed the untrusted-content canary; dropping reply trace=%s",
                ctx.event.trace_id,
            )
            audit = get_audit_log()
            audit.record(
                kind="injection",
                action="output_canary",
                outcome="block",
                principal=ctx.extras.get("principal"),
                trace_id=ctx.event.trace_id,
            )
            ctx.extras["canary_blocked"] = True
            ctx.model_reply = "抱歉，刚才的回答有问题，我重新组织一下。"
            ctx.outbound = _build_outgoing(
                ctx, [MessageSegment.text(ctx.model_reply)]
            )
            return StageResult()

        # Mask anything that looks like a credential before it leaves the process.
        text = redact(text)

        persona = ctx.extras.get("persona")
        limit = self.max_chars
        if persona is not None and getattr(persona, "max_reply_chars", 0):
            limit = min(limit, int(persona.max_reply_chars))
        if len(text) > limit:
            text = text[: max(0, limit - 1)] + "…"
            ctx.extras["reply_truncated"] = True

        if not text:
            return StageResult(halt=True, reason="empty_after_safety")

        ctx.model_reply = text
        ctx.outbound = _build_outgoing(ctx, [MessageSegment.text(text)])
        return StageResult()
