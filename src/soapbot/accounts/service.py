"""Accounts, invites and per-session membership.

Threat model in one paragraph: the archive contains every message the bot has seen,
including private chats. A logged-in account must therefore not be enough to read
*everything* — membership is the authorization unit, and absence of a row is denial.
The owner is the only role that bypasses membership, which is why creating an owner
is a one-time operation guarded by an existing admin credential.

Passwords use ``hashlib.scrypt`` because it is in the standard library: adding
argon2 would be a new dependency for a property (memory-hard hashing) that scrypt
already provides. Invite codes are stored only as SHA-256 hashes, so a database copy
does not hand out working invitations.
"""

from __future__ import annotations

import hashlib
import hmac
import re
import secrets
import time
from dataclasses import dataclass
from typing import Any

from sqlalchemy import func, select
from sqlalchemy.exc import IntegrityError

from soapbot.memory.db import (
    AccountInviteRow,
    AccountRow,
    ChatMembershipRow,
    Database,
)

_SCRYPT_N = 2**14
_SCRYPT_R = 8
_SCRYPT_P = 1
_DKLEN = 32
_USERNAME_RE = re.compile(r"^[A-Za-z0-9_.-]{3,32}$")
MIN_PASSWORD_LENGTH = 8


class AccountError(Exception):
    """A rejected account operation, with a message safe to show the caller."""

    @property
    def message(self) -> str:
        """The authored text, never a stringified exception.

        The API layer returns this verbatim. Going through ``str(exc)`` reads the same
        today but invites the next edit to raise ``AccountError(repr(some_exc))``, which
        is how stack details end up in a response body.
        """
        return self.args[0] if self.args else "account operation rejected"


@dataclass(slots=True)
class Account:
    id: int
    username: str
    role: str
    status: str

    @property
    def is_owner(self) -> bool:
        return self.role == "owner"


# --------------------------------------------------------------------- passwords
def hash_password(password: str, *, salt: str | None = None) -> tuple[str, str]:
    """Return ``(salt_hex, hash_hex)``. A fresh salt unless one is supplied."""
    if len(password) < MIN_PASSWORD_LENGTH:
        raise AccountError(f"密码至少 {MIN_PASSWORD_LENGTH} 个字符")
    salt_bytes = bytes.fromhex(salt) if salt else secrets.token_bytes(16)
    digest = hashlib.scrypt(
        password.encode("utf-8"),
        salt=salt_bytes,
        n=_SCRYPT_N,
        r=_SCRYPT_R,
        p=_SCRYPT_P,
        dklen=_DKLEN,
    )
    return salt_bytes.hex(), digest.hex()


def verify_password(password: str, salt_hex: str, expected_hex: str) -> bool:
    if not salt_hex or not expected_hex:
        return False
    try:
        salt = bytes.fromhex(salt_hex)
    except ValueError:
        return False
    digest = hashlib.scrypt(
        password.encode("utf-8"),
        salt=salt,
        n=_SCRYPT_N,
        r=_SCRYPT_R,
        p=_SCRYPT_P,
        dklen=_DKLEN,
    )
    return hmac.compare_digest(digest.hex(), expected_hex)


def _check_username(username: str) -> str:
    name = username.strip()
    if not _USERNAME_RE.match(name):
        raise AccountError("用户名需为 3–32 位字母、数字、下划线、点或短横线")
    return name


def _to_account(row: AccountRow) -> Account:
    return Account(id=row.id, username=row.username, role=row.role, status=row.status)


# --------------------------------------------------------------------- accounts
async def count_accounts(db: Database) -> int:
    async with db.session_factory()() as session:
        return int((await session.execute(select(func.count(AccountRow.id)))).scalar() or 0)


async def create_owner(db: Database, *, username: str, password: str) -> Account:
    """Create the first owner. Refuses once any account exists.

    The guard is in the service, not only in the route: an account table with two
    owners would mean two people who bypass membership, which is the one thing this
    design must not allow by accident.
    """
    name = _check_username(username)
    salt, digest = hash_password(password)
    async with db.write() as session:
        # Counted inside the write transaction, not before it: the check and the insert
        # must be one critical section, or two bootstraps racing each other both read
        # zero and both succeed. ``Database.write`` serialises writers, so the second
        # request now sees the first row and is refused.
        existing = (await session.execute(select(func.count(AccountRow.id)))).scalar() or 0
        if existing > 0:
            raise AccountError("仓库已有账号，不能再创建所有者")
        row = AccountRow(
            username=name,
            password_hash=digest,
            salt=salt,
            role="owner",
            status="active",
            created_at=time.time(),
            created_by=0,
        )
        session.add(row)
        await session.flush()
        return _to_account(row)


async def authenticate(db: Database, *, username: str, password: str) -> Account | None:
    async with db.session_factory()() as session:
        row = (
            await session.execute(select(AccountRow).where(AccountRow.username == username.strip()))
        ).scalar_one_or_none()
        if row is None or row.status != "active":
            return None
        if not verify_password(password, row.salt, row.password_hash):
            return None
        account = _to_account(row)
    async with db.write() as session:
        await session.execute(
            AccountRow.__table__.update()
            .where(AccountRow.id == account.id)
            .values(last_login_at=time.time())
        )
    return account


async def list_accounts(db: Database) -> list[Account]:
    async with db.session_factory()() as session:
        rows = (
            (
                await session.execute(
                    select(AccountRow).order_by(AccountRow.created_at.asc())
                )
            )
            .scalars()
            .all()
        )
        return [_to_account(row) for row in rows]


