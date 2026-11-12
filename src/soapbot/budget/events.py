"""The single place every approval notification channel subscribes to.

A spend request can arrive from a QQ command, the panel, or (later) an AI-generated
purchase proposal; a decision can be made from QQ or from the panel. If each of those
places grew its own "tell the operator" call, adding a channel would mean editing
every one of them and forgetting at least one. So all of them publish here, and the
panel / QQ / webhook / mobile adapters subscribe independently.

Hard rules, because a notification must never become the reason a decision failed:

* A failing, slow or hostile subscriber is skipped with a warning. Publishing is
  best-effort; the ledger transition has already committed by then.
* The event is a whitelist of scalar fields. No credential, no cookie, no raw
  request object crosses into a channel's payload — a webhook body is an outbound
  HTTP request, and "just pass the row" is how a session token ends up in it.
"""

from __future__ import annotations

import asyncio
import logging
from collections.abc import Awaitable, Callable
from dataclasses import dataclass
from typing import Any

logger = logging.getLogger(__name__)

#: A channel that never returns must not hold the approval response open.
NOTIFY_TIMEOUT = 5.0

#: Consumer code compares against these, rather than free-form strings.
REQUESTED = "requested"
APPROVED = "approved"
DENIED = "denied"
CANCELLED = "cancelled"
EXPIRED = "expired"


@dataclass(frozen=True, slots=True)
class ApprovalEvent:
    """One state change of a spend request, safe to hand to an outbound channel."""

    kind: str
    request_id: int
    session_key: str
    amount_minor: int
    currency: str
    purpose: str
    requester_id: str = ""
    requester_name: str = ""
    actor_id: str = ""
    actor_name: str = ""
    note: str = ""
    remaining_minor: int | None = None
    #: True when ``require_distinct_approver`` was explicitly disabled. Channels can
    #: show "confirmation only" instead of implying a second person approved it.
    degraded: bool = False
    created_at: float = 0.0

    def to_dict(self) -> dict[str, Any]:
        """Explicit whitelist: adding a field here is a reviewable decision."""
        return {
            "kind": self.kind,
            "request_id": self.request_id,
            "session_key": self.session_key,
            "amount_minor": self.amount_minor,
            "currency": self.currency,
            "purpose": self.purpose,
            "requester_id": self.requester_id,
            "requester_name": self.requester_name,
            "actor_id": self.actor_id,
            "actor_name": self.actor_name,
            "note": self.note,
            "remaining_minor": self.remaining_minor,
            "degraded": self.degraded,
            "created_at": self.created_at,
        }


Handler = Callable[[ApprovalEvent], Awaitable[None]]


class ApprovalBus:
    """In-process fan-out. Subscribers are registered by the host, never by plugins."""

    def __init__(self) -> None:
        self._handlers: list[Handler] = []

    def subscribe(self, handler: Handler) -> Callable[[], None]:
        self._handlers.append(handler)

        def _unsubscribe() -> None:
            if handler in self._handlers:
                self._handlers.remove(handler)

        return _unsubscribe

    async def publish(self, event: ApprovalEvent) -> int:
        """Notify every channel; return how many handlers completed successfully."""
        delivered = 0
        for handler in list(self._handlers):
            try:
                await asyncio.wait_for(handler(event), timeout=NOTIFY_TIMEOUT)
                delivered += 1
            except Exception as exc:
                # Only the exception *type*: a channel's error text may echo the
                # payload it was trying to send, which can include the purpose text.
                logger.warning(
                    "approval notification failed handler=%s err=%s",
                    getattr(handler, "__name__", "?"),
                    type(exc).__name__,
                )
        return delivered

    def clear(self) -> None:
        """Test/host-only: drop subscriptions without publishing."""
        self._handlers.clear()


#: One runtime owns one bus. Module-level so the QQ command path (built in
#: ``core/builder.py``) and the API path (``api/admin.py``) reach the same object
#: without either having a reference to the other.
APPROVAL_BUS = ApprovalBus()
