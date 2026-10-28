"""Send a reply sentence by sentence while the model is still producing it.

Why this exists
---------------
A blocking model call means the group waits in silence for the whole answer. Sending
sentences as they complete pays most of that latency back for long replies, which is
exactly the kind of reply a group bot produces.

Why the pacing is hand-written
------------------------------
``security.ratelimit`` is a *detector*: it counts attempts per key and answers "has
this caller been behaving badly". The control needed here is "no more than N messages
per second to one group", which is a pacing question with a deadline, not a window
count. Reusing the limiter would mean checking it and then sleeping anyway.

Failure policy
--------------
Once the first sentence is in the group, the rest of the answer cannot be unsent by
switching providers or by falling back to one big message: the reader already has a
fragment. A failure mid-stream therefore stops the sending and is recorded, and the
caller keeps whatever was delivered. Sending a second, complete answer on top would
be worse than the interruption.
"""

from __future__ import annotations

import asyncio
import logging
import time
from collections.abc import Callable
from typing import Any

from soapbot.core.message import OutgoingMessage
from soapbot.core.text import clean_text

logger = logging.getLogger(__name__)

#: Builder supplied by the caller: (text, is_first) -> message to send. The first
#: sentence carries the reply reference; the later ones must not, or the group shows
#: a quote chain instead of a conversation.
OutgoingBuilder = Callable[[str, bool], OutgoingMessage]


class ProgressiveSender:
    """Deliver reply sentences one message at a time, paced."""

    def __init__(
        self,
        adapter,
        build: OutgoingBuilder,
        *,
        min_interval: float = 0.35,
        max_total_chars: int = 4000,
        clock: Callable[[], float] = time.perf_counter,
    ) -> None:
        self._adapter = adapter
        self._build = build
        self._min_interval = min_interval
        self._max_total_chars = max_total_chars
        self._clock = clock

        self._started = clock()
        self._last_sent_at: float | None = None
        self._chars = 0
        self._first_send_ms: float | None = None

        self.sent: list[str] = []
        self.error = ""
        self.truncated = False

    @property
    def ok(self) -> bool:
        return not self.error

    @property
    def first_send_ms(self) -> float | None:
        return self._first_send_ms

    async def send(self, text: str) -> bool:
        """Send one sentence. Returns False once delivery has failed or was cut short."""
        if self.error:
            return False

        body = clean_text(text).strip()
        if not body:
            return True

        budget = self._max_total_chars - self._chars
        if budget <= 0:
            self.truncated = True
            return False
        if len(body) > budget:
            body = body[:budget]
            self.truncated = True

        await self._pace()

        out = self._build(body, not self.sent)
        receipt = await self._adapter.send(out)
        if not receipt.ok:
            self.error = receipt.error or "send failed"
            logger.warning(
                "progressive send failed adapter=%s after=%d err=%s",
                self._adapter.meta.name,
                len(self.sent),
                self.error,
            )
            return False

        self._chars += len(body)
        self.sent.append(body)
        if self._first_send_ms is None:
            self._first_send_ms = round((self._clock() - self._started) * 1000, 2)
        # The budget ran out: stop rather than emit a stub on the next call.
        return not self.truncated

    def stats(self) -> dict[str, Any]:
        return {
            "sent": list(self.sent),
            "count": len(self.sent),
            "chars": self._chars,
            "first_send_ms": self._first_send_ms,
            "truncated": self.truncated,
            "error": self.error,
        }

    async def _pace(self) -> None:
        if self._last_sent_at is None:
            self._last_sent_at = self._clock()
            return
        wait = self._min_interval - (self._clock() - self._last_sent_at)
        if wait > 0:
            await asyncio.sleep(wait)
        self._last_sent_at = self._clock()
