"""Principals, roles and permissions.

Why this module exists
----------------------
The original access control was a single group allow-list. That is enough to
decide *"should the bot talk here at all"*, but not *"may this particular person
read the knowledge base / delete another group's memory / approve a payment"*.

Concretely, before this module:

* ``/forget <id>`` deleted **any** memory row by primary key, from **any** group.
  A random member of group A could destroy group B's data by walking integers.
* ``/kb`` dumped every uploaded document title, and ``/kb <q>`` ran retrieval over
  operator-only material.
* ``/timeline`` returned the whole group archive to whoever asked.
* Private messages were always treated as "woken", so any stranger could DM the
  bot and get the full persona + memory + RAG pipeline for free.

The rule enforced here
----------------------
    identity  <- the adapter's authenticated channel (never the message body)
    role      <- operator configuration (never the message body)
    action    <- must hold an explicit permission

``Sender.role`` arrives inside the OneBot/QQ payload. It is *claimed* by the
transport, not proven by it, so it is **not** trusted by default
(``trust_protocol_roles=False``). A compromised protocol implementation — or a
reverse-WS endpoint that accepts anyone — can put ``role="owner"`` in a payload.
Config-derived authority is the only durable source of truth.
"""

from __future__ import annotations

import logging
import re
import unicodedata
from dataclasses import dataclass, field
from enum import StrEnum

logger = logging.getLogger(__name__)


class Role(StrEnum):
    """Ordered authority levels. ``rank`` gives the comparison order."""

    ANONYMOUS = "anonymous"
    """Not identified / not allowed to do anything."""

    GUEST = "guest"
    """Identified but unprivileged: may chat, nothing else."""

    MEMBER = "member"
    """Normal participant: chat + their own memory."""

    ADMIN = "admin"
    """Bot administrator, configured by the operator.

    Note: this is *bot* admin, deliberately distinct from a QQ group admin. A QQ
    group admin losing their group rights must not silently keep bot privileges,
    and vice versa.
    """

    OWNER = "owner"
    """The operator. Only role that may touch money, keys and access control."""

    @property
    def rank(self) -> int:
        return _ROLE_RANK[self]


_ROLE_RANK: dict[Role, int] = {
    Role.ANONYMOUS: 0,
    Role.GUEST: 1,
    Role.MEMBER: 2,
    Role.ADMIN: 3,
    Role.OWNER: 4,
}


class Permission(StrEnum):
    """Capabilities that can be required. Deny-by-default if unlisted."""

    CHAT = "chat"
    """Talk to the model at all."""

    USE_COMMAND = "command"
    """Invoke any slash command (a stricter command may require more)."""

    RECALL_OWN = "recall_own"
    """Search memories scoped to the caller's own conversation."""

    RECALL_ANY = "recall_any"
    """Search memories across scopes (admin/diagnostic)."""

    VIEW_TIMELINE = "timeline"
    """Read the archived conversation of the current session."""

    MANAGE_MEMORY = "manage_memory"
    """Delete or edit memories **within the caller's own scope**."""

    MANAGE_MEMORY_ANY = "manage_memory_any"
    """Delete or edit memories in *any* scope.

    Deliberately separate from ``RECALL_ANY``. Reading is not writing: an admin
    who may search across groups for diagnostics must not thereby be able to
    destroy another group's data. Reusing one permission for both is how a
    read-only diagnostic grant silently becomes a destructive one.
    """

    READ_KNOWLEDGE = "knowledge_read"
    """Query the operator's knowledge base."""

    MANAGE_KNOWLEDGE = "knowledge_manage"
    """Upload or delete knowledge documents."""

    MANAGE_CONFIG = "config"
    """Change personas, providers, adapters, access control."""

    MODERATE_GROUP = "moderate_group"
    """Mute, kick or recall messages through the bot.

    Separate from ``MANAGE_CONFIG`` because the two answer different questions and
    one implies far more reach than the other. ``MODERATE_GROUP`` makes the bot act
    *on people* in a group it is already in; config access changes what the bot is.
    Folding moderation into config would mean every deployment that lets a
    moderator clean up spam also hands that moderator the provider API keys. The
    floor is ADMIN because an action taken here is visible to the group and
    attributed to the bot's owner, not to the person who typed the command.
    """

    APPROVE_PAYMENT = "approve_payment"
    """Approve a spending request. Owner-only by policy."""

    MANAGE_MCP = "mcp_manage"
    """Add, edit or remove an external tool server.

    One rank above ``MANAGE_CONFIG``, and not because of secrets. An MCP entry is an
    argv that the host will execute as a child process on every start, whose tools the
    model may then call with the user's message as input. That is a different kind of
    act from editing a provider's base URL, so it belongs to the owner — the role that
    already approves payments.
    """

    VIEW_AUDIT = "view_audit"


