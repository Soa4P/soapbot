"""Security primitives: identity, authorization, injection defence, auditing.

The guiding rule for this package:

    **Authorization is decided from trusted facts, never from the message body.**

A chat message is attacker-controlled input. Anything it *claims* — its sender id,
its role, its group — is only as trustworthy as the transport that carried it.
So identity comes from the adapter's authenticated channel, roles come from the
operator's config, and the message text is only ever data.
"""

from soapbot.security.audit import AuditEvent, AuditLog, get_audit_log
from soapbot.security.injection import (
    looks_like_injection,
    redact,
    vet_memory,
    wrap_untrusted,
)
from soapbot.security.principal import (
    PERMISSION_MIN_ROLE,
    Permission,
    Principal,
    PrincipalResolver,
    Role,
)
from soapbot.security.ratelimit import SlidingWindowLimiter

__all__ = [
    "PERMISSION_MIN_ROLE",
    "AuditEvent",
    "AuditLog",
    "Permission",
    "Principal",
    "PrincipalResolver",
    "Role",
    "SlidingWindowLimiter",
    "get_audit_log",
    "looks_like_injection",
    "redact",
    "vet_memory",
    "wrap_untrusted",
]
