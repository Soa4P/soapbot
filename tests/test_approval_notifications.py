"""Approval notifications: three channels, one dedup answer, no credential leaks.

The ledger commits before publishing, so the property under test is that a broken
or malicious channel cannot change a decision, cannot silence another channel,
and cannot make the same decision look like two different ones.
"""

from __future__ import annotations

import hashlib
import hmac
from types import SimpleNamespace

import httpx
import pytest
from fastapi import FastAPI
from pydantic import SecretStr

from soapbot.api.admin import router as admin_router
from soapbot.api.auth import require_api_auth
from soapbot.budget.events import APPROVAL_BUS, APPROVED, REQUESTED, ApprovalEvent
from soapbot.notifications.dispatcher import ApprovalNotifier

URL = "https://hooks.example.com/approvals"
SECRET = "a-long-signing-secret-that-must-never-leak"


@pytest.fixture(autouse=True)
def _clear_bus():
    APPROVAL_BUS.clear()
    yield
    APPROVAL_BUS.clear()


def _event(kind: str = REQUESTED, request_id: int = 1) -> ApprovalEvent:
    return ApprovalEvent(
        kind=kind,
        request_id=request_id,
        session_key="onebot11:group:100",
        amount_minor=1250,
        currency="CNY",
        purpose="materials",
        created_at=1.0,
    )


def _settings(**kw):
    values = {
        "notify_session_key": "",
        "notify_webhook_url": "",
        "notify_webhook_secret": SecretStr(SECRET),
    }
    values.update(kw)
    return SimpleNamespace(**values)


class _Runtime:
    def __init__(self) -> None:
        self.sent: list[tuple[str, str]] = []

    async def _send_via_adapter(self, session_key: str, text: str) -> None:
        self.sent.append((session_key, text))


class _Client:
    def __init__(self, *, status: int = 200, raises: bool = False) -> None:
        self.calls: list[tuple[str, bytes, dict]] = []
        self.status = status
        self.raises = raises

    async def post(self, url, content=None, headers=None):
        self.calls.append((url, content, dict(headers or {})))
        if self.raises:
            raise OSError("connection reset")
        return SimpleNamespace(status_code=self.status)


class _Audit:
    def __init__(self) -> None:
        self.entries: list[dict] = []

    def record(self, **kwargs):
        self.entries.append(kwargs)


def _notifier(**kw):
    runtime = kw.pop("runtime", _Runtime())
    client = kw.pop("client", _Client())
    audit = kw.pop("audit", _Audit())
    settings = kw.pop("settings", _settings())
    return (
        ApprovalNotifier(
            runtime, settings=settings, audit=audit, client=client, **kw
        ).start(),
        runtime,
        client,
        audit,
    )


# ------------------------------------------------------------------ QQ

async def test_qq_channel_delivers_a_bounded_message() -> None:
    notifier, runtime, _, _ = _notifier(settings=_settings(notify_session_key="onebot11:private:9"))
    try:
        await APPROVAL_BUS.publish(_event())
        assert len(runtime.sent) == 1
        assert runtime.sent[0][0] == "onebot11:private:9"
        assert "#1" in runtime.sent[0][1]
        assert len(runtime.sent[0][1]) <= 500
    finally:
        notifier.stop()


async def test_qq_channel_is_skipped_when_unconfigured() -> None:
    notifier, runtime, _, _ = _notifier()
    try:
        await APPROVAL_BUS.publish(_event())
        assert runtime.sent == []
    finally:
        notifier.stop()


# ------------------------------------------------------------------ webhook

async def test_webhook_signature_can_be_verified() -> None:
    notifier, _, client, _ = _notifier(settings=_settings(notify_webhook_url=URL))
    try:
        await APPROVAL_BUS.publish(_event())
        assert len(client.calls) == 1
        _url, body, headers = client.calls[0]
        ts = headers["X-Soapbot-Timestamp"]
        nonce = headers["X-Soapbot-Nonce"]
        expected = hmac.new(
            SECRET.encode(),
            ts.encode() + b"." + nonce.encode() + b"." + body,
            hashlib.sha256,
        ).hexdigest()
        assert headers["X-Soapbot-Signature"] == expected
        assert b'"kind":"requested"' in body
    finally:
        notifier.stop()


async def test_the_secret_never_appears_in_headers_body_or_audit() -> None:
    notifier, _, client, audit = _notifier(settings=_settings(notify_webhook_url=URL))
    try:
        await APPROVAL_BUS.publish(_event())
        _url, body, headers = client.calls[0]
        assert SECRET.encode() not in body
        assert all(SECRET not in str(v) for v in headers.values())
        assert SECRET not in str(audit.entries)
        # The audit names only the host and the status, not the full URL or purpose.
        assert any("host=hooks.example.com" in str(e.get("detail")) for e in audit.entries)
    finally:
        notifier.stop()


