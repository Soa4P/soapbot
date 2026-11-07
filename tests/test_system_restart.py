"""The restart endpoint: admin-only, answers before exiting, and names the real task."""

from __future__ import annotations

import logging
import subprocess
from typing import Any

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from soapbot.api import system as system_api
from soapbot.api.auth import require_api_auth
from soapbot.api.system import router


@pytest.fixture()
def client() -> TestClient:
    app = FastAPI()
    app.include_router(router)
    return TestClient(app)


def _post(client: TestClient, role: str) -> Any:
    client.app.dependency_overrides[require_api_auth] = lambda: {"role": role}
    try:
        return client.post("/api/system/restart")
    finally:
        client.app.dependency_overrides.clear()


def test_member_cannot_restart(client: TestClient) -> None:
    assert _post(client, "member").status_code == 403


def test_admin_gets_an_answer_before_the_process_leaves(
    client: TestClient, monkeypatch: pytest.MonkeyPatch
) -> None:
    """A restart that kills the connection before responding is indistinguishable from
    a failed save, so the endpoint must return first."""
    scheduled: list[float] = []

    async def _fake_schedule(*, delay: float = 0) -> None:
        scheduled.append(delay)

    monkeypatch.setattr(system_api, "schedule_restart", _fake_schedule)

    response = _post(client, "admin")

    assert response.status_code == 200
    body = response.json()
    assert body["scheduled"] is True
    assert body["hint"]


def test_windows_restart_command_names_the_installed_task(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    captured: list[list[str]] = []

    def _fake_popen(argv, **kwargs):
        captured.append(argv)
        return None

    monkeypatch.setattr(subprocess, "Popen", _fake_popen)
    monkeypatch.setattr(system_api, "service_name", lambda: "SoapbotBot")
    monkeypatch.setattr(system_api.sys, "platform", "win32")
    monkeypatch.setattr(system_api.time, "sleep", lambda _s: None)

    system_api._spawn_windows_restart()

    assert len(captured) == 2, "End and Run are separate children, not one shell line"
    assert captured[0] == ["schtasks", "/End", "/TN", "SoapbotBot"]
    assert captured[1] == ["schtasks", "/Run", "/TN", "SoapbotBot"]


def test_task_name_is_never_interpreted_by_a_shell(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """A task name with shell metacharacters must stay a task name.

    The name comes from ``SOAPBOT_SERVICE_NAME`` in ``.env``, and the old code pasted
    it into ``cmd.exe /c``. A value like ``Soapbot & calc`` would have run ``calc``
    with the service account's rights at the exact moment the process was exiting —
    no shell means the name can only ever be an argument.
    """
    captured: list[list[str]] = []

    def _fake_popen(argv, **kwargs):
        captured.append(argv)
        return None

    monkeypatch.setattr(subprocess, "Popen", _fake_popen)
    monkeypatch.setattr(system_api, "service_name", lambda: 'Soapbot & calc "x"')
    monkeypatch.setattr(system_api.sys, "platform", "win32")
    monkeypatch.setattr(system_api.time, "sleep", lambda _s: None)

    system_api._spawn_windows_restart()

    for argv in captured:
        assert argv[0] == "schtasks", "no cmd.exe, so nothing parses the name"
        assert "cmd.exe" not in argv
        assert 'Soapbot & calc "x"' in argv


def test_restart_delay_is_short_but_not_zero() -> None:
    """Zero would race the response; long enough to be safe, short enough to feel instant."""
    assert 0.1 <= system_api.RESTART_DELAY_SECONDS <= 3.0


def test_concurrent_restart_requests_schedule_only_one_exit(
    client: TestClient, monkeypatch: pytest.MonkeyPatch
) -> None:
    """A pending restart must not create a second exit task.

    On Linux SIGTERM triggers a graceful shutdown rather than an immediate exit, so a
    second request arriving in that window really did schedule a second signal and
    kept accepting writes against a process that was already going down.
    """
    calls: list[float] = []

    async def _fake_schedule(*, delay: float = 0) -> None:
        calls.append(delay)

    monkeypatch.setattr(system_api, "schedule_restart", _fake_schedule)
    # Simulate a task that has been created but has not completed yet.
    monkeypatch.setattr(system_api, "_pending_restarts", {object()})

    response = _post(client, "admin")

    assert response.status_code == 200
    assert response.json()["scheduled"] is False
    assert response.json()["already_scheduled"] is True
    assert calls == []


@pytest.mark.asyncio
async def test_spawn_failure_is_logged_instead_of_being_swallowed(
    monkeypatch: pytest.MonkeyPatch, caplog: pytest.LogCaptureFixture
) -> None:
    """`scheduled: True` with a dead exit task is a restart that never happens.

    The task used to have no exception consumer, so a `Popen` OSError produced only
    asyncio's "Task exception was never retrieved" while the endpoint had already
    told the panel everything was fine.
    """

    def _boom() -> None:
        raise OSError("schtasks unavailable")

    monkeypatch.setattr(system_api, "_perform_now", _boom)

    with caplog.at_level(logging.ERROR):
        await system_api.schedule_restart(delay=0)

    assert "restart failed" in caplog.text
    assert "schtasks unavailable" in caplog.text