# --------------------------------------------------------------------- invites
def _invite_hash(code: str) -> str:
    return hashlib.sha256(code.encode("utf-8")).hexdigest()


async def create_invite(
    db: Database,
    *,
    created_by: int,
    role: str = "member",
    hours: int = 72,
    max_uses: int = 1,
    session_keys: tuple[str, ...] = (),
) -> str:
    """Return the plaintext code exactly once; only its hash is stored."""
    if role not in ("member", "owner"):
        raise AccountError("邀请角色只能是 member 或 owner")
    if max_uses < 1:
        raise AccountError("邀请至少要有 1 次可用次数")
    code = secrets.token_urlsafe(24)
    async with db.write() as session:
        session.add(
            AccountInviteRow(
                code_hash=_invite_hash(code),
                role=role,
                expires_at=time.time() + max(1, hours) * 3600,
                max_uses=max_uses,
                used=0,
                created_by=created_by,
                created_at=time.time(),
                session_keys=",".join(k.strip() for k in session_keys if k.strip()),
            )
        )
    return code


async def redeem_invite(
    db: Database, *, code: str, username: str, password: str
) -> Account:
    name = _check_username(username)
    salt, digest = hash_password(password)
    now = time.time()
    async with db.write() as session:
        invite = (
            await session.execute(
                select(AccountInviteRow).where(AccountInviteRow.code_hash == _invite_hash(code))
            )
        ).scalar_one_or_none()
        if invite is None:
            raise AccountError("邀请码无效")
        if invite.expires_at and invite.expires_at < now:
            raise AccountError("邀请码已过期")
        if invite.used >= invite.max_uses:
            raise AccountError("邀请码已用完")
        existing = (
            await session.execute(select(AccountRow).where(AccountRow.username == name))
        ).scalar_one_or_none()
        if existing is not None:
            raise AccountError("用户名已被占用")

        row = AccountRow(
            username=name,
            password_hash=digest,
            salt=salt,
            role="owner" if invite.role == "owner" else "member",
            status="active",
            created_at=now,
            created_by=invite.created_by,
        )
        session.add(row)
        await session.flush()
        invite.used += 1
        for key in (invite.session_keys or "").split(","):
            key = key.strip()
            if key:
                session.add(
                    ChatMembershipRow(
                        account_id=row.id,
                        session_key=key,
                        created_by=invite.created_by,
                        created_at=now,
                    )
                )
        return _to_account(row)


# --------------------------------------------------------------------- memberships
async def list_memberships(db: Database, account_id: int) -> list[str]:
    async with db.session_factory()() as session:
        rows = (
            (
                await session.execute(
                    select(ChatMembershipRow.session_key)
                    .where(ChatMembershipRow.account_id == account_id)
                    .order_by(ChatMembershipRow.session_key)
                )
            )
            .scalars()
            .all()
        )
        return [str(key) for key in rows]


async def has_access(db: Database, account: Account, session_key: str) -> bool:
    if account.is_owner:
        return True
    async with db.session_factory()() as session:
        row = (
            await session.execute(
                select(ChatMembershipRow.id).where(
                    ChatMembershipRow.account_id == account.id,
                    ChatMembershipRow.session_key == session_key,
                )
            )
        ).scalar_one_or_none()
        return row is not None


async def grant_membership(
    db: Database, *, account_id: int, session_key: str, created_by: int
) -> None:
    key = session_key.strip()
    if not key:
        raise AccountError("session_key 不能为空")
    async with db.write() as session:
        existing = (
            await session.execute(
                select(ChatMembershipRow.id).where(
                    ChatMembershipRow.account_id == account_id,
                    ChatMembershipRow.session_key == key,
                )
            )
        ).scalar_one_or_none()
        if existing is not None:
            return
        try:
            session.add(
                ChatMembershipRow(
                    account_id=account_id,
                    session_key=key,
                    created_by=created_by,
                    created_at=time.time(),
                )
            )
            await session.flush()
        except IntegrityError:
            # The read above and this insert are not atomic; the unique index is the
            # real guard. Granting twice stays a no-op instead of a 500.
            await session.rollback()


async def account_by_id(db: Database, account_id: int) -> Account | None:
    async with db.session_factory()() as session:
        row = (
            await session.execute(select(AccountRow).where(AccountRow.id == account_id))
        ).scalar_one_or_none()
        return _to_account(row) if row is not None else None


async def account_from_claims(db: Database, auth: dict[str, Any]) -> Account | None:
    """Resolve the token subject to an account.

    Subjects are numeric ids for password logins. The bootstrap token uses
    ``operator`` and has no account row; it is treated as the owner so the operator
    can create the first account, then it stops being useful for chat reads.
    """
    subject = str(auth.get("subject") or "")
    if subject == "operator" and str(auth.get("role")) in ("owner", "admin"):
        return Account(id=0, username="operator", role="owner", status="active")
    try:
        account_id = int(subject)
    except (TypeError, ValueError):
        return None
    return await account_by_id(db, account_id)


async def active_account_from_claims(db: Database, auth: dict[str, Any]) -> Account | None:
    """Like :func:`account_from_claims`, but a disabled account is not a principal.

    ``authenticate`` already refuses to *issue* a cookie for a disabled account. That is
    only half the job: a cookie issued before the account was disabled stays valid until
    it expires, so the session it started would keep reading archived conversations —
    "disable" would mean "no new logins" while the incumbent keeps reading. Every route
    that turns a claim into an identity goes through here for that reason.
    """
    account = await account_from_claims(db, auth)
    if account is None or account.status != "active":
        return None
    return account
