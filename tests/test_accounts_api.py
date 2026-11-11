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
from pydantic import SecretStr

from soapbot.accounts import create_invite, create_owner, redeem_invite
from soapbot.api.accounts import router as accounts_router
from soapbot.api.auth import require_api_auth
from soapbot.memory.db import AccountRow, Database


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


async def test_disabling_an_account_ends_the_session_it_already_started(env) -> None:
    """``authenticate`` refusing a disabled account only blocks the *next* login.

    The cookie issued before the flip keeps working until it expires, so without this
    check "disable" would mean "no new logins" while the incumbent reads on.
    """
    env.current.update({"subject": str(env.member.id), "role": env.member.role})
    assert (await env.client.get("/api/accounts/me")).status_code == 200

    async with env.database.write() as session:
        await session.execute(
            AccountRow.__table__.update()
            .where(AccountRow.id == env.member.id)
            .values(status="disabled")
        )

    assert (await env.client.get("/api/accounts/me")).status_code == 401


# ============================================================ the documented setup flow

def test_the_documented_curl_bootstrap_flow_actually_works(tmp_path, monkeypatch) -> None:
    """``docs/public-user-guide.md`` tells the operator to curl ``/api/accounts/owner``.

    That example is a claim about the whole dependency stack: the bootstrap token must
    authenticate, satisfy the ADMIN floor, pass ``require_credential``, find a live
    database behind the runtime, and leave an account behind — none of which the
    router-level tests above exercise, because they override ``require_api_auth`` and
    hand the routes a bare ``FastAPI()``. A doc example that 503s or 401s is worse than
    no example, so this one is copy-pasted from the doc verbatim.
    """
    from fastapi.testclient import TestClient

    from soapbot.app import create_app
    from soapbot.config import settings as live_settings

    config_dir = tmp_path / "cfg"
    config_dir.mkdir(parents=True, exist_ok=True)
    (config_dir / "providers.yaml").write_text("providers: []\n", encoding="utf-8")
    (config_dir / "adapters.yaml").write_text("adapters: []\n", encoding="utf-8")
    data_dir = tmp_path / "data"
    data_dir.mkdir(parents=True, exist_ok=True)

    monkeypatch.setattr(live_settings, "enable_runtime", True)
    monkeypatch.setattr(live_settings, "config_dir", config_dir)
    monkeypatch.setattr(live_settings, "data_dir", data_dir)
    monkeypatch.setattr(live_settings, "init_token", SecretStr("bootstrap-doc"))

    with TestClient(create_app()) as client:
        login = client.post("/api/auth/login", json={"init_token": "bootstrap-doc"})
        assert login.status_code == 200
        operator = {"Authorization": f"Bearer {login.json()['access_token']}"}

        # The bootstrap credential can create the first account...
        created = client.post(
            "/api/accounts/owner",
            json={"username": "owner", "password": "correct horse battery"},
            headers=operator,
        )
        assert created.status_code == 200, created.text

        # ...and cannot do it twice, so the endpoint is not a public signup.
        again = client.post(
            "/api/accounts/owner",
            json={"username": "intruder", "password": "correct horse battery"},
            headers=operator,
        )
        assert again.status_code == 409

        # The account signs in through its own route and reads the archive with its own
        # token; the bootstrap token is not an archive key.
        signed = client.post(
            "/api/accounts/login", json={"username": "owner", "password": "correct horse battery"}
        )
        assert signed.status_code == 200
        account_header = {"Authorization": f"Bearer {signed.json()['access_token']}"}
        assert client.get("/api/chat/sessions", headers=account_header).status_code == 200
        assert client.get("/api/chat/sessions", headers=operator).status_code == 401
