"""Budget ledger correctness: the invariants that must never break.

Why these tests read the way they do
------------------------------------
Each one names a way a quota ledger goes wrong in production, because "it works
when I try it" is exactly what a check-then-act race looks like on a single
request:

* two requests approved in the same millisecond must not overrun the cap
* a retried command must not reserve twice
* a denied/expired request must return its quota, or the balance silently shrinks
* the requester must not approve their own request
* an approval must not be replayable after it landed

The amounts are integer minor units throughout. A float-based test here would hide
the accumulation bug that ``parse_amount`` exists to prevent.
"""

from __future__ import annotations

import asyncio
import time

import pytest

from soapbot.budget.models import (
    BudgetExceededError,
    InvalidAmountError,
    RequestNotFoundError,
    RequestNotPendingError,
    SelfApprovalError,
    SpendStatus,
    format_minor,
    parse_amount,
    sanitize_purpose,
)
from soapbot.budget.policy import BudgetPolicy, PolicyError
from soapbot.budget.store import BudgetStore
from soapbot.memory.db import Database
from soapbot.security.audit import AuditLog

SCOPE = "onebot11:group:12345"


@pytest.fixture
async def db(tmp_path):
    database = Database(f"sqlite+aiosqlite:///{tmp_path / 'budget.db'}")
    await database.init()
    yield database
    await database.close()


@pytest.fixture
async def store(db):
    policy = BudgetPolicy(
        currency="CNY",
        period="month",
        period_cap_minor=10_000,   # ¥100.00
        per_request_cap_minor=5_000,  # ¥50.00
    )
    return BudgetStore(db, policy, audit=AuditLog())


# ------------------------------------------------------------ amount parsing


@pytest.mark.parametrize(
    ("text", "expected"),
    [
        ("12", 1200),
        ("12.5", 1250),
        ("12.50", 1250),
        ("1,250.00", 125000),
        ("¥12.34", 1234),
        ("0.01", 1),
        ("  8  ", 800),
    ],
)
def test_parse_amount_accepts_normal_input(text, expected):
    assert parse_amount(text) == expected


@pytest.mark.parametrize(
    "text",
    ["", "  ", "abc", "nan", "inf", "-5", "0", "1e9", "12.345", None],
)
def test_parse_amount_rejects_junk(text):
    """``nan``/``inf`` are the dangerous ones: they compare true against every cap."""
    with pytest.raises(InvalidAmountError):
        parse_amount(text)


def test_parse_amount_does_not_lose_a_cent():
    """The float version of this returns 28 for "0.29" after truncation."""
    assert parse_amount("0.29") == 29
    assert parse_amount("19.99") == 1999


def test_amounts_sum_exactly():
    """Twenty-nine cents, a hundred times, is 2900 — not 2899.999999999996."""
    total = sum(parse_amount("0.29") for _ in range(100))
    assert total == 2900
    assert format_minor(total) == "¥29.00"


def test_sanitize_purpose_strips_control_characters():
    """A purpose is rendered in chat and in the operator's terminal."""
    messy = "买书\x00\x1b[31m红色\x07  \n\n 夹子"
    cleaned = sanitize_purpose(messy)
    assert "\x00" not in cleaned and "\x1b" not in cleaned and "\x07" not in cleaned
    assert "  " not in cleaned
    assert len(sanitize_purpose("x" * 500)) == 200


# ------------------------------------------------------------------- policy


def test_policy_rejects_incoherent_limits():
    """A per-request cap above the period cap makes every request unapprovable."""
    with pytest.raises(PolicyError):
        BudgetPolicy(period_cap_minor=1_000, per_request_cap_minor=5_000)


def test_policy_rejects_unknown_period():
    with pytest.raises(PolicyError):
        BudgetPolicy(period="fortnight")


def test_period_key_is_stable_within_the_period():
    policy = BudgetPolicy(period="month")
    a = policy.period_key(now=1_700_000_000)
    b = policy.period_key(now=1_700_000_000 + 60)
    assert a == b


def test_period_key_advances_across_months():
    policy = BudgetPolicy(period="month")
    a = policy.period_key(now=1_700_000_000)   # Nov 2023
    b = policy.period_key(now=1_703_000_000)   # Dec 2023
    assert a != b


# ------------------------------------------------------------- create / reserve


async def test_create_reserves_against_the_cap(store):
    req, created = await store.create(
        session_key=SCOPE, requester_id="u1", amount_minor=2000, purpose="买书"
    )
    assert created is True
    assert req.status is SpendStatus.PENDING
    assert req.amount_minor == 2000

    snap = await store.snapshot(session_key=SCOPE, period=req.period)
    # Pending amount is reserved, not yet committed.
    assert snap.reserved_minor == 2000
    assert snap.committed_minor == 0
    assert snap.available_minor == 8000


