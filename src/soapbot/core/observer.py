"""Passive mode: read every message, answer only the ones that are addressed to it.

The operator's requirement, in their words: the bot stays passive in speech but may
read messages, use the knowledge base and the group's own chatter to judge, and the
persona card only shapes the words (or the voice) it produces.

The pipeline as built could not express that. ``WakeStage`` halts *before* anything
is persisted, so an un-addressed group message was never archived, never embedded,
and never available to recall — the bot did not "stay quiet", it never saw the
message at all. The only way to give it context was to make it answer, which is the
opposite of passive.

So the read path is split from the answer path:

* every admitted message is archived (``PersistStage``), so recall has something to
  recall and the knowledge base has something to learn from;
* the model is only called when the message was addressed to the bot
  (``WakeStage`` still decides that, and still runs before anything expensive).

``PassiveObserver`` is the piece that does the reading. It is a bus subscriber rather
than a pipeline stage because a stage would have to run before the wake gate and
would then also run for messages that were *not* admitted — the blacklist and the
private-chat default would stop meaning anything.
"""

from __future__ import annotations

import asyncio
import logging
from typing import Any

from soapbot.core.message import EventType, MessageScene, SegmentType
from soapbot.core.pipeline import PipelineContext

logger = logging.getLogger(__name__)

#: A group message shorter than this is a reaction ("草", "1", a sticker's caption),
#: not something worth spending an embedding on. Tuned by what actually shows up in
#: group chats; the cost of being wrong is a missed memory, not a wrong reply.
_MIN_CHARS = 4

#: How many archives may be in flight before new ones are dropped.
#:
#: Passive mode reads *everything*, so on a busy group it would otherwise queue an
#: unbounded number of SQLite writes behind a bot that has to answer in the same
#: process. Dropping the read is the right failure: a missed memory costs context, a
#: growing backlog costs every reply's latency and eventually the write lock itself.
_MAX_INFLIGHT = 8

#: Attempts per archive before giving up. A locked database is transient by definition
#: — the other writer commits in milliseconds — so one retry covers the realistic case
#: without turning a persistent fault into an infinite loop.
_ATTEMPTS = 2


class PassiveObserver:
    """Archive and embed messages the bot was not asked to answer.

    Deliberately narrow: it writes to the same archive the answering path writes to,
    and it does nothing else. No model call, no reply, no persona — the persona card
    is applied by ``PersonaStage`` on the answer path only, which is what keeps "the
    card only affects the words" true by construction rather than by convention.

    The write is *detached* from the message path. It used to be awaited inline, which
    put a second SQLite writer on the same critical section as the answering write and
    produced ``database is locked`` on a real group — the read was slowing down and
    breaking the very replies it was supposed to improve. Now the observer schedules
    the archive and returns immediately; the bus publish is not held open by it.
    """

    def __init__(
        self,
        memory: Any,
        *,
        min_chars: int = _MIN_CHARS,
        max_inflight: int = _MAX_INFLIGHT,
    ) -> None:
        self.memory = memory
        self.min_chars = min_chars
        self.max_inflight = max_inflight
        self.seen = 0
        """Messages read without answering. Exposed so the panel can show that passive
        mode is doing something — a silent feature reads as a broken one."""
        self.dropped = 0
        """Messages skipped because too many archives were already in flight."""
        self._inflight: set[asyncio.Task[None]] = set()

    async def __call__(self, ctx: PipelineContext) -> None:
        event = ctx.event
        if event.event_type is not EventType.MESSAGE:
            return

        # The answering path already archived this one (PersistStage ran before the
        # model). Archiving again would double every message the bot replied to and
        # put the same line in the transcript twice.
        if ctx.extras.get("persisted_inbound"):
            return

        # Only the *halt reasons* that mean "admitted, but not addressed to me" are
        # read. A blacklisted user, a refused private chat, or an anonymous peer is not
        # context, it is traffic the operator asked us to drop — remembering it would
        # quietly undo the block.
        #
        # ``empty_input`` is here because of how the stages are ordered: a sticker or a
        # bare image carries no text, so ``WakeStage`` never sees a wake word and the
        # message halts as ``not_woken`` — but ``StripWakeWordStage`` runs after the
        # wake gate and the model stage reports the empty text as ``empty_input``. Both
        # names describe the same message, and a group's images are exactly the context
        # passive mode is for.
        if ctx.halt_reason not in {"not_woken", "empty_input"}:
            return

        if event.scene is not MessageScene.GROUP:
            return

        # ``event.text`` renders an image as the literal "[图片]", so it is never empty
        # for a picture and the length gate below would reject a bare image as "too
        # short". Measure the words the sender actually typed instead.
        words = "".join(
            str(seg.data.get("text", ""))
            for seg in event.segments
            if seg.type is SegmentType.TEXT
        ).strip()
        images = event.images
        if len(words) < self.min_chars and not images:
            return

        if len(self._inflight) >= self.max_inflight:
            # Backpressure, not a queue. See ``_MAX_INFLIGHT``.
            self.dropped += 1
            return

        payload = {
            "session_key": event.session_key,
            "role": "user",
            "content": event.text.strip() or f"[{len(images)} 张图片]",
            "adapter": event.adapter,
            "scene": str(event.scene),
            "group_id": event.group_id,
            "user_id": event.sender.user_id,
            "user_name": event.sender.display_name,
            "message_id": event.message_id,
            "trace_id": event.trace_id,
        }
        self.seen += 1
        ctx.extras["passive_read"] = True

        task = asyncio.create_task(self._archive(payload))
        self._inflight.add(task)
        # The set is the only strong reference; without this the task is garbage
        # collected mid-await and the archive silently never happens.
        task.add_done_callback(self._inflight.discard)

    async def _archive(self, payload: dict[str, Any]) -> None:
        """Write one row, retrying a locked database once.

        Runs as its own task, so an exception here is not swallowed by the caller's
        frame — it is caught here and logged, because a background task that raises
        only prints "Task exception was never retrieved" at shutdown.
        """
        for attempt in range(1, _ATTEMPTS + 1):
            try:
                await self.memory.archive_message(**payload)
                return
            except Exception as exc:  # pragma: no cover - a read must never break chat
                if attempt == _ATTEMPTS:
                    logger.warning(
                        "passive archive failed trace=%s after %d attempts: %s",
                        payload.get("trace_id"),
                        attempt,
                        exc,
                    )
                    return
                await asyncio.sleep(0.05 * attempt)

    async def drain(self, timeout: float = 5.0) -> None:
        """Wait for in-flight archives. For shutdown and for tests that assert on rows."""
        if not self._inflight:
            return
        await asyncio.wait(set(self._inflight), timeout=timeout)


def install_passive_observer(bus: Any, memory: Any) -> PassiveObserver | None:
    """Attach the observer to ``bus``. Returns ``None`` when there is no store.

    Takes the bus rather than the runtime because ``build_runtime`` subscribes before
    the runtime object exists — the trace collector is wired the same way, and for the
    same reason: an observer attached after the first message is an observer that
    missed it.
    """
    if memory is None:
        return None
    observer = PassiveObserver(memory)
    bus.subscribe("message.processed", observer)
    return observer


__all__ = ["PassiveObserver", "install_passive_observer"]