PERMISSION_MIN_ROLE: dict[Permission, Role] = {
    Permission.CHAT: Role.MEMBER,
    Permission.USE_COMMAND: Role.GUEST,
    Permission.RECALL_OWN: Role.MEMBER,
    Permission.RECALL_ANY: Role.ADMIN,
    Permission.VIEW_TIMELINE: Role.GUEST,
    Permission.MANAGE_MEMORY: Role.ADMIN,
    Permission.MANAGE_MEMORY_ANY: Role.OWNER,
    Permission.READ_KNOWLEDGE: Role.ADMIN,
    Permission.MANAGE_KNOWLEDGE: Role.ADMIN,
    Permission.MANAGE_CONFIG: Role.ADMIN,
    Permission.MODERATE_GROUP: Role.ADMIN,
    Permission.APPROVE_PAYMENT: Role.OWNER,
    Permission.MANAGE_MCP: Role.OWNER,
    Permission.VIEW_AUDIT: Role.ADMIN,
}

_ID_SAFE_RE = re.compile(r"^[a-z0-9_:\-]{1,64}$")


def normalize_id(raw: object) -> str:
    """Canonicalise an account/group identifier for allow-list comparison.

    Attack this closes: allow-lists are compared as strings, so an identifier that
    differs only in *presentation* must not be treated as a different identity.
    ``" 20001"``, ``"\\u200b20001"``, ``"２０００１"`` (full-width) and ``"+20001"``
    all denote the same QQ number, and each is a plausible way to slip past a naive
    ``in`` check if only one side is normalised.

    Unrecognised shapes are returned lower-cased rather than rejected, so an
    unexpected id simply fails to match the allow-list (fail-closed) instead of
    raising inside the hot path.
    """
    if raw is None:
        return ""
    text = unicodedata.normalize("NFKC", str(raw))
    # Zero-width and bidi controls survive NFKC; strip them explicitly.
    text = text.translate(_ZW_MAP)
    text = text.strip().strip("\"'")
    text = text.replace("\u3000", " ")
    text = "".join(text.split())
    if text.startswith("+"):
        text = text[1:]
    if not text:
        return ""
    if text.isdigit():
        # Drop leading zeros: "007" and "7" are the same account number.
        return str(int(text))
    return text.lower()


_ZW_MAP = dict.fromkeys(
    map(ord, "\u200b\u200c\u200d\u200e\u200f\u202a\u202b\u202c\u202d\u202e\ufeff"), None
)


@dataclass(slots=True)
class Principal:
    """A resolved actor: who is asking, and what they are allowed to do."""

    user_id: str = ""
    display_name: str = ""
    scene: str = ""
    group_id: str = ""
    role: Role = Role.ANONYMOUS
    adapter: str = ""
    authenticated: bool = False
    """True only when the transport proved this identity (signed/token-authed)."""

    granted: frozenset[Permission] = field(default_factory=frozenset)
    source: str = ""
    """How the role was decided: config / protocol / default. For audit trails."""

    def can(self, permission: Permission) -> bool:
        """Permission check. Two independent gates must both pass."""
        if not self.authenticated:
            return False
        if permission in self.granted:
            return True
        required = PERMISSION_MIN_ROLE.get(permission, Role.OWNER)
        return self.role.rank >= required.rank

    @property
    def session_key(self) -> str:
        """The principal's own conversation scope.

        Mirrors ``IncomingMessage.session_key`` so scope-ownership checks compare
        like with like. Kept as a property (not a stored field) so it cannot drift
        from ``scene`` / ``group_id`` / ``user_id``.
        """
        if not self.adapter:
            return ""
        if self.scene == "group":
            return f"{self.adapter}:group:{self.group_id}"
        if self.scene == "private":
            return f"{self.adapter}:private:{self.user_id}"
        return ""

    def require(self, permission: Permission) -> None:
        if not self.can(permission):
            raise PermissionDeniedError(permission, self)

    @property
    def is_privileged(self) -> bool:
        return self.role.rank >= Role.ADMIN.rank