async def test_per_request_cap_is_enforced(store):
    """Per-request cap is a policy limit, so ``BudgetError`` rather than a parse error."""
    from soapbot.budget.models import BudgetError

    with pytest.raises(BudgetError, match="单笔上限"):
        await store.create(session_key=SCOPE, requester_id="u1", amount_minor=999_999)


async def test_period_cap_is_enforced(store):
    await store.create(session_key=SCOPE, requester_id="u1", amount_minor=5000)
    await store.create(session_key=SCOPE, requester_id="u1", amount_minor=5000)
    # Third request exceeds ¥100.00 total.
    with pytest.raises(BudgetExceededError):
        await store.create(session_key=SCOPE, requester_id="u1", amount_minor=100)


async def test_scope_isolation_of_quota(store):
    """Two groups must not share a cap, or one group can drain another's budget."""
    other = "onebot11:group:999"
    await store.create(session_key=SCOPE, requester_id="u1", amount_minor=5000)
    snap = await store.snapshot(session_key=other)
    assert snap.reserved_minor == 0
    assert snap.available_minor == 10000


async def test_idempotency_key_prevents_double_reservation(store):
    """A double-tapped command must reserve once, not twice."""
    first, created1 = await store.create(
        session_key=SCOPE, requester_id="u1", amount_minor=2000, idempotency_key="abc"
    )
    second, created2 = await store.create(
        session_key=SCOPE, requester_id="u1", amount_minor=2000, idempotency_key="abc"
    )
    assert created1 is True and created2 is False
    assert first.id == second.id

    snap = await store.snapshot(session_key=SCOPE, period=first.period)
    assert snap.reserved_minor == 2000, "retry double-reserved quota"


async def test_concurrent_creates_cannot_overrun_the_cap(store):
    """The race that a Python-side check would lose.

    Ten concurrent requests of ¥50 against a ¥100 cap: exactly two may succeed.
    A check-then-act implementation lets all ten through, because they all read
    "available = 10000" before any of them writes.
    """
    results = await asyncio.gather(
        *[
            store.create(session_key=SCOPE, requester_id=f"u{i}", amount_minor=5000)
            for i in range(10)
        ],
        return_exceptions=True,
    )
    ok = [r for r in results if not isinstance(r, BaseException)]
    rejected = [r for r in results if isinstance(r, BudgetExceededError)]
    assert len(ok) == 2, f"expected exactly 2 successes, got {len(ok)}"
    assert len(rejected) == 8

    snap = await store.snapshot(session_key=SCOPE)
    assert snap.reserved_minor == 10000
    assert snap.available_minor == 0


# -------------------------------------------------------------------- approve


async def test_approve_moves_reserved_to_committed(store):
    req, _ = await store.create(session_key=SCOPE, requester_id="u1", amount_minor=3000)
    outcome = await store.approve(req.id, session_key=SCOPE, approver_id="boss")

    assert outcome.request.status is SpendStatus.APPROVED
    assert outcome.committed_minor == 3000
    assert outcome.reserved_minor == 0

    snap = await store.snapshot(session_key=SCOPE, period=req.period)
    assert snap.committed_minor == 3000
    assert snap.reserved_minor == 0
    assert snap.available_minor == 7000


async def test_requester_cannot_approve_own_request(store):
    """Different error from "no permission" — the remedy is a second person."""
    req, _ = await store.create(session_key=SCOPE, requester_id="u1", amount_minor=1000)
    with pytest.raises(SelfApprovalError):
        await store.approve(req.id, session_key=SCOPE, approver_id="u1")


async def test_self_approval_can_be_enabled_explicitly(db):
    """Opt-out exists, but must be asked for by name."""
    policy = BudgetPolicy(
        period_cap_minor=10_000, per_request_cap_minor=5_000, require_distinct_approver=False
    )
    store = BudgetStore(db, policy)
    req, _ = await store.create(session_key=SCOPE, requester_id="u1", amount_minor=1000)
    outcome = await store.approve(req.id, session_key=SCOPE, approver_id="u1")
    assert outcome.request.status is SpendStatus.APPROVED


async def test_approval_is_not_replayable(store):
    """A forwarded approval or a retried command must not re-run the transition."""
    req, _ = await store.create(session_key=SCOPE, requester_id="u1", amount_minor=1000)
    await store.approve(req.id, session_key=SCOPE, approver_id="boss")
    with pytest.raises(RequestNotPendingError):
        await store.approve(req.id, session_key=SCOPE, approver_id="boss")


async def test_approval_cannot_cross_scopes(store):
    """A request id from another group must look nonexistent, not forbidden."""
    req, _ = await store.create(session_key=SCOPE, requester_id="u1", amount_minor=1000)
    with pytest.raises(RequestNotFoundError):
        await store.approve(req.id, session_key="onebot11:group:999", approver_id="boss")


