"""Privilege separation for plugin workers (S-PLUG-04).

The audit's "same-uid self-approval" finding: a plugin process runs as the host's user,
so it can rewrite ``plugin-approvals.json`` and approve itself — every pipe-level check
in ``isolation.py`` is irrelevant to that, because the child does not have to *ask*.

An HMAC over the approval file would be signed with a key the same uid can read, so it
would look like a boundary without being one. The real fix is an identity change:
``PLUGIN_RUN_UID`` / ``PLUGIN_RUN_GID`` make the worker run as a different user.

These tests pin the decision logic, the forwarding into the spawn call, and the honest
Windows behaviour. A live uid switch needs root, which CI does not have.
"""

from __future__ import annotations

import contextlib
import sys

import pytest

from soapbot.config import settings
from soapbot.plugins import isolation, supervisor


@pytest.fixture(autouse=True)
def _reset(monkeypatch):
    monkeypatch.setattr(settings, "plugin_run_uid", None, raising=False)
    monkeypatch.setattr(settings, "plugin_run_gid", None, raising=False)
    yield


def test_unset_means_no_extra_kwargs() -> None:
    """Default must be a no-op: dropping privileges silently would break deployments
    whose plugin directories are only readable by the host user."""
    assert isolation.privilege_kwargs() == {}


def test_posix_uid_and_gid_are_forwarded(monkeypatch) -> None:
    monkeypatch.setattr(isolation.sys, "platform", "linux")
    monkeypatch.setattr(settings, "plugin_run_uid", 10001, raising=False)
    monkeypatch.setattr(settings, "plugin_run_gid", 10001, raising=False)
    assert isolation.privilege_kwargs() == {"user": 10001, "group": 10001}


def test_a_gid_alone_still_applies(monkeypatch) -> None:
    """Only a group change is a weaker separation, but it is what the operator asked
    for; silently ignoring it would be worse than honouring it."""
    monkeypatch.setattr(isolation.sys, "platform", "linux")
    monkeypatch.setattr(settings, "plugin_run_gid", 20000, raising=False)
    assert isolation.privilege_kwargs() == {"group": 20000}


def test_windows_reports_and_ignores(monkeypatch, caplog) -> None:
    """Windows has no equivalent: job objects do not change identity. Pretending
    otherwise would leave an operator believing a boundary exists."""
    import logging

    monkeypatch.setattr(isolation.sys, "platform", "win32")
    monkeypatch.setattr(settings, "plugin_run_uid", 10001, raising=False)
    with caplog.at_level(logging.WARNING, logger="soapbot.plugins.isolation"):
        assert isolation.privilege_kwargs() == {}
    assert any("POSIX-only" in record.message for record in caplog.records)


async def test_the_resident_worker_start_forwards_the_kwargs(monkeypatch, tmp_path) -> None:
    """The setting only matters if it reaches ``create_subprocess_exec``."""
    captured: dict = {}

    class _Proc:
        pid = 4242
        returncode = None

        async def communicate(self):  # pragma: no cover - not reached
            return b"", b""

    async def fake_exec(*args, **kwargs):
        captured.update(kwargs)
        return _Proc()

    monkeypatch.setattr(isolation.sys, "platform", "linux")
    monkeypatch.setattr(settings, "plugin_run_uid", 10001, raising=False)
    monkeypatch.setattr(settings, "plugin_run_gid", 10001, raising=False)
    monkeypatch.setattr(supervisor.asyncio, "create_subprocess_exec", fake_exec)
    # The job-object path is Windows-only; on POSIX the call is a no-op anyway.
    monkeypatch.setattr("soapbot.plugins.job_object.assign", lambda _pid: None, raising=False)

    plugin_dir = tmp_path / "p"
    plugin_dir.mkdir()
    worker = supervisor.PluginWorker(
        supervisor.WorkerConfig(plugin="p", plugin_dir=plugin_dir, attr="Plugin"),
        surface_handler=lambda *_a, **_k: None,
    )
    # start() continues into the ready-frame handshake after spawning, which the fake
    # process cannot provide; the spawn kwargs are what this test is about.
    with contextlib.suppress(Exception):
        await worker.start()

    assert captured.get("user") == 10001
    assert captured.get("group") == 10001


def test_platform_guard_is_the_real_one() -> None:
    """Sanity: this suite's platform assumption is explicit rather than accidental."""
    assert sys.platform in {"win32", "linux", "darwin"} or sys.platform.startswith("linux")
