"""Pipeline stages that enforce identity, authorization and abuse limits.

Ordering rationale (this is the crux of the whole defence):

    dedup -> **guard** -> whitelist -> ...

``GuardStage`` runs *before* the whitelist, wake, command, recall and model
stages for one reason: every stage after it consumes resources, touches the
database, or leaks information the moment it runs. If an unauthorised user can
reach the command stage at all, `/kb` has already read the operator's documents
before any later check could object. Authorization must therefore be decided
once, early, from trusted facts — not sprinkled through handlers.

This is the "fail before you read" principle: the cheapest way to not leak data
is to never query it.
"""

from __future__ import annotations

import logging
from typing import Any

from soapbot.config import settings
from soapbot.core.pipeline import PipelineContext, Stage, StageResult
from soapbot.security.audit import AuditLog, get_audit_log
from soapbot.security.injection import (
    INJECTION_BLOCK_ON,
    injection_refusal,
    looks_like_injection,
)
from soapbot.security.principal import (
    Permission,
    Principal,
    PrincipalResolver,
    Role,
)
from soapbot.security.ratelimit import SlidingWindowLimiter

logger = logging.getLogger(__name__)

_DENY_NOTICE = "抱歉，你没有执行该操作的权限。"
"""Deliberately uninformative.

Saying "only admins may use /kb" tells an attacker exactly which door to push on
and confirms the knowledge base exists. A flat refusal leaks nothing.
"""


class GuardStage(Stage):
    """Resolve the principal and reject unauthorised traffic before any work.

    Three independent gates, each failing closed:

    1. **Authentication** — is this identity trustworthy? A reverse WebSocket that
       accepted an unauthenticated client yields ``authenticated=False``, and an
       unauthenticated principal cannot hold any permission.
    2. **Identity presence** — an event with no resolvable sender id is anonymous
       and therefore refused; every downstream decision (scope, ownership,
       audit attribution) depends on knowing who this is.
    3. **Abuse** — has this actor just produced a burst of denials?

    Scene-level admission (group allow-list, private-off-by-default) is *not*
    duplicated here — it lives in :class:`soapbot.core.stages.AccessPolicy` and
    runs immediately after, still before any command handler or DB read. One
    source of truth per decision is what keeps the two from drifting apart.
    """

    name = "guard"

    def __init__(
        self,
        resolver: PrincipalResolver,
        *,
        audit: AuditLog | None = None,
        denial_limit: int = 8,
        denial_window: float = 60.0,
    ) -> None:
        self.resolver = resolver
        self.audit = audit or get_audit_log()
        self._denials = SlidingWindowLimiter(limit=denial_limit, window_seconds=denial_window)

    async def run(self, ctx: PipelineContext) -> StageResult:
        # Read trust from the *event*, which the adapter set, not from ``extras``,
        # which any later stage could overwrite. Trust must flow from the
        # transport inward, never be re-asserted by the pipeline.
        authenticated = bool(getattr(ctx.event, "transport_authenticated", True))
        principal = self.resolver.resolve(ctx.event, authenticated=authenticated)
        ctx.extras["principal"] = principal

        if not authenticated:
            self.audit.record(
                kind="authz",
                action="authenticate",
                outcome="deny",
                principal=principal,
                detail="transport reported an unauthenticated peer",
                trace_id=ctx.event.trace_id,
                adapter=principal.adapter,
            )
            return self._deny(ctx, principal, "unauthenticated")

        # Abuse gate: a burst of denials means enumeration, not a lost user.
        limit = self._denials.check(f"{principal.scene}:{principal.user_id}")
        if limit.limited:
            self.audit.record(
                kind="rate_limit",
                action="denial_burst",
                outcome="block",
                principal=principal,
                detail=f"retry_after={limit.retry_after:.1f}s",
                trace_id=ctx.event.trace_id,
            )
            return StageResult(halt=True, reason="abuse_rate_limited")

        # Identity gate: anonymous events carry no attribution, so no downstream
        # ownership check could ever be made for them.
        if principal.role is Role.ANONYMOUS:
            return self._deny(ctx, principal, "anonymous")

        self.audit.record(
            kind="authz",
            action="interact",
            outcome="allow",
            principal=principal,
            detail=principal.source,
            trace_id=ctx.event.trace_id,
        )
        return StageResult()

    def _deny(self, ctx: PipelineContext, principal: Principal, reason: str) -> StageResult:
        """Record the denial and *silently* drop the message.

        Silent for unauthorised traffic: replying "you are not allowed" to a
        stranger confirms the bot is alive and listening on this adapter, which is
        reconnaissance value for free. Authorised users who hit a real permission
        wall get a notice (see :class:`AuthorizationStage`).
        """
        self.audit.record(
            kind="authz",
            action="interact",
            outcome="deny",
            principal=principal,
            detail=reason,
            trace_id=ctx.event.trace_id,
        )
        return StageResult(halt=True, reason=reason)

    def note_denial(self, principal: Principal) -> None:
        """Feed the abuse counter when a *permission* check fails later."""
        self._denials.check(f"{principal.scene}:{principal.user_id}")


