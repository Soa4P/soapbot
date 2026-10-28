"""Spend-request ledger: reservations, approvals, expiry, and the audit trail.

The property this module exists to guarantee
--------------------------------------------
**Concurrent requests cannot overrun the cap.** Checking "is there room?" and then
inserting is a check-then-act race: two requests arriving in the same millisecond
both read the same available balance, both pass, and the ledger is over budget by
one request. Nobody notices until the cap is exceeded, and by then the offending
request has already been approved by a human who trusted the number shown to them.

The fix is to make the check and the insert one atomic step. SQLite gives us that
for free by making the whole comparison an ``INSERT ... SELECT ... WHERE`` — the
statement reads and writes inside a single transaction, so a second concurrent
writer sees the first's row. Doing it in Python (``SELECT sum()`` then
``INSERT``) would leave exactly the window described above, and it is the sort of
bug that only reproduces under load.

Why reserved amounts are counted as used
----------------------------------------
The cap is compared against ``committed + reserved``, not ``committed`` alone.
Counting only approved spend would let ten pending requests each be told the full
remainder is free — the eleventh approval is the one that breaks the cap, and it
breaks it *after* a human approved it.

Expiry releases quota
---------------------
``sweep_expired`` moves stale pending rows to ``expired``. Without it, every
unanswered request permanently shrinks the available balance, and the symptom —
quota slowly vanishing with no visible cause — is not diagnosable from the UI.
The sweep runs inside the same transaction as the balance query, so an operator
never sees a balance that includes a request which has already expired.
"""

from __future__ import annotations

import logging
import time
from dataclasses import dataclass

from sqlalchemy import func, select, text, update
from sqlalchemy.exc import IntegrityError

from soapbot.budget.models import (
    COMMITTED_STATES,
    RESERVING_STATES,
    BudgetExceededError,
    BudgetSnapshot,
    RequestNotFoundError,
    RequestNotPendingError,
    SelfApprovalError,
    SpendRequest,
    SpendStatus,
    sanitize_purpose,
)
from soapbot.budget.policy import BudgetPolicy
from soapbot.memory.db import Database, SpendRequestRow
from soapbot.security.audit import AuditLog

logger = logging.getLogger(__name__)


@dataclass(slots=True)
class ApprovalOutcome:
    """Result of a decision, carrying enough context to render a reply."""

    request: SpendRequest
    previous: SpendStatus
    committed_minor: int
    reserved_minor: int
    cap_minor: int

    @property
    def available_minor(self) -> int:
        return max(0, self.cap_minor - self.committed_minor - self.reserved_minor)


def _row_to_request(row: SpendRequestRow) -> SpendRequest:
    return SpendRequest(
        id=row.id,
        amount_minor=row.amount_minor,
        currency=row.currency,
        purpose=row.purpose,
        session_key=row.session_key,
        requester_id=row.requester_id,
        requester_name=row.requester_name,
        status=SpendStatus(row.status),
        period=row.period,
        created_at=row.created_at,
        expires_at=row.expires_at,
        decided_at=row.decided_at,
        decided_by=row.decided_by,
        decision_note=row.decision_note,
        idempotency_key=row.idempotency_key or "",
        trace_id=row.trace_id,
    )


