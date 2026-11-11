"""The account endpoints, exercised over HTTP rather than through the service layer.

``tests/test_accounts.py`` proves the rules (one owner, hashed invites, membership is the
only grant). This file proves the *routes* obey them: a status code and a body are what
an operator meets, and the dependency stack — role floors, the credential requirement,
the cross-site check — lives only at this level. Testing the service directly would pass
even if the route were mounted without ``require_role``.
"""

from __future__ import annotations

from types import SimpleNamespace

import httpx
import pytest
from fastapi import FastAPI

from soapbot.accounts import create_invite, create_owner, redeem_invite
from soapbot.api.accounts import router as accounts_router
from soapbot.api.auth import require_api_auth
from soapbot.memory.db import Database


@pytest.fixture
async def env(tmp_path, monkeypatch):
    database = Database(f"sqlite+aiosqlite:///{tmp_path / 'accounts-api.db'}")
    await database.init()
    memory = SimpleNamespace(db=database)
    runtime = SimpleNamespace(memory=memory)
    monkeypatch.setattr("soapbot.app.get_runtime", lambda: runtime)

    owner = await create_owner(database, username="alice", password="correct horse battery")
    code = await create_invite(database, created_by=owner.id, session_keys=("qq:group:1",))
    member = await redeem_invite(
        database, code=code, username="bob", password="correct horse battery"
    )

    app = FastAPI()
    app.include_router(accounts_router)
    current = {"subject": str(owner.id), "role": owner.role, "mode": "token"}

    async def fake_auth() -> dict[str, str]:
        # ``mode`` is what ``require_credential`` inspects: a token-backed call may
        # change state, a loopback read may not.
        return dict(current)

    app.dependency_overrides[require_api_auth] = fake_auth
    transport = httpx.ASGITransport(app=app)
    async with httpx.AsyncClient(transport=transport, base_url="http://test") as client:
        yield SimpleNamespace(
            client=client,
            current=current,
            owner=owner,
            member=member,
            database=database,
        )
    await database.close()


async def test_creating_a_second_owner_is_a_409_with_the_authored_reason(env) -> None:
    response = await env.client.post(
        "/api/accounts/owner", json={"username": "bob", "password": "another long password"}
    )
    assert response.status_code == 409
    # The body is the service's own sentence, not a traceback or a generic "conflict".
    assert "已有账号" in response.json()["detail"]


async def test_registering_with_an_unknown_invite_is_a_400(env) -> None:
    response = await env.client.post(
        "/api/accounts/register",
        json={
            "invite": "not-a-real-invite-code",
            "username": "carol",
            "password": "correct horse battery",
        },
    )
    assert response.status_code == 400
    assert response.json()["detail"] == "邀请码无效"


async def test_a_member_cannot_list_accounts(env) -> None:
    env.current.update({"subject": str(env.member.id), "role": env.member.role})
    response = await env.client.get("/api/accounts")
    assert response.status_code == 403


async def test_a_member_cannot_mint_an_invite(env) -> None:
    env.current.update({"subject": str(env.member.id), "role": env.member.role})
    response = await env.client.post("/api/accounts/invites", json={"role": "member"})
    assert response.status_code == 403


async def test_a_caller_without_a_credential_cannot_mint_an_invite(env) -> None:
    """Loopback reads are allowed; minting a code that grants archive access is not."""
    env.current.pop("mode")
    response = await env.client.post("/api/accounts/invites", json={"role": "member"})
    assert response.status_code == 401


async def test_me_reports_the_account_and_only_its_granted_sessions(env) -> None:
    env.current.update({"subject": str(env.member.id), "role": env.member.role})
    body = (await env.client.get("/api/accounts/me")).json()
    assert body["username"] == "bob"
    assert body["role"] == "member"
    assert body["sessions"] == ["qq:group:1"]


async def test_me_refuses_a_token_whose_account_was_removed(env) -> None:
    env.current["subject"] = "9999"
    response = await env.client.get("/api/accounts/me")
    assert response.status_code == 401