class InjectionScreenStage(Stage):
    """Flag prompt-injection attempts and quarantine obviously hostile turns.

    Placement: after sanitize (so obfuscation is normalised) and before the model.

    This stage never *authorizes* anything — it only annotates and, for clear-cut
    instruction-override attempts, refuses. A false positive costs one unhelpful
    reply; a false negative on the *authorization* path would be a breach, which
    is why authorization does not depend on this stage at all.
    """

    name = "injection_screen"

    def __init__(
        self, audit: AuditLog | None = None, *, block_on: int = INJECTION_BLOCK_ON
    ) -> None:
        self.audit = audit or get_audit_log()
        self.block_on = block_on

    async def run(self, ctx: PipelineContext) -> StageResult:
        from soapbot.core.message import SegmentType

        segments = ctx.extras.get("clean_segments") or ctx.event.segments
        text = "".join(
            s.plain() for s in segments if s.type is SegmentType.TEXT
        ).strip()
        if not text:
            return StageResult()

        suspicious, labels = looks_like_injection(text)
        ctx.extras["injection_labels"] = labels
        if not suspicious:
            return StageResult()

        principal = ctx.extras.get("principal")
        # A privileged user *may* legitimately paste a suspicious snippet while
        # debugging ("why does this prompt inject?"). They are flagged, not
        # blocked — their authority is already established elsewhere.
        is_privileged = bool(getattr(principal, "is_privileged", False))

        self.audit.record(
            kind="injection",
            action="detect",
            outcome="allow" if (is_privileged or len(labels) < self.block_on) else "block",
            principal=principal,
            detail=",".join(labels[:4]),
            trace_id=ctx.event.trace_id,
            text_len=len(text),
        )

        if is_privileged or len(labels) < self.block_on:
            return StageResult()

        # Refuse *in the reply*, not by silence. The audit entry above already says
        # what matched; the reply says the same thing to the group, so "it ignored me"
        # and "it refused me" stop looking identical from the outside. The labels are
        # our pattern names, never the quarantined text.
        ctx.model_reply = injection_refusal(ctx.locale, labels)
        ctx.extras["skip_model"] = True
        ctx.extras["injection_blocked"] = True
        return StageResult()

    def guard_stage(self) -> GuardStage | None:  # pragma: no cover - typing aid
        return None


class AuthorizationStage(Stage):
    """Enforce the ``CHAT`` permission and surface a notice when it fails.

    Split from :class:`GuardStage` on purpose: Guard is about *identity and
    reachability* (silent drop), this is about *capability* (explicit refusal).
    Keeping them apart means the noisy, user-visible path can never accidentally
    run before the quiet one.
    """

    name = "authorization"

    def __init__(self, audit: AuditLog | None = None, *, notice: str = _DENY_NOTICE) -> None:
        self.audit = audit or get_audit_log()
        self.notice = notice

    async def run(self, ctx: PipelineContext) -> StageResult:
        principal: Principal | None = ctx.extras.get("principal")
        if principal is None:
            # No principal means Guard was not installed. Fail closed rather than
            # letting an unconfigured pipeline become an open pipeline.
            logger.error("authorization stage ran without a principal; failing closed")
            return StageResult(halt=True, reason="no_principal")

        if principal.can(Permission.CHAT):
            return StageResult()

        self.audit.record(
            kind="authz",
            action="chat",
            outcome="deny",
            principal=principal,
            detail="missing CHAT permission",
            trace_id=ctx.event.trace_id,
        )
        ctx.model_reply = self.notice
        ctx.extras["skip_model"] = True
        return StageResult()