async def test_a_broken_webhook_does_not_break_the_other_channels() -> None:
    notifier, runtime, _, _ = _notifier(
        settings=_settings(
            notify_webhook_url=URL, notify_session_key="onebot11:private:9"
        ),
        client=_Client(raises=True),
    )
    try:
        assert await APPROVAL_BUS.publish(_event()) == 1
        assert len(runtime.sent) == 1
    finally:
        notifier.stop()


async def test_a_non_200_webhook_is_logged_without_the_url(caplog) -> None:
    notifier, _, _, _ = _notifier(
        settings=_settings(notify_webhook_url=URL), client=_Client(status=503)
    )
    try:
        await APPROVAL_BUS.publish(_event())
        assert URL not in caplog.text
    finally:
        notifier.stop()


# ------------------------------------------------------------------ idempotency / feed

async def test_the_same_event_is_delivered_only_once() -> None:
    notifier, runtime, client, _ = _notifier(
        settings=_settings(
            notify_webhook_url=URL, notify_session_key="onebot11:private:9"
        )
    )
    try:
        await APPROVAL_BUS.publish(_event())
        await APPROVAL_BUS.publish(_event())
        assert len(runtime.sent) == 1
        assert len(client.calls) == 1
        assert len(notifier.feed()["events"]) == 1
    finally:
        notifier.stop()


async def test_a_different_decision_on_the_same_request_is_not_suppressed() -> None:
    notifier, _, _, _ = _notifier()
    try:
        await APPROVAL_BUS.publish(_event(REQUESTED))
        await APPROVAL_BUS.publish(_event(APPROVED))
        assert [e["kind"] for e in notifier.feed()["events"]] == [REQUESTED, APPROVED]
    finally:
        notifier.stop()


async def test_the_feed_cursor_returns_only_new_events() -> None:
    notifier, _, _, _ = _notifier()
    try:
        await APPROVAL_BUS.publish(_event(request_id=1))
        first = notifier.feed()
        assert first["cursor"] == 1
        assert notifier.feed(after=first["cursor"])["events"] == []
        await APPROVAL_BUS.publish(_event(request_id=2))
        later = notifier.feed(after=first["cursor"])
        assert [e["request_id"] for e in later["events"]] == [2]
    finally:
        notifier.stop()


async def test_the_feed_is_bounded() -> None:
    notifier, _, _, _ = _notifier(feed_size=3)
    try:
        for i in range(10):
            await APPROVAL_BUS.publish(_event(request_id=i))
        feed = notifier.feed()
        assert len(feed["events"]) == 3
        assert feed["cursor"] == 10
    finally:
        notifier.stop()


async def test_the_feed_payload_is_the_event_whitelist() -> None:
    notifier, _, _, _ = _notifier()
    try:
        await APPROVAL_BUS.publish(_event())
        payload = notifier.feed()["events"][0]
        assert payload["id"] == 1
        assert payload["amount_minor"] == 1250
        assert "raw_html" not in payload
    finally:
        notifier.stop()


# ------------------------------------------------------------------ endpoint

@pytest.fixture
async def client(monkeypatch):
    notifier = ApprovalNotifier(settings=_settings()).start()
    runtime = SimpleNamespace(approval_notifier=notifier)
    monkeypatch.setattr("soapbot.app.get_runtime", lambda: runtime)
    app = FastAPI()
    app.include_router(admin_router)
    current = {"subject": "owner-1", "role": "owner", "mode": "token"}

    async def fake_auth():
        return dict(current)

    app.dependency_overrides[require_api_auth] = fake_auth
    transport = httpx.ASGITransport(app=app)
    async with httpx.AsyncClient(transport=transport, base_url="http://test") as c:
        yield c, notifier, current
    notifier.stop()


async def test_feed_endpoint_reports_events_by_cursor(client) -> None:
    http, _, _ = client
    await APPROVAL_BUS.publish(_event())
    first = await http.get("/api/approvals/feed")
    assert first.status_code == 200
    assert first.json()["enabled"] is True
    assert first.json()["cursor"] == 1
    again = await http.get("/api/approvals/feed", params={"after": 1})
    assert again.json()["events"] == []


async def test_feed_endpoint_requires_the_management_permission(client) -> None:
    http, _, current = client
    current["role"] = "member"
    response = await http.get("/api/approvals/feed")
    assert response.status_code == 403
