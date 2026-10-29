"""Concrete pipeline stages that do not depend on the AI layer.

Waves 2+ append model/persona/memory stages; keeping the deterministic gates
here makes the群聊安全顺序 explicit and testable.
"""

from __future__ import annotations

import logging
import re
import time
from collections import OrderedDict
from dataclasses import dataclass, field

from soapbot.core.adapter import Capability
from soapbot.core.message import MessageScene, MessageSegment, SegmentType
from soapbot.core.pipeline import PipelineContext, Stage, StageResult
from soapbot.security.principal import normalize_id
from soapbot.voice.tts import VoiceUnavailableError

logger = logging.getLogger(__name__)


class DedupStage(Stage):
    """Drop duplicate message ids.

    Protocol端 reconnects replay events; without dedup the bot answers twice.
    Bounded LRU so memory cannot grow without limit.
    """

    name = "dedup"

    def __init__(self, capacity: int = 2000) -> None:
        self._seen: OrderedDict[str, float] = OrderedDict()
        self._capacity = capacity

    async def run(self, ctx: PipelineContext) -> StageResult:
        mid = ctx.event.message_id
        if mid:
            if mid in self._seen:
                return StageResult(halt=True, reason="duplicate")
            self._seen[mid] = time.time()
            if len(self._seen) > self._capacity:
                self._seen.popitem(last=False)
        return StageResult()


@dataclass(slots=True)
class AccessPolicy:
    """Group/private allow-lists.

    Two deliberate changes from the naive "empty list means allow all" model:

    1. **Identifiers are normalised on both sides.** Allow-lists are operator
       input; message ids come from the wire. Comparing raw strings means
       ``" 20001"``, ``"+20001"``, ``"２０００１"`` or a value padded with a
       zero-width character can miss a blacklist entry while still being the same
       account. Normalisation happens here, at the single comparison point.
    2. **Private chat defaults to deny.** An unlisted DM previously reached the full
       pipeline: persona, memory recall, RAG, tools. A stranger DMing the bot is the
       cheapest possible exfiltration channel, so ``private_allowlist`` is now
       *exclusive* — empty means "nobody", and the operator must name allowed users.
       Groups keep the "empty means allow all" behaviour because the bot has to be
       joinable to be usable, and group access is further constrained downstream by
       the wake rule and the principal's role.
    """

    group_allowlist: set[str] = field(default_factory=set)
    private_allowlist: set[str] = field(default_factory=set)
    group_blacklist: set[str] = field(default_factory=set)
    user_blacklist: set[str] = field(default_factory=set)
    allow_all_private: bool = False
    """Explicit opt-in for 'anyone may DM the bot'. Off by default."""

    def allows(self, scene: MessageScene, group_id: str, user_id: str) -> tuple[bool, str]:
        uid = normalize_id(user_id)
        gid = normalize_id(group_id)
        banned = {normalize_id(u) for u in self.user_blacklist}

        if uid and uid in banned:
            return False, "user_blacklisted"

        if scene is MessageScene.GROUP:
            if gid in {normalize_id(g) for g in self.group_blacklist}:
                return False, "group_blacklisted"
            if self.group_allowlist and gid not in {
                normalize_id(g) for g in self.group_allowlist
            }:
                return False, "group_not_allowed"
            return True, ""

        if not uid:
            return False, "private_no_identity"
        if self.allow_all_private:
            return True, ""
        if uid not in {normalize_id(u) for u in self.private_allowlist}:
            return False, "private_not_allowed"
        return True, ""


class WhitelistStage(Stage):
    name = "whitelist"

    def __init__(self, policy: AccessPolicy | None = None) -> None:
        self.policy = policy or AccessPolicy()

    async def run(self, ctx: PipelineContext) -> StageResult:
        ok, reason = self.policy.allows(
            ctx.event.scene, ctx.event.group_id, ctx.event.sender.user_id
        )
        if not ok:
            return StageResult(halt=True, reason=reason)
        return StageResult()