class PermissionDeniedError(Exception):
    """Raised (or converted to a user-facing refusal) when a check fails."""

    def __init__(self, permission: Permission, principal: Principal) -> None:
        self.permission = permission
        self.principal = principal
        super().__init__(
            f"permission {permission} denied for user={principal.user_id or '?'} "
            f"role={principal.role} source={principal.source}"
        )


@dataclass(slots=True)
class AuthorityConfig:
    """Operator-owned authority lists.

    Populated from config/env only. Nothing here may be derived from a chat
    message: that is exactly the escalation path this type exists to prevent.
    """

    owners: set[str] = field(default_factory=set)
    admins: set[str] = field(default_factory=set)
    members: set[str] = field(default_factory=set)
    """Explicitly privileged beyond guest. Optional; usually empty."""

    trust_protocol_roles: bool = False
    """If True, a protocol-asserted owner/admin role is honoured.

    Off by default: the role field is attacker-influenced whenever the transport
    is unauthenticated (e.g. a reverse WebSocket that accepts any client).
    """

    default_role: Role = Role.MEMBER
    """Role for an identified user who is on no list.

    Deliberately ``MEMBER``, not ``GUEST``: a bot that cannot answer anyone until
    an operator hand-registers every participant is not a product. The split is
    by *risk*, not by identity —

      * low-risk (chat, own-scope recall)  -> open to any identified participant
      * high-risk (knowledge base, memory
        deletion, config, spending)        -> config-gated, deny by default

    That keeps the bot usable out of the box while ensuring every dangerous
    capability still requires an explicit operator grant.
    """

    def role_for(self, user_id: str) -> tuple[Role, str]:
        uid = normalize_id(user_id)
        if not uid:
            return Role.ANONYMOUS, "no_id"
        if uid in self.owners:
            return Role.OWNER, "config:owner"
        if uid in self.admins:
            return Role.ADMIN, "config:admin"
        if uid in self.members:
            return Role.MEMBER, "config:member"
        return self.default_role, f"default:{self.default_role}"


class PrincipalResolver:
    """Builds a :class:`Principal` from an inbound event."""

    def __init__(self, authority: AuthorityConfig | None = None) -> None:
        self.authority = authority or AuthorityConfig()

    def resolve(self, event, *, authenticated: bool = True) -> Principal:
        user_id = normalize_id(getattr(event.sender, "user_id", ""))
        scene = str(getattr(event.scene, "value", getattr(event, "scene", "")))
        group_id = normalize_id(getattr(event, "group_id", "") or "")

        role, source = self.authority.role_for(user_id)

        claimed = str(getattr(event.sender, "role", "") or "").lower()
        if (
            self.authority.trust_protocol_roles
            and role.rank < Role.ADMIN.rank
            and claimed in ("owner", "admin")
        ):
            role, source = Role.ADMIN, f"protocol:{claimed}"

        granted: set[Permission] = set()
        if role.rank >= Role.MEMBER.rank:
            granted.update({Permission.CHAT, Permission.RECALL_OWN})
        if role.rank >= Role.ADMIN.rank:
            granted.update(
                {
                    Permission.RECALL_ANY,
                    Permission.MANAGE_MEMORY,
                    Permission.READ_KNOWLEDGE,
                    Permission.MANAGE_KNOWLEDGE,
                    Permission.MANAGE_CONFIG,
                    Permission.VIEW_AUDIT,
                }
            )
        if role is Role.OWNER:
            granted.add(Permission.APPROVE_PAYMENT)
            granted.add(Permission.MANAGE_MEMORY_ANY)

        return Principal(
            user_id=user_id,
            display_name=str(getattr(event.sender, "display_name", "") or user_id),
            scene=scene,
            group_id=group_id,
            role=role,
            adapter=str(getattr(event, "adapter", "") or ""),
            authenticated=authenticated,
            granted=frozenset(granted),
            source=source,
        )

    # -- helpers used by tests and the WebUI ---------------------------------
    def grant_admin(self, user_id: str) -> None:
        self.authority.admins.add(normalize_id(user_id))

    def grant_owner(self, user_id: str) -> None:
        self.authority.owners.add(normalize_id(user_id))

    def revoke(self, user_id: str) -> None:
        uid = normalize_id(user_id)
        self.authority.owners.discard(uid)
        self.authority.admins.discard(uid)
        self.authority.members.discard(uid)