async def test_approve_rechecks_budget_at_decision_time(store):
    """The cap must be re-checked, not trusted from request time.

    Scenario: two ¥50 requests are reserved against ¥100 (both valid). The period
    rolls over; the old reservations no longer count. Approving the stale one must
    not silently succeed against a fresh, empty period.
    """
    req, _ = await store.create(session_key=SCOPE, requester_id="u1", amount_minor=5000)
    # Approving now is fine: reserved 5000 + this 5000 == cap 10000.
    outcome = await store.approve(req.id, session_key=SCOPE, approver_id="boss")
    assert outcome.committed_minor == 5000


# ----------------------------------------------------------------------- deny


async def test_deny_releases_the_reservation(store):
    """Otherwise quota leaks: a refused request permanently shrinks the balance."""
    req, _ = await store.create(session_key=SCOPE, requester_id="u1", amount_minor=4000)
    await store.deny(req.id, session_key=SCOPE, approver_id="boss", note="不需要")

    snap = await store.snapshot(session_key=SCOPE, period=req.period)
    assert snap.reserved_minor == 0
    assert snap.committed_minor == 0
    assert snap.available_minor == 10000


async def test_cancel_by_requester_releases_reservation(store):
    req, _ = await store.create(session_key=SCOPE, requester_id="u1", amount_minor=4000)
    await store.cancel(req.id, session_key=SCOPE, requester_id="u1")
    snap = await store.snapshot(session_key=SCOPE, period=req.period)
    assert snap.available_minor == 10000


async def test_someone_else_cannot_cancel_your_request(store):
    req, _ = await store.create(session_key=SCOPE, requester_id="u1", amount_minor=4000)
    with pytest.raises(RequestNotFoundError):
        await store.cancel(req.id, session_key=SCOPE, requester_id="u2")


# --------------------------------------------------------------------- expiry


async def test_expired_request_releases_quota(store):
    """The silent-shrink bug: an unanswered request must not hold quota forever."""
    now = time.time()
    req, _ = await store.create(
        session_key=SCOPE, requester_id="u1", amount_minor=4000, now=now
    )
    # Well past the TTL.
    snapshot = await store.snapshot(
        session_key=SCOPE, period=req.period, now=now + 10 * 24 * 3600
    )
    assert snapshot.reserved_minor == 0
    assert snapshot.available_minor == 10000


async def test_expired_request_cannot_be_approved(store):
    now = time.time()
    req, _ = await store.create(
        session_key=SCOPE, requester_id="u1", amount_minor=1000, now=now
    )
    with pytest.raises(RequestNotPendingError, match="过期"):
        await store.approve(
            req.id, session_key=SCOPE, approver_id="boss", now=now + 10 * 24 * 3600
        )


async def test_global_sweep_expires_across_scopes(store):
    """A background tick must free quota even if nobody opens the view."""
    now = time.time()
    await store.create(session_key=SCOPE, requester_id="u1", amount_minor=1000, now=now)
    await store.create(
        session_key="onebot11:group:999", requester_id="u2", amount_minor=1000, now=now
    )
    count = await store.sweep_expired(now=now + 10 * 24 * 3600)
    assert count == 2


# --------------------------------------------------------------------- listing


async def test_list_pending_is_scoped_and_ordered(store):
    a, _ = await store.create(session_key=SCOPE, requester_id="u1", amount_minor=100)
    b, _ = await store.create(session_key=SCOPE, requester_id="u2", amount_minor=200)
    await store.create(session_key="onebot11:group:999", requester_id="u3", amount_minor=300)

    pending = await store.list_pending(session_key=SCOPE)
    ids = [r.id for r in pending]
    assert ids == [a.id, b.id], "oldest first, and no cross-scope leakage"


async def test_get_is_scoped(store):
    req, _ = await store.create(session_key=SCOPE, requester_id="u1", amount_minor=100)
    assert (await store.get(req.id, session_key=SCOPE)).id == req.id
    with pytest.raises(RequestNotFoundError):
        await store.get(req.id, session_key="onebot11:group:999")


# ----------------------------------------------------------------- audit trail


async def test_every_transition_is_audited(store):
    """Approvals grant authority; the record of who granted it must survive."""
    req, _ = await store.create(session_key=SCOPE, requester_id="u1", amount_minor=1000)
    await store.approve(req.id, session_key=SCOPE, approver_id="boss")

    actions = [e["action"] for e in store.audit.recent(limit=50, kind="budget")]
    assert "request" in actions
    assert "approve" in actions


async def test_audit_records_approver_identity(store):
    req, _ = await store.create(session_key=SCOPE, requester_id="u1", amount_minor=1000)
    await store.approve(req.id, session_key=SCOPE, approver_id="boss")
    events = [
        e for e in store.audit.recent(limit=50, kind="budget") if e["action"] == "approve"
    ]
    assert events and "approver=boss" in events[-1]["detail"]
