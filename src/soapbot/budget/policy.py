"""Quota policy: how much may be spent, by whom, per period.

Why a policy object instead of constants
----------------------------------------
Limits are the part an operator changes without touching code, and the part that
gets *wrong* silently. Keeping them in one object with validation means an
invalid configuration fails at construction — a deployment with
``per_request > period_cap`` would otherwise accept requests that can never be
approved, which looks like a broken approval flow rather than a config error.

Period boundaries are explicit
------------------------------
``period_key`` is computed by the **host** from a trusted clock, never supplied by
a caller. If the period were an argument, a requester could pass
``period="2000-01"`` and spend against an empty historical bucket — resetting
their own quota at will.
"""

from __future__ import annotations

import time
from dataclasses import dataclass
from datetime import UTC, datetime

from soapbot.budget.models import BudgetError, format_minor


class PolicyError(BudgetError):
    """The configured limits are internally inconsistent."""


@dataclass(slots=True)
class BudgetPolicy:
    """Limits for one installation.

    ``currency`` is informational: the ledger never converts between currencies.
    Accepting two currencies against one cap would be a silent mis-accounting
    (1 USD and 1 CNY both "count as 100"), so only one currency is allowed per
    deployment and any request quoting another is refused.
    """

    currency: str = "CNY"
    period: str = "month"
    """``day`` / ``week`` / ``month``. Anything else is rejected at construction."""
    period_cap_minor: int = 50_000
    """Cap per period, in minor units (default ¥500.00)."""
    per_request_cap_minor: int = 10_000
    """Cap for a single request (default ¥100.00)."""
    request_ttl_seconds: float = 24 * 3600
    """How long a pending request waits before it expires and releases quota."""
    require_distinct_approver: bool = True
    """Whether the requester may approve their own request.

    Kept configurable, but the default is ``True`` because the whole point of a
    second approval is that it is a *second* person. An operator who turns this
    off has converted the workflow into a confirmation dialog, and should know
    that is what they did — hence the explicit name rather than a bare flag.
    """

    def __post_init__(self) -> None:
        if self.currency.upper() != self.currency:
            self.currency = self.currency.upper()
        if self.period not in ("day", "week", "month"):
            raise PolicyError(f"unsupported period {self.period!r}")
        if self.period_cap_minor <= 0:
            raise PolicyError("period_cap_minor must be positive")
        if self.per_request_cap_minor <= 0:
            raise PolicyError("per_request_cap_minor must be positive")
        if self.per_request_cap_minor > self.period_cap_minor:
            # Every request would be individually valid but collectively impossible
            # to approve; the operator's first approval attempt would fail with a
            # budget error that looks like a bug in the ledger.
            raise PolicyError(
                f"per_request_cap {format_minor(self.per_request_cap_minor, self.currency)} "
                f"exceeds period_cap {format_minor(self.period_cap_minor, self.currency)}"
            )
        if self.request_ttl_seconds <= 0:
            raise PolicyError("request_ttl_seconds must be positive")

    def period_key(self, *, now: float | None = None, tz_offset_hours: int = 8) -> str:
        """The accounting bucket for ``now``.

        Uses a fixed UTC offset rather than the OS timezone so the key does not
        change when the container's ``TZ`` differs from the operator's — a period
        that shifts by eight hours at a deployment boundary produces a period with
        twice the cap.

        Default offset is +8 (Asia/Shanghai), matching ``settings.default_timezone``
        for the project's primary audience; it is a parameter so a differently
        located deployment can align the reset with its own midnight.
        """
        ts = time.time() if now is None else now
        moment = datetime.fromtimestamp(ts, tz=UTC)
        if tz_offset_hours:
            from datetime import timedelta

            moment = moment + timedelta(hours=tz_offset_hours)
        if self.period == "day":
            return moment.strftime("%Y-%m-%d")
        if self.period == "week":
            iso = moment.isocalendar()
            return f"{iso.year}-W{iso.week:02d}"
        return moment.strftime("%Y-%m")

    def expires_at(self, *, now: float | None = None) -> float:
        ts = time.time() if now is None else now
        return ts + self.request_ttl_seconds

    def check_amount(self, amount_minor: int) -> None:
        """Per-request validation, before the ledger is consulted."""
        from soapbot.budget.models import require_positive_int

        require_positive_int(amount_minor)
        if amount_minor > self.per_request_cap_minor:
            raise BudgetError(
                f"单笔上限 {format_minor(self.per_request_cap_minor, self.currency)}，"
                f"本次 {format_minor(amount_minor, self.currency)}"
            )

    def check_currency(self, currency: str) -> None:
        """Refuse a currency the ledger does not account in."""
        if (currency or "").upper() != self.currency:
            raise BudgetError(
                f"本部署仅使用 {self.currency} 记账，不接受 {currency or '未指定'}"
            )