@dataclass(slots=True)
class WakePolicy:
    """How the bot decides a group message is addressed to it."""

    wake_words: list[str] = field(default_factory=lambda: ["soapbot", "/"])
    prefix_only: bool = False
    """When True, only the leading token is checked (cheaper, stricter)."""
    require_at_in_group: bool = True
    """When True, a group message needs an ``at`` segment OR a wake word."""

    def is_woken(self, ctx: PipelineContext) -> tuple[bool, str]:
        event = ctx.event
        if event.scene is MessageScene.PRIVATE:
            return True, "private"

        if self.require_at_in_group:
            for seg in event.segments:
                if seg.type is SegmentType.AT and str(seg.data.get("qq", "")) == str(event.self_id):
                    return True, "at"

        text = event.text.lower()
        for word in self.wake_words:
            w = word.lower()
            if not w:
                continue
            if self.prefix_only:
                if text.startswith(w):
                    return True, f"wake_word:{word}"
            elif w in text:
                return True, f"wake_word:{word}"
        return False, ""


class WakeStage(Stage):
    name = "wake"

    def __init__(self, policy: WakePolicy | None = None) -> None:
        self.policy = policy or WakePolicy()

    async def run(self, ctx: PipelineContext) -> StageResult:
        woken, how = self.policy.is_woken(ctx)
        if not woken:
            return StageResult(halt=True, reason="not_woken")
        ctx.extras["wake_reason"] = how
        return StageResult()


_WAKE_PREFIX_RE = re.compile(r"^[/!]?\s*", re.UNICODE)

#: Characters that introduce a slash command. They may also be configured as wake
#: words, but they must never be stripped from the text — see StripWakeWordStage.
_COMMAND_PREFIXES = frozenset({"/", "!", "／", "！"})


class StripWakeWordStage(Stage):
    """Remove the wake word / leading @ from the text handed to the model."""

    name = "strip_wake"

    def __init__(self, wake_words: list[str] | None = None) -> None:
        self.wake_words = wake_words or []

    async def run(self, ctx: PipelineContext) -> StageResult:
        cleaned: list[MessageSegment] = []
        dropped_at = False
        for seg in ctx.event.segments:
            if (
                seg.type is SegmentType.AT
                and not dropped_at
                and str(seg.data.get("qq", "")) == str(ctx.event.self_id)
            ):
                dropped_at = True
                continue
            if seg.type is SegmentType.TEXT:
                text = str(seg.data.get("text", ""))
                # Never strip a command prefix. ``/`` and ``!`` are valid wake
                # words, and stripping them turns ``/budget`` into ``budget`` —
                # which ``CommandStage`` does not recognise, so *every* slash
                # command silently stops working while the rest of the bot looks
                # fine. (It surfaces only as an empty reply, which reads like a
                # model failure, not a configuration one.)
                for word in self.wake_words:
                    if not word or word in _COMMAND_PREFIXES:
                        continue
                    if text.lower().startswith(word.lower()):
                        text = text[len(word) :]
                        break
                cleaned.append(MessageSegment.text(text))
            else:
                cleaned.append(seg)
        ctx.extras["clean_segments"] = cleaned
        return StageResult()


class SanitizeStage(Stage):
    """Normalise text: strip control chars, collapse whitespace, cap length.

    Guards the model from prompt-injection via zero-width / bidi characters
    which are invisible to humans but steer a model.
    """

    name = "sanitize"

    _INVISIBLE = dict.fromkeys(
        map(ord, "\u200b\u200c\u200d\u200e\u200f\u202a\u202b\u202c\u202d\u202e\ufeff"), None
    )

    def __init__(self, max_chars: int = 4000) -> None:
        self.max_chars = max_chars

    async def run(self, ctx: PipelineContext) -> StageResult:
        segments: list[MessageSegment] = []
        for seg in ctx.extras.get("clean_segments") or ctx.event.segments:
            if seg.type is SegmentType.TEXT:
                text = str(seg.data.get("text", "")).translate(self._INVISIBLE)
                text = re.sub(r"[ \t]{2,}", " ", text)
                segments.append(MessageSegment.text(text))
            else:
                segments.append(seg)

        total = sum(len(s.plain()) for s in segments)
        if total > self.max_chars:
            budget = self.max_chars
            trimmed: list[MessageSegment] = []
            for seg in segments:
                if seg.type is not SegmentType.TEXT:
                    trimmed.append(seg)
                    continue
                text = str(seg.data.get("text", ""))
                if budget <= 0:
                    continue
                trimmed.append(MessageSegment.text(text[:budget]))
                budget -= min(len(text), budget)
            segments = trimmed
            ctx.extras["truncated"] = True
        ctx.extras["clean_segments"] = segments
        return StageResult()


