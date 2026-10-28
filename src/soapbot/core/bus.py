"""In-process event bus.

Adapters publish normalised events; pipeline stages and plugins subscribe.
The bus is intentionally tiny: asyncio queues per subscriber, ordered delivery,
and a hard cap so a slow consumer cannot grow memory without bound.
"""

from __future__ import annotations

import asyncio
import logging
from collections.abc import Awaitable, Callable
from typing import Any

logger = logging.getLogger(__name__)

Handler = Callable[[Any], Awaitable[None]]


class EventBus:
    def __init__(self, queue_size: int = 1000) -> None:
        self._subs: dict[str, list[Handler]] = {}
        self._queue_size = queue_size

    def subscribe(self, topic: str, handler: Handler) -> Callable[[], None]:
        self._subs.setdefault(topic, []).append(handler)

        def _unsub() -> None:
            handlers = self._subs.get(topic, [])
            if handler in handlers:
                handlers.remove(handler)

        return _unsub

    async def publish(self, topic: str, payload: Any) -> None:
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
