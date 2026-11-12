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
from soapbot.core.text import INVISIBLE
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
            # A protocol message id is unique only inside one adapter+account pair: two
            # bots in the same group are handed the same id by the same server, and a
            # second adapter can reuse the numbering. Keying on the id alone dropped a
            # genuine message whenever the other bot's copy arrived first.
            key = f"{ctx.event.adapter}:{ctx.event.self_id}:{mid}"
            if key in self._seen:
                return StageResult(halt=True, reason="duplicate")
            self._seen[key] = time.time()
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
    """Groups the bot replies in. Empty means every group."""

    memory_collect_groups: set[str] = field(default_factory=set)
    """Groups whose messages are archived. Empty means every group.

    Independent of ``group_allowlist`` on purpose: "learn here" and "speak here" are
    different decisions, and an operator may want the bot to sit quietly in a busy
    group and still build up its history.
    """

    private_allowlist: set[str] = field(default_factory=set)
    group_blacklist: set[str] = field(default_factory=set)
    user_blacklist: set[str] = field(default_factory=set)
    allow_all_private: bool = False
    """Explicit opt-in for 'anyone may DM the bot'. Off by default."""

    def replies_in(self, gid: str) -> bool:
        return not self.group_allowlist or normalize_id(gid) in {
            normalize_id(g) for g in self.group_allowlist
        }

    def collects_from(self, scene: MessageScene, gid: str) -> bool:
        """Whether messages here may be written to memory.

        Empty means every group, exactly like ``replies_in``. The two lists are
        deliberately symmetric so that each one can be read on its own: "empty = all"
        everywhere, and narrowing one never changes the other behind the operator's
        back. An earlier version made an empty collect list inherit the reply list,
        which meant narrowing replies silently stopped archiving — a side effect the
        operator never asked for and could not see in the panel.
        """
        if scene is MessageScene.PRIVATE:
            # A DM is allow-listed at the user level before this is consulted, and the
            # group lists say nothing about it.
            return True
        return not self.memory_collect_groups or normalize_id(gid) in {
            normalize_id(g) for g in self.memory_collect_groups
        }

    def allows(self, scene: MessageScene, group_id: str, user_id: str) -> tuple[bool, str]:
        """Whether this message enters the pipeline at all.

        Groups pass when they are in *either* scope. A message from a collected-only
        group must still be admitted, otherwise its history is never archived — it is
        the reply that gets skipped later, not the admission.
        """
        uid = normalize_id(user_id)
        gid = normalize_id(group_id)
        banned = {normalize_id(u) for u in self.user_blacklist}

        if uid and uid in banned:
            return False, "user_blacklisted"

        if scene is MessageScene.GROUP:
            if gid in {normalize_id(g) for g in self.group_blacklist}:
                return False, "group_blacklisted"
            if not self.replies_in(gid) and not self.collects_from(scene, gid):
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
        if ctx.event.adapter == "web":
            # Admission for web conversations was already decided upstream, in the API
            # layer: the endpoint only exists when talk is enabled, and it grants the
            # session only after the account authenticated with a password and a
            # chat_memberships row named exactly this session. Re-deriving it here from
            # private_allowlist would reopen the question this branch closes — the QQ
            # lists hold QQ numbers and cannot express "account 3", so every web
            # conversation would need a second, manual list that drifts from the one
            # the panel manages. The QQ paths below stay deny-by-default; this branch
            # is reachable only for events the runtime accepted from the in-process
            # web adapter, which itself only exists when chat_talk_enabled is on.
            ctx.extras["memory_collect"] = True
            ctx.extras["replies_here"] = True
            return StageResult()
        ok, reason = self.policy.allows(
            ctx.event.scene, ctx.event.group_id, ctx.event.sender.user_id
        )
        if not ok:
            return StageResult(halt=True, reason=reason)
        # Carry the archive decision forward: ``PersistStage`` runs later in the
        # pipeline and must not re-derive it from configuration it does not hold.
        ctx.extras["memory_collect"] = self.policy.collects_from(
            ctx.event.scene, ctx.event.group_id
        )
        ctx.extras["replies_here"] = self.policy.replies_in(ctx.event.group_id)
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
    """Decide whether this message is addressed to the bot — without ending it.

    It used to halt on ``not_woken``, which also stopped ``persist`` further down: the
    archive step sat behind the wake check, so a group message nobody @-ed was never
    written to memory. That made "collect this group's history" impossible — the bot
    only remembered the messages it was asked about.

    Now the decision is recorded and the pipeline continues to the archive step, which
    consults the collect list; ``SkipReplyStage`` stops the turn afterwards. Everything
    before it is cheap and idempotent (strip, sanitize, injection screening), and the
    injection screen still runs *before* anything is stored.
    """

    name = "wake"

    def __init__(self, policy: WakePolicy | None = None) -> None:
        self.policy = policy or WakePolicy()

    async def run(self, ctx: PipelineContext) -> StageResult:
        woken, how = self.policy.is_woken(ctx)
        if not woken:
            ctx.extras["skip_reply"] = True
            return StageResult()
        ctx.extras["wake_reason"] = how
        return StageResult()


