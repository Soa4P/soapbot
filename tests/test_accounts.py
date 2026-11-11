"""Accounts, invites and memberships.

The properties that matter are the ones an attacker would try to break: a second
owner, a reused invite, a plaintext password or code on disk, and a member reading a
session nobody granted. Each has a test that fails loudly rather than a comment that
asks nicely.
"""

from __future__ import annotations

import pytest
from sqlalchemy import select

from soapbot.accounts import (
    authenticate,
    count_accounts,
    create_invite,
    create_owner,
    grant_membership,
    has_access,
    list_memberships,
    redeem_invite,
)
from soapbot.accounts.service import AccountError
from soapbot.memory.db import AccountInviteRow, AccountRow, Database


@pytest.fixture
async def db(tmp_path):
    database = Database(f"sqlite+aiosqlite:///{tmp_path / 'accounts.db'}")
    await database.init()
    try:
        yield database
    finally:
        await database.close()


async def test_first_owner_is_the_only_owner(db) -> None:
    owner = await create_owner(db, username="alice", password="correct horse battery")
    assert owner.role == "owner"
    assert await count_accounts(db) == 1
    with pytest.raises(AccountError, match="已有账号"):
        await create_owner(db, username="bob", password="another long password")


async def test_password_is_never_stored_in_plaintext(db) -> None:
    await create_owner(db, username="alice", password="correct horse battery")
    async with db.session_factory()() as session:
        row = (await session.execute(select(AccountRow))).scalar_one()
    assert row.password_hash != "correct horse battery"
    assert row.salt and len(row.salt) == 32
    assert len(row.password_hash) == 64


async def test_login_accepts_the_right_password_and_nothing_else(db) -> None:
    await create_owner(db, username="alice", password="correct horse battery")
    assert await authenticate(db, username="alice", password="correct horse battery") is not None
    assert await authenticate(db, username="alice", password="wrong password") is None
    # Unknown user and wrong password are indistinguishable to the caller.
    assert await authenticate(db, username="nobody", password="correct horse battery") is None


async def test_disabled_account_cannot_log_in(db) -> None:
    owner = await create_owner(db, username="alice", password="correct horse battery")
    async with db.write() as session:
        await session.execute(
            AccountRow.__table__.update().where(AccountRow.id == owner.id).values(status="disabled")
        )
    assert await authenticate(db, username="alice", password="correct horse battery") is None


async def test_short_password_is_rejected_before_hashing(db) -> None:
    with pytest.raises(AccountError, match="至少"):
        await create_owner(db, username="alice", password="short")


@pytest.mark.parametrize("name", ["ab", "has space", "中文名字", "x" * 33])
async def test_usernames_are_restricted(db, name: str) -> None:
    with pytest.raises(AccountError):
        await create_owner(db, username=name, password="correct horse battery")


async def test_invite_is_stored_only_as_a_hash(db) -> None:
    owner = await create_owner(db, username="alice", password="correct horse battery")
    code = await create_invite(db, created_by=owner.id, session_keys=("qq:group:1",))
    async with db.session_factory()() as session:
        row = (await session.execute(select(AccountInviteRow))).scalar_one()
    assert row.code_hash != code
    assert len(row.code_hash) == 64
    assert code not in row.code_hash


async def test_redeeming_an_invite_grants_the_listed_sessions(db) -> None:
    owner = await create_owner(db, username="alice", password="correct horse battery")
    code = await create_invite(
        db, created_by=owner.id, session_keys=("qq:group:1", "qq:group:2")
    )
    member = await redeem_invite(
        db, code=code, username="bob", password="correct horse battery"
    )
    assert member.role == "member"
    assert await list_memberships(db, member.id) == ["qq:group:1", "qq:group:2"]


async def test_an_invite_cannot_be_used_twice_by_default(db) -> None:
    owner = await create_owner(db, username="alice", password="correct horse battery")
    code = await create_invite(db, created_by=owner.id)
    await redeem_invite(db, code=code, username="bob", password="correct horse battery")
    with pytest.raises(AccountError, match="用完"):
        await redeem_invite(db, code=code, username="carol", password="correct horse battery")


async def test_an_expired_invite_is_refused(db) -> None:
    owner = await create_owner(db, username="alice", password="correct horse battery")
    code = await create_invite(db, created_by=owner.id, hours=1)
    async with db.write() as session:
        await session.execute(
            AccountInviteRow.__table__.update().values(expires_at=1.0)
        )
    with pytest.raises(AccountError, match="过期"):
        await redeem_invite(db, code=code, username="bob", password="correct horse battery")


async def test_membership_is_the_only_thing_that_grants_access(db) -> None:
    owner = await create_owner(db, username="alice", password="correct horse battery")
    code = await create_invite(db, created_by=owner.id)
    member = await redeem_invite(
        db, code=code, username="bob", password="correct horse battery"
    )

    assert not await has_access(db, member, "qq:group:1")
    assert await has_access(db, owner, "qq:group:1"), "owner bypasses membership by design"

    await grant_membership(db, account_id=member.id, session_key="qq:group:1", created_by=owner.id)
    await grant_membership(db, account_id=member.id, session_key="qq:group:1", created_by=owner.id)
    assert await list_memberships(db, member.id) == ["qq:group:1"]
    assert await has_access(db, member, "qq:group:1")


async def test_invite_rejects_an_unknown_code(db) -> None:
    with pytest.raises(AccountError, match="无效"):
        await redeem_invite(
            db, code="not-a-real-code", username="bob", password="correct horse battery"
        )