class BudgetStore:
    """Persistence and invariants for spend authorisations."""

    def __init__(
        self,
        db: Database,
        policy: BudgetPolicy | None = None,
        *,
        audit: AuditLog | None = None,
    ) -> None:
        self.db = db
        self.policy = policy or BudgetPolicy()
        self.audit = audit or AuditLog()

    # ------------------------------------------------------------------ reads
    async def _totals(self, session, *, session_key: str, period: str) -> tuple[int, int, int]:
        """Return ``(committed, reserved, pending_count)`` for one scope+period.

        Summed in SQL rather than Python: pulling every row to add them up is both
        slower and racy — a row inserted between the read and the sum would be
        missed, which is the same overrun hole described in the module docstring.
        """
        committed = await session.scalar(
            select(func.coalesce(func.sum(SpendRequestRow.amount_minor), 0)).where(
                SpendRequestRow.session_key == session_key,
                SpendRequestRow.period == period,
                SpendRequestRow.status.in_([str(s) for s in COMMITTED_STATES]),
            )
        )
        reserved = await session.scalar(
            select(func.coalesce(func.sum(SpendRequestRow.amount_minor), 0)).where(
                SpendRequestRow.session_key == session_key,
                SpendRequestRow.period == period,
                SpendRequestRow.status.in_([str(s) for s in RESERVING_STATES]),
            )
        )
        pending = await session.scalar(
            select(func.count()).select_from(SpendRequestRow).where(
                SpendRequestRow.session_key == session_key,
                SpendRequestRow.period == period,
                SpendRequestRow.status.in_([str(s) for s in RESERVING_STATES]),
            )
        )
        return int(committed or 0), int(reserved or 0), int(pending or 0)

    async def snapshot(
        self, *, session_key: str, period: str | None = None, now: float | None = None
    ) -> BudgetSnapshot:
        """Current usage, after sweeping expired requests."""
        period = period or self.policy.period_key(now=now)
        async with self.db.session_factory()() as session:
            await self._sweep_expired_in(session, session_key=session_key, period=period, now=now)
            committed, reserved, pending = await self._totals(
                session, session_key=session_key, period=period
            )
            await session.commit()
        return BudgetSnapshot(
            session_key=session_key,
            period=period,
            currency=self.policy.currency,
            cap_minor=self.policy.period_cap_minor,
            committed_minor=committed,
            reserved_minor=reserved,
            pending_count=pending,
        )

    async def get(self, request_id: int, *, session_key: str) -> SpendRequest:
        """Fetch one request **scoped to the caller**.

        ``session_key`` is a required argument, not a filter the caller may forget:
        omitting it would make this an existence oracle across groups.
        """
        async with self.db.session_factory()() as session:
            row = await session.get(SpendRequestRow, request_id)
            if row is None or row.session_key != session_key:
                raise RequestNotFoundError(f"没有编号为 {request_id} 的申请")
            return _row_to_request(row)

    async def list_pending(self, *, session_key: str, limit: int = 10) -> list[SpendRequest]:
        async with self.db.session_factory()() as session:
            rows = (
                await session.execute(
                    select(SpendRequestRow)
                    .where(
                        SpendRequestRow.session_key == session_key,
                        SpendRequestRow.status == str(SpendStatus.PENDING),
                    )
                    .order_by(SpendRequestRow.created_at.asc())
                    .limit(max(1, min(limit, 50)))
                )
            ).scalars()
            return [_row_to_request(r) for r in rows]

    async def list_requests(
        self, *, status: str = "", limit: int = 100, session_key: str = ""
    ) -> list[SpendRequest]:
        """Cross-scope listing for the operator's management view.

        Deliberately *not* scoped, which is why nothing in the chat path may call it:
        every chat-facing read goes through ``get`` or ``list_pending``, both of which
        require a ``session_key``. This method exists for the authenticated API, where
        the caller is the operator and "show me requests in every group" is the point.
        """
        limit = max(1, min(limit, 500))
        stmt = select(SpendRequestRow).order_by(SpendRequestRow.created_at.desc()).limit(limit)
        if status:
            stmt = stmt.where(SpendRequestRow.status == status)
        if session_key:
            stmt = stmt.where(SpendRequestRow.session_key == session_key)
        async with self.db.session_factory()() as session:
            rows = (await session.execute(stmt)).scalars()
            return [_row_to_request(r) for r in rows]

    async def _overrun_message(
        self, *, session_key: str, period: str, amount_minor: int
    ) -> str:
        """Explain a rejected insert with real numbers.

        The atomic INSERT only tells us *that* it failed. Recomputing the totals
        afterwards is safe here — we are producing an error message, not making a
        decision, so a stale read cannot cause an overrun.
        """
        async with self.db.session_factory()() as session:
            committed, reserved, _ = await self._totals(
                session, session_key=session_key, period=period
            )
        used = committed + reserved
        available = max(0, self.policy.period_cap_minor - used)
        return (
            f"本{_period_word(self.policy.period)}额度不足："
            f"上限 {self.policy.period_cap_minor / 100:.2f}，已用 {used / 100:.2f}，"
            f"可用 {available / 100:.2f}，本次需要 {amount_minor / 100:.2f}"
        )

    # ----------------------------------------------------------------- writes
    async def create(
        self,
        *,
        session_key: str,
        requester_id: str,
        amount_minor: int,
        purpose: str = "",
        requester_name: str = "",
        currency: str | None = None,
        idempotency_key: str = "",
        trace_id: str = "",
        now: float | None = None,
    ) -> tuple[SpendRequest, bool]:
        """Create a pending request, reserving its amount against the period cap.

        Returns ``(request, created)``. ``created`` is ``False`` when an
        idempotency key matched an existing row, so the caller can render the
        original request instead of a duplicate.

        The cap check and the insert are one statement. See the module docstring —
        splitting them reintroduces the overrun race under concurrent load.
        """
        ts = time.time() if now is None else now
        currency = (currency or self.policy.currency).upper()
        self.policy.check_currency(currency)
        self.policy.check_amount(amount_minor)
        purpose = sanitize_purpose(purpose)
        period = self.policy.period_key(now=ts)
        key = (idempotency_key or "").strip()[:64] or None

        async with self.db.session_factory()() as session:
            if key:
                existing = await session.scalar(
                    select(SpendRequestRow).where(
                        SpendRequestRow.session_key == session_key,
                        SpendRequestRow.idempotency_key == key,
                    )
                )
                if existing is not None:
                    # A retry, not a new decision. Returning the original keeps a
                    # double-tapped command from reserving twice.
                    return _row_to_request(existing), False

            await self._sweep_expired_in(session, session_key=session_key, period=period, now=ts)
            await session.commit()

            # The cap check and the insert are ONE statement, on purpose.
            #
            # The natural-looking version — SELECT the totals, compare in Python,
            # then INSERT — has a check-then-act window: two requests arriving in
            # the same millisecond both read the same available balance, both pass,
            # and the ledger ends up over cap by one request. It never reproduces in
            # a single-threaded test and always reproduces under load.
            #
            # Putting the comparison inside the INSERT makes SQLite do both inside
            # one write transaction, so a concurrent writer sees the row this one
            # just created. ``rowcount == 0`` means the WHERE clause rejected the
            # insert, i.e. the cap would have been exceeded.
            insert_stmt = text(
                """
                INSERT INTO spend_requests
                    (amount_minor, currency, purpose, session_key, requester_id,
                     requester_name, status, period, created_at, expires_at,
                     decided_at, decided_by, decision_note,
                     idempotency_key, trace_id)
                SELECT :amount_minor, :currency, :purpose, :session_key, :requester_id,
                       :requester_name, :status, :period, :created_at, :expires_at,
                       0.0, '', '',
                       :idempotency_key, :trace_id
                WHERE (
                    SELECT COALESCE(SUM(amount_minor), 0)
                    FROM spend_requests
                    WHERE session_key = :session_key
                      AND period = :period
                      AND status IN ('approved', 'pending')
                ) + :amount_minor <= :cap
                """
            )
            params = {
                "amount_minor": amount_minor,
                "currency": currency,
                "purpose": purpose,
                "session_key": session_key,
                "requester_id": requester_id,
                "requester_name": requester_name,
                "status": str(SpendStatus.PENDING),
                "period": period,
                "created_at": ts,
                "expires_at": self.policy.expires_at(now=ts),
                "idempotency_key": key,
                "trace_id": trace_id,
                "cap": self.policy.period_cap_minor,
            }
            overrun = False
            try:
                result = await session.execute(insert_stmt, params)
                if not result.rowcount:
                    # Do NOT raise from inside the transaction: building the error
                    # message needs to re-read the totals, and a second connection
                    # cannot read while this one holds the write lock — the reply
                    # would hang until ``busy_timeout`` and then report a bogus
                    # "database is locked" instead of "quota exceeded".
                    overrun = True
                else:
                    await session.commit()
            except IntegrityError:
                # Lost an idempotency race to a concurrent identical request. The
                # unique index did its job; return the winner rather than erroring,
                # because from the caller's point of view the request simply exists.
                await session.rollback()
                if not key:
                    raise
                existing = await session.scalar(
                    select(SpendRequestRow).where(
                        SpendRequestRow.session_key == session_key,
                        SpendRequestRow.idempotency_key == key,
                    )
                )
                if existing is None:
                    raise
                return _row_to_request(existing), False

            if overrun:
                # Release the write lock before re-reading, so the explanatory
                # message can actually be produced.
                await session.rollback()
                raise BudgetExceededError(
                    await self._overrun_message(
                        session_key=session_key, period=period, amount_minor=amount_minor
                    )
                )

            # The row was inserted by raw SQL, so there is no ORM instance to
            # refresh. Fetch it back by primary key (``lastrowid``), which also
            # proves the write landed rather than assuming it did.
            new_id = getattr(result, "lastrowid", None)
            row = await session.get(SpendRequestRow, new_id) if new_id else None
            if row is None:
                row = await session.scalar(
                    select(SpendRequestRow).where(
                        SpendRequestRow.session_key == session_key,
                        SpendRequestRow.period == period,
                        SpendRequestRow.created_at == ts,
                        SpendRequestRow.amount_minor == amount_minor,
                    )
                )
            if row is None:
                raise BudgetExceededError("申请写入失败，请重试")
            created = _row_to_request(row)

        self.audit.record(
            kind="budget",
            action="request",
            outcome="allow",
            detail=f"amount={amount_minor} period={period} {purpose[:60]}",
            plugin=None,
        )
        return created, True

    async def approve(
        self,
        request_id: int,
        *,
        session_key: str,
        approver_id: str,
        approver_name: str = "",
        note: str = "",
        now: float | None = None,
        allow_self: bool | None = None,
    ) -> ApprovalOutcome:
        """Approve a pending request.

        Guards, in order, because each failure means something different to the
        operator:

        1. **Not found in scope** — never distinguish "missing" from "someone
           else's", or the command becomes a probe.
        2. **Not pending** — the replay guard. An approval arriving twice (retry,
           forwarded message, double click) must not re-run the transition.
        3. **Self-approval** — a *different* error from "no permission", so the
           remedy ("find a second person") is not confused with a role problem.
        4. **Expired** — checks the clock rather than trusting the sweep, because
           the sweep may not have run since the TTL lapsed.
        5. **Budget** — re-checked at approval time, not just at request time. The
           period may have rolled over or another request may have been approved
           in between; trusting the earlier check is how a cap gets exceeded.
        """
        ts = time.time() if now is None else now
        allow_self = self.policy.require_distinct_approver if allow_self is None else allow_self

        async with self.db.session_factory()() as session:
            row = await session.get(SpendRequestRow, request_id)
            if row is None or row.session_key != session_key:
                raise RequestNotFoundError(f"没有编号为 {request_id} 的申请")

            previous = SpendStatus(row.status)
            if previous.is_terminal:
                raise RequestNotPendingError(
                    f"申请 #{request_id} 已经是「{_status_word(previous)}」，不能重复审批"
                )

            if allow_self and row.requester_id == approver_id:
                raise SelfApprovalError("不能审批自己发起的申请，需要另一个人确认")

            if row.expires_at and ts > row.expires_at:
                await self._expire_row(session, row, now=ts)
                await session.commit()
                raise RequestNotPendingError(
                    f"申请 #{request_id} 已于 {_fmt_ts(row.expires_at)} 过期"
                )

            committed, reserved, _ = await self._totals(
                session, session_key=session_key, period=row.period
            )
            # ``reserved`` includes this request, so compare without double-counting.
            other_reserved = max(0, reserved - row.amount_minor)
            if committed + other_reserved + row.amount_minor > self.policy.period_cap_minor:
                raise BudgetExceededError(
                    f"批准后本周期将超出额度上限 {self.policy.period_cap_minor / 100:.2f}"
                )

            row.status = str(SpendStatus.APPROVED)
            row.decided_at = ts
            row.decided_by = approver_id
            row.decision_note = sanitize_purpose(note, limit=200)
            await session.commit()
            await session.refresh(row)
            outcome = ApprovalOutcome(
                request=_row_to_request(row),
                previous=previous,
                committed_minor=committed + row.amount_minor,
                reserved_minor=other_reserved,
                cap_minor=self.policy.period_cap_minor,
            )

        self.audit.record(
            kind="budget",
            action="approve",
            outcome="allow",
            detail=(
                f"request={request_id} amount={outcome.request.amount_minor} "
                f"requester={outcome.request.requester_id} approver={approver_id}"
            ),
            plugin=None,
        )
        return outcome

    async def deny(
        self,
        request_id: int,
        *,
        session_key: str,
        approver_id: str,
        note: str = "",
        now: float | None = None,
        allow_self: bool | None = None,
    ) -> ApprovalOutcome:
        """Refuse a pending request, releasing its reservation.

        Denying is held to the same self-approval rule as approving: a requester
        could otherwise cancel a competing request by "denying" it, and the
        distinction between withdrawing your own request and refusing someone
        else's matters for the audit trail. Withdrawal uses ``cancel``.
        """
        ts = time.time() if now is None else now
        allow_self = self.policy.require_distinct_approver if allow_self is None else allow_self

        async with self.db.session_factory()() as session:
            row = await session.get(SpendRequestRow, request_id)
            if row is None or row.session_key != session_key:
                raise RequestNotFoundError(f"没有编号为 {request_id} 的申请")
            previous = SpendStatus(row.status)
            if previous.is_terminal:
                raise RequestNotPendingError(
                    f"申请 #{request_id} 已经是「{_status_word(previous)}」，不能重复审批"
                )
            if allow_self and row.requester_id == approver_id:
                raise SelfApprovalError("不能驳回自己发起的申请；如需撤回请用取消")

            row.status = str(SpendStatus.DENIED)
            row.decided_at = ts
            row.decided_by = approver_id
            row.decision_note = sanitize_purpose(note, limit=200)
            await session.commit()
            await session.refresh(row)
            committed, reserved, _ = await self._totals(
                session, session_key=session_key, period=row.period
            )
            outcome = ApprovalOutcome(
                request=_row_to_request(row),
                previous=previous,
                committed_minor=committed,
                reserved_minor=reserved,
                cap_minor=self.policy.period_cap_minor,
            )

        self.audit.record(
            kind="budget",
            action="deny",
            outcome="deny",
            detail=f"request={request_id} amount={outcome.request.amount_minor} by={approver_id}",
            plugin=None,
        )
        return outcome

    async def cancel(
        self, request_id: int, *, session_key: str, requester_id: str, now: float | None = None
    ) -> ApprovalOutcome:
        """Withdraw your own pending request.

        Only the requester may cancel — an approver has ``deny`` for the other
        direction, and conflating the two would make "who ended this request"
        ambiguous in the audit log.
        """
        ts = time.time() if now is None else now
        async with self.db.session_factory()() as session:
            row = await session.get(SpendRequestRow, request_id)
            if row is None or row.session_key != session_key:
                raise RequestNotFoundError(f"没有编号为 {request_id} 的申请")
            previous = SpendStatus(row.status)
            if previous.is_terminal:
                raise RequestNotPendingError(f"申请 #{request_id} 已结束，无法取消")
            if row.requester_id != requester_id:
                # Same wording as "not found": a member must not learn that another
                # person's request exists, nor be able to withdraw it.
                raise RequestNotFoundError(f"没有编号为 {request_id} 的申请")

            row.status = str(SpendStatus.CANCELLED)
            row.decided_at = ts
            row.decided_by = requester_id
            row.decision_note = "申请人自行撤回"
            await session.commit()
            await session.refresh(row)
            committed, reserved, _ = await self._totals(
                session, session_key=session_key, period=row.period
            )
            outcome = ApprovalOutcome(
                request=_row_to_request(row),
                previous=previous,
                committed_minor=committed,
                reserved_minor=reserved,
                cap_minor=self.policy.period_cap_minor,
            )

        self.audit.record(
            kind="budget",
            action="cancel",
            outcome="allow",
            detail=f"request={request_id} by={requester_id}",
            plugin=None,
        )
        return outcome

    # ---------------------------------------------------------------- expiry
    async def _expire_row(self, session, row: SpendRequestRow, *, now: float) -> None:
        row.status = str(SpendStatus.EXPIRED)
        row.decided_at = now
        row.decided_by = "system"
        row.decision_note = "超时未处理，自动过期"

    async def _sweep_expired_in(
        self, session, *, session_key: str, period: str, now: float | None = None
    ) -> int:
        """Expire stale pending rows for one scope+period. Returns how many.

        Bulk ``UPDATE`` rather than row-by-row: a scope with many stale requests
        should not turn a balance query into N statements.
        """
        ts = time.time() if now is None else now
        result = await session.execute(
            update(SpendRequestRow)
            .where(
                SpendRequestRow.session_key == session_key,
                SpendRequestRow.period == period,
                SpendRequestRow.status == str(SpendStatus.PENDING),
                SpendRequestRow.expires_at > 0,
                SpendRequestRow.expires_at < ts,
            )
            .values(
                status=str(SpendStatus.EXPIRED),
                decided_at=ts,
                decided_by="system",
                decision_note="超时未处理，自动过期",
            )
        )
        count = int(result.rowcount or 0)
        if count:
            logger.info("expired %d stale spend request(s) in %s/%s", count, session_key, period)
        return count

    async def sweep_expired(self, *, now: float | None = None) -> int:
        """Expire stale requests across **all** scopes.

        A background tick uses this so quota is released even when nobody opens
        the budget view — relying on the read path alone means an idle group keeps
        its quota locked until someone happens to look.
        """
        ts = time.time() if now is None else now
        async with self.db.session_factory()() as session:
            result = await session.execute(
                update(SpendRequestRow)
                .where(
                    SpendRequestRow.status == str(SpendStatus.PENDING),
                    SpendRequestRow.expires_at > 0,
                    SpendRequestRow.expires_at < ts,
                )
                .values(
                    status=str(SpendStatus.EXPIRED),
                    decided_at=ts,
                    decided_by="system",
                    decision_note="超时未处理，自动过期",
                )
            )
            count = int(result.rowcount or 0)
            await session.commit()
        if count:
            logger.info("expired %d stale spend request(s) globally", count)
            self.audit.record(
                kind="budget",
                action="expire",
                outcome="allow",
                detail=f"count={count}",
                plugin=None,
            )
        return count


def _period_word(period: str) -> str:
    return {"day": "日", "week": "周", "month": "月"}.get(period, "周期")


def _status_word(status: SpendStatus) -> str:
    return {
        SpendStatus.PENDING: "待审批",
        SpendStatus.APPROVED: "已批准",
        SpendStatus.DENIED: "已驳回",
        SpendStatus.CANCELLED: "已取消",
        SpendStatus.EXPIRED: "已过期",
    }.get(status, str(status))


def _fmt_ts(ts: float) -> str:
    from datetime import datetime

    return datetime.fromtimestamp(ts).strftime("%m-%d %H:%M")