class SkipReplyStage(Stage):
    """Stop a turn that has been archived but must not be answered.

    Two reasons land here, and they are different questions:

    - ``not_woken``: nobody addressed the bot. Same reason the wake stage used to
      report, so the metrics and the "why didn't it answer" trail are unchanged.
    - ``group_not_replied``: somebody did address it, but this group is collected
      without being a reply group. Collecting and replying are separate settings, and
      without this check the reply list would only affect admission — a group the
      operator muted would still answer.

    Placed after ``PersistStage`` and before commands and plugin hooks: an un-mentioned
    group message must be archived, not handed to code that acts on it.
    """

    name = "skip_reply"

    async def run(self, ctx: PipelineContext) -> StageResult:
        if ctx.extras.get("skip_reply"):
            return StageResult(halt=True, reason="not_woken")
        # Collecting a group and replying in it are separate decisions, so a group that
        # is only collected must not get an answer even when somebody @-s the bot. The
        # archive above has already happened; this stops the turn before commands, the
        # model, and delivery.
        #
        # ``is False`` rather than a falsy check: an embedder or an older test that never
        # ran ``WhitelistStage`` has no key at all, and a missing key must mean "no
        # restriction" instead of silently muting every group.
        if ctx.event.scene is MessageScene.GROUP and ctx.extras.get("replies_here") is False:
            return StageResult(halt=True, reason="group_not_replied")
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

    # The one shared table; see :mod:`soapbot.core.text`.
    _INVISIBLE = INVISIBLE

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

    def __init__(self, store=None, *, tts=None, loader=None, picker=None) -> None:
        self._store = store
        self._tts = tts
        #: Autonomous voice picker (voice/picker.py). ``None`` means the operator's
        #: configured voice is used verbatim — the pre-existing behaviour.
        self._picker = picker
        #: Plugin loader when events are wired. ``None`` in tests that only exercise
        #: delivery, which is most of them.
        self._loader = loader
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

        # One writable event exists, and it is here: a plugin may replace the text
        # just before delivery. The replacement is re-scrubbed because it reaches the
        # group — routing it through the same filter the model's own text went
        # through is what stops a handler smuggling invisible characters or a
        # credential past output safety.
        if self._loader is not None:
            from soapbot.plugins.events import dispatch_event
            from soapbot.plugins.sandbox import scrub_plugin_output

            try:
                rewritten = await dispatch_event(
                    self._loader,
                    "reply_ready",
                    {
                        "text": ctx.model_reply,
                        "session_key": getattr(ctx.event, "session_key", ""),
                    },
                )
            except Exception as exc:
                logger.warning("reply_ready event failed: %s", type(exc).__name__)
                rewritten = None
            if isinstance(rewritten, str) and rewritten.strip():
                ctx.model_reply = scrub_plugin_output(rewritten)

        segments = [MessageSegment.text(ctx.model_reply)]
        voiced = False
        if self._tts is not None and ctx.adapter.supports_segment(SegmentType.RECORD):
            # Synthesised only when the adapter can actually carry a voice segment.
            # Asking first avoids paying for audio the channel will drop.
            voice_name, picked_via = None, "operator"
            persona_card = ctx.extras.get("persona")
            if self._picker is not None and persona_card is not None:
                from soapbot.ai.autonomy import parse_autonomy
                from soapbot.voice.picker import DEFAULT_VOICE

                autonomy = parse_autonomy(persona_card)
                if (
                    autonomy.voice_self_select
                    and self._tts.voice == DEFAULT_VOICE
                ):
                    # 手动指定优先：操作者改过 voice_tts_voice 时自主挑选不生效。
                    try:
                        voice_name, reason = await self._picker.pick(
                            persona_id=ctx.persona_id,
                            persona_prompt=ctx.persona_prompt,
                            session_key=ctx.event.session_key,
                            recent_context=ctx.model_reply[:400],
                        )
                        picked_via = "self"
                    except Exception as exc:
                        logger.info("voice pick failed, using default: %s", type(exc).__name__)
                        voice_name = None
                        picked_via = "default"
                    ctx.extras["voice_pick"] = f"{voice_name or 'default'}:{picked_via}:{reason if picked_via == 'self' else ''}"
            try:
                # ``voice`` 仅在自主挑选生效时传入：自定义 TTS 实现（含测试存根）的
                # synthesize 签名没有 voice 参数，无条件传会 TypeError 被吞成文本回退。
                if voice_name:
                    audio = await self._tts.synthesize(ctx.model_reply, voice=voice_name)
                else:
                    audio = await self._tts.synthesize(ctx.model_reply)
            except VoiceUnavailableError as exc:
                # Two different events share this exception. "Too long" happens on
                # every long answer and is normal, so it stays at debug; a missing
                # dependency or a failed synthesis is a configuration or vendor
                # problem the operator must actually see.
                if exc.code in {"too_long", "empty"}:
                    logger.debug("voice reply skipped: %s", exc)
                else:
                    logger.info("voice reply skipped: %s", exc)
                ctx.extras["voice_reply"] = f"text:{exc.code}"
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
        if ctx.extras.get("injection_blocked"):
            from soapbot.security.audit import get_audit_log

            get_audit_log().record(
                kind="injection",
                action="refusal_delivery",
                outcome="allow" if receipt.ok else "deny",
                principal=ctx.extras.get("principal"),
                detail="refusal sent" if receipt.ok else "refusal delivery failed",
                trace_id=ctx.event.trace_id,
            )
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
