"""Turn a public page into a spend request — or refuse it before it exists.

The point of the pre-check is that "ask a human" is not a substitute for a limit.
If the page says ¥9,999 and the per-request cap is ¥100, writing a pending request
and then asking an owner to reject it would still reserve the amount, still occupy
the period, and still put a scary number in every notification channel. A proposal
that cannot be approved is not a proposal.

The price comes from a deterministic extraction on the fetched page (a meta tag or
a ¥-prefixed number in visible text), never from a model's free-form output: an
amount the model invented is exactly the kind of untrusted value that must not
become an authorisation input. An operator can still override it explicitly.
"""

from __future__ import annotations

import time
from dataclasses import dataclass

from soapbot.browse.reader import PageSnapshot
from soapbot.budget.events import APPROVAL_BUS, REQUESTED, ApprovalEvent


@dataclass(frozen=True, slots=True)
class ProposalResult:
    """Why a proposal was or was not created — safe to show to the operator."""

    created: bool
    reason: str
    request_id: int | None = None
    price_minor: int | None = None
    available_minor: int = 0
    per_request_cap_minor: int = 0

    def to_dict(self) -> dict:
        return {
            "created": self.created,
            "reason": self.reason,
            "request_id": self.request_id,
            "price_minor": self.price_minor,
            "available_minor": self.available_minor,
            "per_request_cap_minor": self.per_request_cap_minor,
        }


async def propose_purchase(
    store,
    page: PageSnapshot,
    *,
    session_key: str,
    requester_id: str,
    requester_name: str = "",
    trace_id: str = "",
    amount_override_minor: int | None = None,
) -> ProposalResult:
    """Pre-check the caps, then create one pending request and announce it."""
    price = amount_override_minor if amount_override_minor is not None else page.price_minor
    snapshot = await store.snapshot(session_key=session_key)
    context = {
        "price_minor": price,
        "available_minor": snapshot.available_minor,
        "per_request_cap_minor": store.policy.per_request_cap_minor,
    }
    if price is None:
        return ProposalResult(False, "no_price_on_page", **context)
    if price <= 0:
        return ProposalResult(False, "invalid_price", **context)
    if price > store.policy.per_request_cap_minor:
        return ProposalResult(False, "over_per_request_cap", **context)
    if price > snapshot.available_minor:
        return ProposalResult(False, "over_period_cap", **context)

    purpose = f"{page.title[:80]} | {page.url}"[:200]
    req, created = await store.create(
        session_key=session_key,
        requester_id=requester_id,
        requester_name=requester_name,
        amount_minor=price,
        purpose=purpose,
        trace_id=trace_id,
    )
    if created:
        await APPROVAL_BUS.publish(
            ApprovalEvent(
                kind=REQUESTED,
                request_id=req.id,
                session_key=session_key,
                amount_minor=price,
                currency=req.currency,
                purpose=purpose,
                requester_id=requester_id,
                requester_name=requester_name,
                remaining_minor=snapshot.available_minor - price,
                degraded=not store.policy.require_distinct_approver,
                created_at=time.time(),
            )
        )
    return ProposalResult(
        created=created,
        reason="created" if created else "deduplicated",
        request_id=req.id,
        **context,
    )