class RecordStage(Stage):
    """Persist the inbound message. Implemented in Wave 3 against the DB layer.

    Wave 1 keeps a no-op recorder so the pipeline shape is final and tests can
    assert ordering without a database.
    """

    name = "record"

    def __init__(self, recorder=None) -> None:
        self._recorder = recorder

    async def run(self, ctx: PipelineContext) -> StageResult:
        if self._recorder is not None:
            await self._recorder(ctx)
        return StageResult()


class ReplyStage(Stage):
    """Deliver the model reply through the adapter."""

    name = "reply"

    def __init__(self, store=None, *, tts=None) -> None:
        self._store = store
        self._tts = tts
        """Optional speech synthesis. ``None`` means text only, which is the default:
        a group that did not ask for audio should not receive it."""

    async def run(self, ctx: PipelineContext) -> StageResult:
        if not ctx.model_reply:
            return StageResult(halt=True, reason="empty_reply")

        # Already delivered sentence by sentence during the model call. Sending the
        # whole text again would repeat the answer to the group, so this stage's job
        # is reduced to reporting the outcome the stream already knows.
        if ctx.extras.get("progressive_sent"):
            stats = ctx.extras.get("stream") or {}
            ctx.extras["send_ok"] = not stats.get("error")
            ctx.extras["send_error"] = stats.get("error", "")
            ctx.extras["reply_chunks"] = list(stats.get("sent") or [])
            return StageResult()

        segments = [MessageSegment.text(ctx.model_reply)]
        voiced = False
        if self._tts is not None and ctx.adapter.supports_segment(SegmentType.RECORD):
            # Synthesised only when the adapter can actually carry a voice segment.
            # Asking first avoids paying for audio the channel will drop.
            try:
                audio = await self._tts.synthesize(ctx.model_reply)
            except VoiceUnavailableError as exc:
                # Expected whenever the extra is not installed, or the reply is long.
                # Logged at info: an operator who enabled voice needs to see *why* a
                # reply went out as text, and silence would look like a broken setting.
                logger.info("voice reply skipped: %s", exc)
                ctx.extras["voice_reply"] = f"text:{exc}"
            except Exception as exc:  # pragma: no cover - defensive
                logger.warning("voice synthesis failed: %s", type(exc).__name__)
                ctx.extras["voice_reply"] = f"text:{type(exc).__name__}"
            else:
                segments = [MessageSegment.record(b64=audio)]
                voiced = True
                ctx.extras["voice_reply"] = "voice"

        out = ctx.outbound or _build_outgoing(ctx, segments)
        out.segments = segments

        receipt = await ctx.adapter.send(out)
        if voiced and not receipt.ok:
            # A voice segment that failed means the group got nothing at all, so the
            # text is sent as a second attempt rather than reported as a failed reply.
            logger.warning("voice send failed, falling back to text: %s", receipt.error)
            ctx.extras["voice_reply"] = "text:send_failed"
            out.segments = [MessageSegment.text(ctx.model_reply)]
            receipt = await ctx.adapter.send(out)
        ctx.extras["send_ok"] = receipt.ok
        ctx.extras["send_error"] = receipt.error
        # Same key as the progressive path, so the trace reader does not have to
        # branch on "was this streamed?" to find where the chunks went.
        ctx.extras["reply_chunks"] = []
        if not receipt.ok:
            logger.warning(
                "reply send failed adapter=%s target=%s err=%s",
                ctx.adapter.meta.name,
                out.target_id,
                receipt.error,
            )
        return StageResult()


def _build_outgoing(
    ctx: PipelineContext, segments: list[MessageSegment], *, reply: bool = True
):
    """Build the outgoing message.

    ``reply`` exists for progressive delivery: only the first sentence quotes the
    triggering message. Quoting every one of them turns a three-sentence answer into
    three quote blocks, which reads as three separate replies from the bot.
    """
    from soapbot.core.message import OutgoingMessage

    event = ctx.event
    return OutgoingMessage(
        scene=event.scene,
        segments=segments,
        group_id=event.group_id,
        user_id=event.sender.user_id,
        reply_to=(
            event.message_id if reply and ctx.adapter.supports(Capability.REPLY) else ""
        ),
    )
