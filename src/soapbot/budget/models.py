"""Budget domain model: spend requests, quota periods and the approval state machine.

What this module is, and what it deliberately is not
---------------------------------------------------
It is a **quota and authorisation ledger**. It is not a payment integration.

The project's disclaimer promises 不持有任何支付凭据、不调用支付 API、不自动扣款，
所有消费均需人工二次授权. The easy way to break that promise is to add a
convenience method that "just" performs the charge once a request is approved —
nobody re-reads the module that actually moves money, and the promise quietly
stops being true. So the terminal state here is ``APPROVED``, meaning *a human
with authority said yes*, and **nothing in this package performs the spend**.
Execution belongs to a separate, explicitly-operated system (or to a human).

Money is integer minor units
----------------------------
``0.1 + 0.2 != 0.3`` in binary floating point. A quota ledger built on floats
drifts: after enough operations the sum of approved requests no longer equals the
recorded total, and at the boundary it can approve one request too many. Amounts
are therefore ``int`` **minor units** (fen for CNY, cents for USD) and no float
ever enters the accounting path. ``parse_amount`` is the only place user text is
converted, so the rounding rule lives in exactly one function.
"""

from __future__ import annotations

import math
from dataclasses import dataclass, field
from enum import StrEnum

#: Upper bound on a single request, in minor units (10,000,000.00 major units).
#: Chosen to reject obvious garbage (a pasted integer with a stuck key) while
#: staying far above any plausible real spend. It is a sanity bound, not a policy
#: limit — the policy's per-request cap is the actual control.
MAX_AMOUNT_MINOR = 1_000_000_000


class BudgetError(RuntimeError):
    """Base class for budget faults. Callers may catch this to degrade politely."""


class InvalidAmountError(BudgetError):
    """The amount was not a positive, in-range, exact quantity of minor units."""


class BudgetExceededError(BudgetError):
    """The request would push the period's usage past its cap.

    Raised *before* anything is reserved, so a rejected request leaves no trace
    in the ledger — a failed attempt must not consume quota.
    """


class SelfApprovalError(BudgetError):
    """The requester tried to approve their own request.

    Separated from a plain permission error because the remedy is different: the
    actor may well hold ``APPROVE_PAYMENT``, they simply may not apply it to
    themselves. Reporting it as "no permission" would send an owner debugging
    their own role configuration instead of finding a second approver.
    """


class RequestNotPendingError(BudgetError):
    """The request was already decided (approved, denied, cancelled or expired).

    This is the replay guard: an approval link or retried command that arrives
    twice must fail the second time rather than re-running the state transition.
    """


class RequestNotFoundError(BudgetError):
    """No such request *for this caller's scope*.

    Deliberately indistinguishable from "exists but belongs to someone else".
    Returning a distinct error would turn the command into an existence oracle,
    exactly like ``/forget`` probing primary keys.
    """


class SpendStatus(StrEnum):
    """Lifecycle of a spend request.

    ``PENDING`` reserves quota; ``APPROVED`` converts the reservation into
    committed usage; ``DENIED`` / ``CANCELLED`` / ``EXPIRED`` release it. The
    release path matters as much as the reserve path: a request that expires
    without releasing its reservation permanently shrinks the available quota,
    and the symptom (quota slowly disappearing with no visible cause) is one
    operators cannot diagnose without reading this code.
    """

    PENDING = "pending"
    APPROVED = "approved"
    DENIED = "denied"
    CANCELLED = "cancelled"
    EXPIRED = "expired"

    @property
    def is_terminal(self) -> bool:
        return self is not SpendStatus.PENDING


#: Statuses that hold a reservation against the period's cap.
RESERVING_STATES: frozenset[SpendStatus] = frozenset({SpendStatus.PENDING})
#: Statuses that count as consumed usage.
COMMITTED_STATES: frozenset[SpendStatus] = frozenset({SpendStatus.APPROVED})


@dataclass(slots=True)
class SpendRequest:
    """One human-authored request to spend, awaiting a second human's approval."""

    id: int
    amount_minor: int
    currency: str
    purpose: str
    session_key: str
    """Scope the request belongs to. Requests are never visible across scopes."""
    requester_id: str
    requester_name: str = ""
    status: SpendStatus = SpendStatus.PENDING
    period: str = ""
    """Quota period the amount is accounted against (see ``policy.period_key``)."""
    created_at: float = 0.0
    expires_at: float = 0.0
    decided_at: float = 0.0
    decided_by: str = ""
    decision_note: str = ""
    idempotency_key: str = ""
    trace_id: str = ""

    @property
    def amount_major(self) -> float:
        """Display-only. Never feed this back into arithmetic."""
        return self.amount_minor / 100

    def to_dict(self) -> dict:
        return {
            "id": self.id,
            "amount_minor": self.amount_minor,
            "amount_text": format_minor(self.amount_minor, self.currency),
            "currency": self.currency,
            "purpose": self.purpose,
            "session_key": self.session_key,
            "requester_id": self.requester_id,
            "requester_name": self.requester_name,
            "status": str(self.status),
            "period": self.period,
            "created_at": self.created_at,
            "expires_at": self.expires_at,
            "decided_at": self.decided_at,
            "decided_by": self.decided_by,
            "decision_note": self.decision_note,
            "trace_id": self.trace_id,
        }


