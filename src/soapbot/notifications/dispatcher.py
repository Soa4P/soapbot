"""One approval subscription fanning out to QQ, a signed webhook, and a phone feed.

Why a single subscriber instead of three: the ledger publishes once, and the
"did we already tell anyone" question has exactly one answer. Three independent
subscribers would each need their own dedup table and could disagree after a
restart.

Idempotency is keyed on ``(request_id, kind)`` — the state machine already makes
that pair unique, so a replayed callback, a retried POST, or a channel handler
being invoked twice cannot produce two messages. The key is a bounded in-memory
LRU, not a durable outbox: a process restart can re-notify once. That is a
deliberate, documented trade-off; a missed notification is worse than a duplicate.

Credential rules, because the webhook body is an outbound HTTP request:
* the signing secret never appears in a header, a log line, or an audit detail;
* the URL is reduced to its hostname in the audit record;
* request bodies carry only ``ApprovalEvent.to_dict()`` — an explicit whitelist.
"""

from __future__ import annotations

import asyncio
import hashlib
import hmac
import json
import logging
import secrets
import time
from collections import OrderedDict, deque
from collections.abc import Callable
from typing import Any
from urllib.parse import urlsplit

from soapbot.budget.events import APPROVAL_BUS, ApprovalEvent
from soapbot.budget.models import format_minor

logger = logging.getLogger(__name__)

MAX_SEEN = 1000
FEED_SIZE = 200
CHANNEL_TIMEOUT = 5.0


class ApprovalNotifier:
    """Subscribes to the approval bus; owns the phone feed's ring buffer."""

    def __init__(
        self,
        runtime: Any = None,
        *,
        settings: Any = None,
        audit: Any = None,
        client: Any = None,
        feed_size: int = FEED_SIZE,
    ) -> None:
        self._runtime = runtime
        self._settings = settings
        self._audit = audit
        self._client = client
        self._seen: OrderedDict[tuple[int, str], None] = OrderedDict()
        self._feed: deque[dict] = deque(maxlen=feed_size)
        self._seq = 0
        self._unsubscribe: Callable[[], None] | None = None

    def _cfg(self):
        if self._settings is not None:
            return self._settings
        from soapbot.config import settings

        return settings

    def start(self) -> ApprovalNotifier:
        self._unsubscribe = APPROVAL_BUS.subscribe(self.on_event)
        return self

    def stop(self) -> None:
        if self._unsubscribe is not None:
            self._unsubscribe()
            self._unsubscribe = None

    def feed(self, after: int = 0) -> dict:
        """Events newer than ``after``, for a phone polling with a cursor."""
        return {
            "events": [dict(item) for item in self._feed if item["id"] > after],
            "cursor": self._seq,
        }

    async def on_event(self, event: ApprovalEvent) -> None:
        key = (event.request_id, event.kind)
        if key in self._seen:
            return
        self._seen[key] = None
        if len(self._seen) > MAX_SEEN:
            self._seen.popitem(last=False)

        self._seq += 1
        payload = {"id": self._seq, **event.to_dict()}
        self._feed.append(payload)

        # Channels are independent: one broken destination must not cost the others
        # their notification. Each handles and logs its own failure.
        await asyncio.gather(
            self._qq(event), self._webhook(payload), return_exceptions=True
        )

    # ------------------------------------------------------------------ QQ

    async def _qq(self, event: ApprovalEvent) -> None:
        target = str(getattr(self._cfg(), "notify_session_key", "") or "")
        if not target or self._runtime is None:
            return
        text = (
            f"[审批] #{event.request_id} {event.kind} "
            f"{format_minor(event.amount_minor, event.currency)} "
            f"{event.purpose}\n"
            "请在面板或群里处理；本机器人不执行任何支付。"
        )[:500]
        try:
            await asyncio.wait_for(
                self._runtime._send_via_adapter(target, text), timeout=CHANNEL_TIMEOUT
            )
        except Exception as exc:
            logger.warning("approval QQ notification failed err=%s", type(exc).__name__)

    # ------------------------------------------------------------------ webhook

    def _signature(self, body: bytes, timestamp: str, nonce: str) -> str:
        secret = getattr(self._cfg(), "notify_webhook_secret", "")
        raw = (
            secret.get_secret_value()
            if hasattr(secret, "get_secret_value")
            else str(secret or "")
        )
        signing = timestamp.encode() + b"." + nonce.encode() + b"." + body
        return hmac.new(raw.encode(), signing, hashlib.sha256).hexdigest()

    async def _webhook(self, payload: dict) -> None:
        url = str(getattr(self._cfg(), "notify_webhook_url", "") or "")
        if not url:
            return
        body = json.dumps(payload, ensure_ascii=False, separators=(",", ":")).encode(
            "utf-8"
        )
        timestamp = str(int(time.time()))
        nonce = secrets.token_hex(8)
        headers = {
            "Content-Type": "application/json",
            "X-Soapbot-Timestamp": timestamp,
            "X-Soapbot-Nonce": nonce,
            "X-Soapbot-Signature": self._signature(body, timestamp, nonce),
        }
        try:
            from soapbot.net.client import outbound_client

            async with outbound_client(client=self._client) as http:
                response = await asyncio.wait_for(
                    http.post(url, content=body, headers=headers),
                    timeout=CHANNEL_TIMEOUT,
                )
            status = int(getattr(response, "status_code", 0))
            if status >= 400:
                logger.warning("approval webhook failed status=%s", status)
            if self._audit is not None:
                self._audit.record(
                    kind="approval",
                    action="webhook",
                    outcome="allow",
                    detail=f"host={urlsplit(url).hostname or '-'} status={status}",
                )
        except Exception as exc:
            # Only the type: an httpx error string can echo the URL, and the URL may
            # carry a token in its query string.
            logger.warning("approval webhook failed err=%s", type(exc).__name__)