class ModelQuotaStage(Stage):
    """Cap how often one person may reach the model in a window.

    The existing limiters all count *refusals*: a burst of denials means enumeration, and
    that is a different question from cost. Nothing bounded a user who simply talks a lot
    — every message is a provider call, and on a busy group one enthusiastic member can
    spend the operator's budget without ever being refused anything.

    Placed after the command stages and before context assembly, so:

    * ``/help`` and other free commands do not consume the quota (they cost nothing);
    * the refusal happens before the model call, which is the only place a quota saves
      money.

    The refusal is spoken rather than silent. Silence is right for unauthorised traffic —
    acknowledging it confirms the bot is listening — but a legitimate user hitting a rate
    limit needs to know why the bot stopped answering, or they will assume it broke.
    """

    name = "model_quota"

    def __init__(
        self,
        *,
        audit: AuditLog | None = None,
        calls: int | None = None,
        window_seconds: float | None = None,
        notice: str = "",
    ) -> None:
        self.audit = audit or get_audit_log()
        self.calls = settings.user_quota_calls if calls is None else calls
        self.window_seconds = (
            settings.user_quota_window_seconds if window_seconds is None else window_seconds
        )
        self.notice = notice or settings.user_quota_notice
        self._limiter = SlidingWindowLimiter(
            limit=max(1, self.calls), window_seconds=max(1.0, self.window_seconds)
        )
        self._limited = 0
        """How many turns this process refused. Exposed for the panel."""

    async def run(self, ctx: PipelineContext) -> StageResult:
        principal: Principal | None = ctx.extras.get("principal")
        if principal is None:
            # No principal means Guard was not installed. The quota is a cost control,
            # not an authorization gate, so refusing here would be the wrong failure —
            # but it is also the one case where we cannot attribute the call.
            return StageResult()

        # Privileged users are exempt: an operator debugging the bot should not be
        # rate-limited by the control they are operating.
        if getattr(principal, "is_privileged", False):
            return StageResult()

        key = f"{principal.adapter}:{principal.user_id}"
        result = self._limiter.check(key)
        ctx.extras["quota_remaining"] = result.remaining
        if not result.limited:
            return StageResult()

        self._limited += 1
        self.audit.record(
            kind="rate_limit",
            action="model_quota",
            outcome="block",
            principal=principal,
            detail=(
                f"limit={self.calls}/{self.window_seconds:.0f}s "
                f"retry_after={result.retry_after:.0f}s"
            ),
            trace_id=ctx.event.trace_id,
        )
        ctx.model_reply = self.notice
        ctx.extras["skip_model"] = True
        ctx.extras["quota_exceeded"] = True
        return StageResult()

    def status(self) -> dict[str, Any]:
        """What the panel shows. Counts only — never the keys, which are user ids."""
        return {
            "limit": self.calls,
            "window_seconds": self.window_seconds,
            "refused": self._limited,
        }


def require(
    ctx: PipelineContext,
    permission: Permission,
    *,
    audit: AuditLog | None = None,
    action: str = "",
) -> tuple[bool, str]:
    """Check a permission from inside a command handler.

    Returns ``(allowed, refusal_text)`` instead of raising, because handlers must
    be able to return a user-facing string and this keeps the call sites linear.

    Every denial is audited — that record is what makes an enumeration attempt
    visible, since the attacker sees only a bland refusal.
    """
    principal: Principal | None = ctx.extras.get("principal")
    label = action or permission.value
    if principal is None:
        (audit or get_audit_log()).record(
            kind="authz",
            action=label,
            outcome="deny",
            detail="no principal on context",
            trace_id=ctx.event.trace_id,
        )
        return False, _DENY_NOTICE

    if principal.can(permission):
        return True, ""

    (audit or get_audit_log()).record(
        kind="authz",
        action=label,
        outcome="deny",
        principal=principal,
        detail=f"requires {permission} (role={principal.role})",
        trace_id=ctx.event.trace_id,
    )
    return False, _DENY_NOTICE
