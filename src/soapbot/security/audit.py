"""Append-only audit log for security-relevant decisions.

Every authorization outcome is recorded, including *denials*. A denial log is the
only way to answer "did anyone try to escalate?" after the fact — and it is what
turns an invisible brute-force attempt (`/forget 1`, `/forget 2`, ...) into
something an operator can act on.

Records are kept in memory (bounded) and mirrored to the normal logger, so they
land in the WebUI log stream without requiring a second logging pipeline.
"""

from __future__ import annotations

import logging
import re
import time
from collections import deque
from dataclasses import asdict, dataclass, field
from typing import Any

logger = logging.getLogger("soapbot.security.audit")

_REDACT_KEYS = ("token", "secret", "password", "key", "authorization", "cookie")

#: Inline credential patterns for free-text fields. Applied to ``detail`` and to
#: log lines, because the most common way a secret escapes is not a structured
#: field but a URL or message string someone thought was harmless.
_INLINE_SECRET_RE = re.compile(
    r"(sk-[A-Za-z0-9_\-]{8,}"
    r"|(?i:bearer)\s+[A-Za-z0-9._\-]{8,}"
    r"|(?i:(?:api[_-]?key|access[_-]?token|refresh[_-]?token|token|secret|password|passwd))"
    r"\s*[=:]\s*[^\s&,;\"']{4,})"
)


def _redact_detail(text: str) -> str:
    """Mask credentials in a free-text detail field, and cap its length.

    Kept local (not imported from ``security.injection``) so this module has no
    import cycle with the plugin layer, which imports the audit log.
    """
    if not text:
        return ""
    out = _INLINE_SECRET_RE.sub("***REDACTED***", str(text))
    return out[:500]


@dataclass(slots=True)
class AuditEvent:
    ts: float
    kind: str
    """login / authz / injection / memory / command / rate_limit."""
    action: str
    outcome: str
    """allow / deny / block / quarantine."""
    user_id: str = ""
    role: str = ""
    scene: str = ""
    group_id: str = ""
    plugin: str = ""
    """Originating plugin, when the event concerns plugin activity.

    Promoted to a first-class field rather than left in ``meta`` because every
    plugin-related query filters on it ("show me everything this plugin did"). As a
    meta key it would be invisible to callers that do not know the key name, which
    is how an audit trail quietly stops being usable for triage.
    """

    detail: str = ""
    trace_id: str = ""
    meta: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        data = asdict(self)
        meta = data.get("meta") or {}
        data["meta"] = {
            k: ("***REDACTED***" if any(s in k.lower() for s in _REDACT_KEYS) else v)
            for k, v in meta.items()
        }
        return data


class AuditLog:
    def __init__(self, capacity: int = 2000) -> None:
        self._events: deque[AuditEvent] = deque(maxlen=capacity)
        self.denials = 0
        self.blocks = 0

    def record(
        self,
        *,
        kind: str,
        action: str,
        outcome: str,
        principal=None,
        detail: str = "",
        trace_id: str = "",
        plugin: str = "",
        **meta: Any,
    ) -> AuditEvent:
        # ``detail`` is free text assembled by callers from runtime data: URLs with
        # query strings, exception messages, ids from the wire. It is streamed to
        # the WebUI log view and mirrored to the log file, so it must be redacted
        # here rather than trusting every call site to remember. A token appearing
        # in ``detail`` would otherwise be published by the very component meant to
        # record security events.
        safe_detail = _redact_detail(detail)
        event = AuditEvent(
            ts=time.time(),
            kind=kind,
            action=action,
            outcome=outcome,
            user_id=getattr(principal, "user_id", "") or "",
            role=str(getattr(principal, "role", "") or ""),
            scene=getattr(principal, "scene", "") or "",
            group_id=getattr(principal, "group_id", "") or "",
            plugin=plugin or "",
            detail=safe_detail,
            trace_id=trace_id,
            meta=meta,
        )
        self._events.append(event)

        if outcome == "deny":
            self.denials += 1
            logger.warning(
                "AUTHZ DENY action=%s user=%s role=%s scene=%s group=%s detail=%s trace=%s",
                action,
                event.user_id or "?",
                event.role,
                event.scene,
                event.group_id,
                detail,
                trace_id,
            )
        elif outcome in ("block", "quarantine"):
            self.blocks += 1
            logger.warning(
                "SECURITY %s action=%s user=%s detail=%s trace=%s",
                outcome.upper(),
                action,
                event.user_id or "?",
                detail,
                trace_id,
            )
        else:
            logger.info(
                "AUDIT %s action=%s user=%s role=%s trace=%s",
                outcome,
                action,
                event.user_id or "?",
                event.role,
                trace_id,
            )
        return event

    def recent(self, *, limit: int = 100, kind: str = "") -> list[dict[str, Any]]:
        items = list(self._events)
        if kind:
            items = [e for e in items if e.kind == kind]
        return [e.to_dict() for e in items[-limit:]]

    def denials_for(self, user_id: str) -> int:
        return sum(
            1
            for e in self._events
            if e.outcome == "deny" and e.user_id == user_id
        )

    def clear(self) -> None:
        self._events.clear()
        self.denials = 0
        self.blocks = 0


_audit = AuditLog()


def get_audit_log() -> AuditLog:
    return _audit
