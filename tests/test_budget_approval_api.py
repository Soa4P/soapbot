"""The panel's approve/deny endpoints: authority, scope, replay, and the shared bus.

The ledger already had a state machine; what was missing was a way to *reach* it
without typing a slash command into a QQ group. These tests pin the two things a
new entry point can get wrong: letting a loopback read decide, and publishing a
different event shape than the command path does.
"""

from __future__ import annotations

from types import SimpleNamespace

import httpx
import pytest
from fastapi import FastAPI

from soapbot.api.admin import router as admin_router
from soapbot.api.auth import require_api_auth
from soapbot.budget.events import APPROVAL_BUS, APPROVED, DENIED, ApprovalEvent
from soapbot.budget.policy import BudgetPolicy
from soapbot.budget.store import BudgetStore
from soapbot.memory.db import Database
from soapbot.security.audit import AuditLog

SCOPE = "onebot11:group:100"


@pytest.fixture(autouse=True)
def _clear_bus():
    APPROVAL_BUS.clear()
    yield
    APPROVAL_BUS.clear()


@pytest.fixture
async def env(tmp_path, monkeypatch):
    database = Database(f"sqlite+aiosqlite:///{tmp_path / 'approval-api.db'}")
    await database.init()
    store = BudgetStore(
        database,
        BudgetPolicy(period_cap_minor=10_000, per_request_cap_minor=5_000),
        audit=AuditLog(),
    )
    runtime = SimpleNamespace(budget=store)
    monkeypatch.setattr("soapbot.app.get_runtime", lambda: runtime)

    app = FastAPI()
    app.include_router(admin_router)
    current = {"subject": "owner-1", "role": "owner", "mode": "token"}

    async def fake_auth() -> dict:
        return dict(current)

    app.dependency_overrides[require_api_auth] = fake_auth
    transport = httpx.ASGITransport(app=app)
    async with httpx.AsyncClient(transport=transport, base_url="http://test") as client:
        yield SimpleNamespace(
            client=client,
            current=current,
            store=store,
            runtime=runtime,
        )
    await database.close()


async def _request(env, *, requester_id: str = "qq-1", purpose: str = "materials") -> int:
    req, created = await env.store.create(
        session_key=SCOPE,
        requester_id=requester_id,
        requester_name=requester_id,
        amount_minor=1250,
        purpose=purpose,
        trace_id="t-1",
    )
    assert created is True
    return req.id


def _body(session_key: str = SCOPE, note: str = "") -> dict:
    return {"session_key": session_key, "note": note}


# ------------------------------------------------------------------ authority


async def test_a_member_cannot_decide(env) -> None:
    env.current["role"] = "member"
    response = await env.client.post("/api/budget/1/approve", json=_body())
    assert response.status_code == 403


async def test_a_loopback_read_cannot_decide(env) -> None:
    env.current["mode"] = "loopback"
    response = await env.client.post("/api/budget/1/deny", json=_body())
    assert response.status_code == 401


async def test_a_disabled_ledger_is_503_not_a_stack_trace(env) -> None:
    env.runtime.budget = None
    response = await env.client.post("/api/budget/1/approve", json=_body())
    assert response.status_code == 503


# ------------------------------------------------------------------ decisions


async def test_owner_approval_commits_and_publishes_one_event(env) -> None:
    request_id = await _request(env)
    seen: list[ApprovalEvent] = []

    async def capture(event):
        seen.append(event)

    APPROVAL_BUS.subscribe(capture)
    response = await env.client.post(
        f"/api/budget/{request_id}/approve", json=_body(note="looks fine")
    )
    assert response.status_code == 200, response.text
    assert response.json()["status"] == "approved"
    assert response.json()["notified"] == 1
    assert len(seen) == 1
    event = seen[0]
    assert event.kind == APPROVED
    assert event.request_id == request_id
    assert event.session_key == SCOPE
    assert event.actor_id == "owner-1"
    assert event.note == "looks fine"
    assert event.degraded is False
    assert event.remaining_minor is not None


async def test_owner_denial_releases_and_publishes(env) -> None:
    request_id = await _request(env)
    seen: list[ApprovalEvent] = []

    async def capture(event):
        seen.append(event)

    APPROVAL_BUS.subscribe(capture)
    response = await env.client.post(f"/api/budget/{request_id}/deny", json=_body())
    assert response.status_code == 200, response.text
    assert response.json()["status"] == "denied"
    assert seen[0].kind == DENIED


async def test_a_replayed_approval_is_a_conflict_not_a_second_event(env) -> None:
    request_id = await _request(env)
    seen: list[ApprovalEvent] = []

    async def capture(event):
        seen.append(event)

    APPROVAL_BUS.subscribe(capture)
    assert (
        await env.client.post(f"/api/budget/{request_id}/approve", json=_body())
    ).status_code == 200
    again = await env.client.post(f"/api/budget/{request_id}/approve", json=_body())
    assert again.status_code == 409
    assert len(seen) == 1


async def test_another_sessions_request_is_not_found(env) -> None:
    request_id = await _request(env)
    response = await env.client.post(
        f"/api/budget/{request_id}/approve", json=_body("onebot11:group:999")
    )
    assert response.status_code == 404


async def test_a_requester_cannot_approve_their_own_request(env) -> None:
    request_id = await _request(env, requester_id="owner-1")
    response = await env.client.post(f"/api/budget/{request_id}/approve", json=_body())
    assert response.status_code == 403


async def test_an_explicitly_degraded_policy_is_visible_in_the_event(env) -> None:
    """Single-owner deployments may opt out — but never silently."""
    env.store.policy.require_distinct_approver = False
    request_id = await _request(env, requester_id="owner-1")
    seen: list[ApprovalEvent] = []

    async def capture(event):
        seen.append(event)

    APPROVAL_BUS.subscribe(capture)
    response = await env.client.post(f"/api/budget/{request_id}/approve", json=_body())
    assert response.status_code == 200, response.text
    assert seen[0].degraded is True


async def test_the_view_reports_the_distinct_approver_policy(env) -> None:
    response = await env.client.get("/api/budget")
    assert response.status_code == 200
    assert response.json()["policy"]["require_distinct_approver"] is True