@dataclass(slots=True)
class BudgetSnapshot:
    """Current usage for one scope and period, as shown to a user."""

    session_key: str
    period: str
    currency: str
    cap_minor: int
    committed_minor: int = 0
    reserved_minor: int = 0
    pending_count: int = 0
    notes: list[str] = field(default_factory=list)

    @property
    def available_minor(self) -> int:
        """What may still be requested.

        Reserved-but-unapproved amounts are subtracted: otherwise ten pending
        requests would each be told the full remainder is available, and the
        eleventh approval would overrun the cap. Reservations are what make the
        check meaningful in the presence of concurrent requests.
        """
        return max(0, self.cap_minor - self.committed_minor - self.reserved_minor)

    @property
    def usage_ratio(self) -> float:
        if self.cap_minor <= 0:
            return 0.0
        return min(1.0, (self.committed_minor + self.reserved_minor) / self.cap_minor)

    def to_dict(self) -> dict:
        return {
            "session_key": self.session_key,
            "period": self.period,
            "currency": self.currency,
            "cap_minor": self.cap_minor,
            "cap_text": format_minor(self.cap_minor, self.currency),
            "committed_minor": self.committed_minor,
            "committed_text": format_minor(self.committed_minor, self.currency),
            "reserved_minor": self.reserved_minor,
            "reserved_text": format_minor(self.reserved_minor, self.currency),
            "available_minor": self.available_minor,
            "available_text": format_minor(self.available_minor, self.currency),
            "pending_count": self.pending_count,
            "usage_ratio": round(self.usage_ratio, 4),
            "notes": self.notes,
        }


_SYMBOLS = {"CNY": "¥", "USD": "$", "EUR": "€", "JPY": "¥", "POINT": ""}


def format_minor(amount_minor: int, currency: str = "CNY") -> str:
    """Render minor units for humans (``1250 -> "¥12.50"``)."""
    major = amount_minor / 100
    symbol = _SYMBOLS.get(currency.upper(), "")
    body = f"{major:,.2f}"
    return f"{symbol}{body}" if symbol else f"{body} {currency}"


def parse_amount(text: str) -> int:
    """Parse user-supplied money into minor units.

    Accepts ``"12"``, ``"12.5"``, ``"12.50"``, ``"1,250.00"`` and a leading
    currency symbol. Rejects everything else — including ``"nan"``, ``"inf"``,
    ``"1e9"`` and negatives — because the alternative is an amount that compares
    true against every cap or silently becomes zero.

    Rounding: more than two decimals is an **error**, not silently rounded. A
    request for ``10.005`` is ambiguous (half-fen), and guessing which way the
    user meant it is how a ledger acquires a discrepancy nobody can explain.
    """
    if text is None:
        raise InvalidAmountError("金额不能为空")
    raw = str(text).strip()
    if not raw:
        raise InvalidAmountError("金额不能为空")

    # Strip a leading currency symbol/marker, then thousands separators.
    for symbol in (*_SYMBOLS.values(), "¥", "$", "€", "RMB", "CNY"):
        if symbol and raw.startswith(symbol):
            raw = raw[len(symbol) :].strip()
            break
    raw = raw.replace(",", "").replace("，", "")

    try:
        # ``Decimal`` rather than ``float``: parsing then scaling in float turns
        # "0.29" into 28.999999999999996 minor units and truncates to 28.
        from decimal import Decimal, InvalidOperation

        value = Decimal(raw)
    except (InvalidOperation, ValueError) as exc:
        raise InvalidAmountError(f"无法识别的金额：{text}") from exc

    if not value.is_finite():
        raise InvalidAmountError(f"金额必须是有限数值：{text}")
    if value <= 0:
        raise InvalidAmountError("金额必须大于 0")

    minor = value * 100
    if minor != minor.to_integral_value():
        raise InvalidAmountError("金额最多两位小数")

    amount = int(minor)
    if amount > MAX_AMOUNT_MINOR:
        raise InvalidAmountError(
            f"单笔金额超过上限 {format_minor(MAX_AMOUNT_MINOR)}"
        )
    return amount


def require_positive_int(value: object, *, field_name: str = "amount_minor") -> int:
    """Validate an already-parsed amount coming from code (not user text).

    ``bool`` is rejected explicitly: it is an ``int`` subclass, so ``True`` would
    otherwise be accepted as an amount of one minor unit.
    """
    if isinstance(value, bool) or not isinstance(value, int):
        raise InvalidAmountError(f"{field_name} 必须是整数")
    if value <= 0:
        raise InvalidAmountError(f"{field_name} 必须大于 0")
    if value > MAX_AMOUNT_MINOR:
        raise InvalidAmountError(f"{field_name} 超过上限")
    return value


def sanitize_purpose(text: str, *, limit: int = 200) -> str:
    """Normalise a free-text purpose.

    Purposes are attacker-supplied and get rendered in the approval UI and in
    group chat. Collapsing whitespace and stripping control characters keeps a
    request from arriving pre-formatted to look like a system notice, and the
    length cap keeps one request from filling the operator's terminal.
    """
    if not text:
        return ""
    cleaned = "".join(
        ch if (ch.isprintable() or ch in " \t") else " " for ch in str(text)
    )
    cleaned = " ".join(cleaned.split())
    return cleaned[:limit]


def is_finite_number(value: object) -> bool:
    """Guard for values that reach the ledger from JSON (WebUI / plugin calls)."""
    return (
        isinstance(value, int | float)
        and not isinstance(value, bool)
        and math.isfinite(value)
    )
