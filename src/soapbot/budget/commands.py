"""``/budget`` and ``/approve`` command handlers (Wave 5).

Why these live here and not in ``CommandStage`` directly
-------------------------------------------------------
``CommandStage`` is core memory plumbing that must work with every optional
subsystem disabled. The budget workflow is optional: a deployment that never
spends should not fail to import a ledger. Keeping the handlers in this module
and letting ``CommandStage`` call into it when configured means ``stages.py``
acquires no new mandatory dependency.

Who may do what
---------------
* ``/budget`` — view the current period's usage. Any member: seeing "we have
  ¥37 left this month" is not privileged information inside the group whose
  budget it is.
* ``/budget <金额> <用途>`` — request. Any member with ``USE_COMMAND``, but the
  request is **not** effective until someone else approves it.
* ``/budget approve <id>`` / ``/budget deny <id>`` — requires
  ``APPROVE_PAYMENT`` (admin+). This is the ``Permission.APPROVE_PAYMENT`` that
  existed from the start and, until now, was checked by nothing.
* ``/budget cancel <id>`` — the requester, and only the requester.

The scope is always ``ctx.event.session_key``
---------------------------------------------
Never a command argument. If the scope came from ``args``, ``/budget 500 买书
--scope other:group:9`` would spend another group's quota, and the ledger would
faithfully record it as theirs. Same reasoning as ``/recall``.
"""

from __future__ import annotations

import logging
from typing import ClassVar

from soapbot.budget.models import (
    BudgetError,
    BudgetExceededError,
    InvalidAmountError,
    RequestNotFoundError,
    RequestNotPendingError,
    SelfApprovalError,
    SpendStatus,
    format_minor,
    parse_amount,
)
from soapbot.budget.store import BudgetStore
from soapbot.core.pipeline import PipelineContext
from soapbot.security.audit import AuditLog, get_audit_log
from soapbot.security.principal import Permission
from soapbot.security.stages import require

logger = logging.getLogger(__name__)

USAGE = (
    "用法：\n"
    "/budget — 查看本期额度\n"
    "/budget <金额> <用途> — 发起消费申请，例：/budget 25.5 买资料\n"
    "/budget approve <编号> [备注] — 批准（需管理员）\n"
    "/budget deny <编号> [备注] — 驳回（需管理员）\n"
    "/budget cancel <编号> — 撤回自己的申请"
)


