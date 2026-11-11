"""In-process event bus.

Adapters publish normalised events; pipeline stages subscribe. The bus is intentionally
tiny, and its semantics are worth stating exactly, because a previous version described
itself as "asyncio queues per subscriber, ordered delivery, and a hard cap" while
implementing none of that: ``__init__`` accepted a ``queue_size`` argument, stored it,
and never read it again. A limit that looks like a limit but is not one is worse than no
limit — it gets cited in reviews as if it held.

What actually happens on ``publish``
------------------------------------
* Fan-out is by topic, in subscription order.
* Every handler is awaited before ``publish`` returns. There is no background queue, so
  the caller's next line runs only after the slowest subscriber finished.
* One handler raising does not stop the others; the exception is logged and swallowed,
  so a broken subscriber cannot take the pipeline down with it.
* No message is dropped. Since delivery is awaited rather than queued, there is nothing
  to overflow and nothing to bound — the memory a queue cap would protect against does
  not exist here.

The cost of that simplicity is that a handler which never returns stalls its publisher.
That is deliberate for the one subscriber in use (``message.processed``, which fans out
to pipeline stages), and the boundaries that can hang have their own timeouts: plugin
handlers run under ``asyncio.wait_for`` in ``plugins/dispatch.py``, and provider calls
are bounded by the HTTP client. Pushing a timeout into ``publish`` would only move the
decision somewhere that cannot log which handler it abandoned.

If a future subscriber needs to be isolated from the publisher, give *that* subscriber a
queue and a worker task, and say so here — do not reintroduce a constructor argument.
"""

from __future__ import annotations

import asyncio
import logging
from collections.abc import Awaitable, Callable
from typing import Any

logger = logging.getLogger(__name__)

Handler = Callable[[Any], Awaitable[None]]


class EventBus:
    def __init__(self) -> None:
        self._subs: dict[str, list[Handler]] = {}

    def subscribe(self, topic: str, handler: Handler) -> Callable[[], None]:
        self._subs.setdefault(topic, []).append(handler)

        def _unsub() -> None:
            handlers = self._subs.get(topic, [])
            if handler in handlers:
                handlers.remove(handler)

        return _unsub

    async def publish(self, topic: str, payload: Any) -> None:
        """Deliver ``payload`` to every handler on ``topic`` and wait for all of them.

        Handlers run concurrently with each other (``gather``), not one after another —
        a subscriber that is slow does not delay its siblings. Ordering within a single
        handler is guaranteed by the caller awaiting this coroutine before publishing
        the next event; the bus itself keeps no history.
        """
        handlers = list(self._subs.get(topic, []))
        if not handlers:
            return
        results = await asyncio.gather(
            *(self._call(h, payload, topic) for h in handlers),
            return_exceptions=True,
        )
        for r in results:
            if isinstance(r, Exception):  # pragma: no cover - defensive
                logger.error("bus handler error topic=%s err=%s", topic, r)

    async def _call(self, handler: Handler, payload: Any, topic: str) -> None:
        try:
            await handler(payload)
        except Exception:
            logger.exception("bus handler failed topic=%s", topic)

    def subscriber_count(self, topic: str) -> int:
        return len(self._subs.get(topic, []))