class BudgetCommands:
    """Handler bundle for the budget command family."""

    #: Sub-commands that decide a request, mapped to the permission they need.
    #: Anything not listed is a *request* or a *view*, which members may do.
    DECISION_PERMISSIONS: ClassVar[dict[str, Permission]] = {
        "approve": Permission.APPROVE_PAYMENT,
        "deny": Permission.APPROVE_PAYMENT,
    }

    def __init__(self, store: BudgetStore, *, audit: AuditLog | None = None) -> None:
        self.store = store
        self.audit = audit or get_audit_log()

    # ------------------------------------------------------------------ entry
    async def handle(self, ctx: PipelineContext, args: list[str]) -> str:
        """Dispatch ``/budget`` with no args, an amount, or a sub-command."""
        if not args:
            return await self._show(ctx)

        head = args[0].lower()
        if head in self.DECISION_PERMISSIONS:
            # Authorise before touching the ledger: reaching the handler at all
            # would let a member probe request ids from the differing errors.
            allowed, refusal = require(
                ctx,
                self.DECISION_PERMISSIONS[head],
                audit=self.audit,
                action=f"budget:{head}",
            )
            if not allowed:
                return refusal
            return await self._decide(ctx, head, args[1:])

        if head in ("cancel", "撤回"):
            return await self._cancel(ctx, args[1:])

        if head in ("list", "列表", "pending"):
            return await self._list(ctx)

        return await self._request(ctx, args)

    # ------------------------------------------------------------------ views
    async def _show(self, ctx: PipelineContext) -> str:
        snap = await self.store.snapshot(session_key=ctx.event.session_key)
        lines = [
            f"本期（{snap.period}）额度",
            f"  上限　{format_minor(snap.cap_minor, snap.currency)}",
            f"  已用　{format_minor(snap.committed_minor, snap.currency)}",
            f"  待批　{format_minor(snap.reserved_minor, snap.currency)}"
            f"（{snap.pending_count} 笔）",
            f"  可用　{format_minor(snap.available_minor, snap.currency)}",
        ]
        if snap.pending_count:
            lines.append("用 /budget list 查看待审批申请。")
        return "\n".join(lines)

    async def _list(self, ctx: PipelineContext) -> str:
        pending = await self.store.list_pending(session_key=ctx.event.session_key)
        if not pending:
            return "当前没有待审批的申请。"
        lines = ["待审批申请："]
        for req in pending:
            lines.append(
                f"  #{req.id} {format_minor(req.amount_minor, req.currency)} "
                f"{req.purpose or '（未填用途）'} — {req.requester_name or req.requester_id}"
            )
        lines.append("管理员可用 /budget approve <编号> 或 /budget deny <编号> 处理。")
        return "\n".join(lines)

    # --------------------------------------------------------------- requests
    async def _request(self, ctx: PipelineContext, args: list[str]) -> str:
        principal = ctx.extras.get("principal")
        try:
            amount_minor = parse_amount(args[0])
        except InvalidAmountError as exc:
            return f"{exc}\n\n{USAGE}"

        purpose = " ".join(args[1:]).strip()
        if not purpose:
            # A request without a stated purpose is unreviewable: the approver
            # would be authorising an unlabelled transfer of quota.
            return "请说明用途，例如：/budget 25.5 买资料"

        try:
            req, created = await self.store.create(
                session_key=ctx.event.session_key,
                requester_id=getattr(principal, "user_id", "") or "",
                requester_name=getattr(principal, "display_name", "") or "",
                amount_minor=amount_minor,
                purpose=purpose,
                trace_id=ctx.event.trace_id,
                # Doubling-tap protection: the same text within the same minute is
                # the same intent. Without this, an adapter resend or an impatient
                # second tap reserves the amount twice.
                idempotency_key=_idempotency_key(ctx, amount_minor, purpose),
            )
        except BudgetExceededError as exc:
            return str(exc)
        except BudgetError as exc:
            return f"申请未受理：{exc}"

        if not created:
            return (
                f"这笔申请已经在处理中了（#{req.id}，"
                f"{format_minor(req.amount_minor, req.currency)}），无需重复提交。"
            )

        return (
            f"已提交申请 #{req.id}：{format_minor(req.amount_minor, req.currency)}"
            f"（{req.purpose}）\n"
            "需要另一位管理员用 /budget approve %d 确认。" % req.id
        )

    # --------------------------------------------------------------- decisions
    async def _decide(self, ctx: PipelineContext, kind: str, args: list[str]) -> str:
        if not args:
            return f"用法：/budget {kind} <编号> [备注]"
        try:
            request_id = int(args[0].lstrip("#"))
        except ValueError:
            return "申请编号必须是数字。"

        principal = ctx.extras.get("principal")
        approver_id = getattr(principal, "user_id", "") or ""
        note = " ".join(args[1:]).strip()

        try:
            if kind == "approve":
                outcome = await self.store.approve(
                    request_id,
                    session_key=ctx.event.session_key,
                    approver_id=approver_id,
                    approver_name=getattr(principal, "display_name", "") or "",
                    note=note,
                )
            else:
                outcome = await self.store.deny(
                    request_id,
                    session_key=ctx.event.session_key,
                    approver_id=approver_id,
                    note=note,
                )
        except SelfApprovalError as exc:
            return str(exc)
        except RequestNotFoundError as exc:
            return str(exc)
        except RequestNotPendingError as exc:
            return str(exc)
        except BudgetExceededError as exc:
            return f"无法批准：{exc}"
        except BudgetError as exc:
            return f"操作失败：{exc}"

        req = outcome.request
        amount = format_minor(req.amount_minor, req.currency)
        notice = await self._remaining_notice(ctx)
        if kind == "approve":
            return (
                f"已批准申请 #{req.id}：{amount}（{req.purpose}）\n"
                f"本期剩余可用 {format_minor(outcome.available_minor, req.currency)}。\n"
                "提醒：本机器人不执行任何支付，请按你们既有的渠道人工完成。"
                f"{notice}"
            )
        return f"已驳回申请 #{req.id}：{amount}（{req.purpose}）{notice}"

    async def _remaining_notice(self, ctx: PipelineContext) -> str:
        """Tell the approver what is still queued after this decision.

        An approver working through a list otherwise has to run ``/budget list`` again
        to discover whether they are done — and the answer "there are 3 more" is
        exactly the information that stops one of them from waiting for days.
        """
        try:
            pending = await self.store.list_pending(session_key=ctx.event.session_key)
        except Exception as exc:  # pragma: no cover - a notice must never fail a decision
            logger.warning("could not render pending notice: %s", type(exc).__name__)
            return ""
        if not pending:
            return ""
        currency = pending[0].currency or self.store.policy.currency
        return "\n" + render_pending_notice(pending, currency=currency)

    async def _cancel(self, ctx: PipelineContext, args: list[str]) -> str:
        if not args:
            return "用法：/budget cancel <编号>"
        try:
            request_id = int(args[0].lstrip("#"))
        except ValueError:
            return "申请编号必须是数字。"

        principal = ctx.extras.get("principal")
        try:
            outcome = await self.store.cancel(
                request_id,
                session_key=ctx.event.session_key,
                requester_id=getattr(principal, "user_id", "") or "",
            )
        except (RequestNotFoundError, RequestNotPendingError) as exc:
            return str(exc)
        except BudgetError as exc:
            return f"操作失败：{exc}"

        return f"已撤回申请 #{outcome.request.id}。"


def _idempotency_key(ctx: PipelineContext, amount_minor: int, purpose: str) -> str:
    """Stable key for "the same request, submitted again".

    Built from caller + amount + purpose + a one-minute bucket. Including the
    minute is what keeps this from being *too* sticky: requesting the same lunch
    twice on purpose, an hour apart, must create two requests. Stripping a trace
    id or message id out on purpose — those differ per delivery, which is exactly
    the duplicate we are trying to collapse.
    """
    import hashlib

    principal = ctx.extras.get("principal")
    user_id = getattr(principal, "user_id", "") or ""
    bucket = int(__import__("time").time() // 60)
    raw = f"{ctx.event.session_key}|{user_id}|{amount_minor}|{purpose}|{bucket}"
    return hashlib.sha256(raw.encode("utf-8")).hexdigest()[:32]


def render_pending_notice(requests: list, *, currency: str = "CNY") -> str:
    """One-line summary used by the notice/reminder path."""
    if not requests:
        return ""
    total = sum(r.amount_minor for r in requests)
    return (
        f"有 {len(requests)} 笔待审批申请，合计 "
        f"{format_minor(total, currency)}，用 /budget list 查看。"
    )


def status_label(status: SpendStatus) -> str:
    return {
        SpendStatus.PENDING: "待审批",
        SpendStatus.APPROVED: "已批准",
        SpendStatus.DENIED: "已驳回",
        SpendStatus.CANCELLED: "已取消",
        SpendStatus.EXPIRED: "已过期",
    }.get(status, str(status))
