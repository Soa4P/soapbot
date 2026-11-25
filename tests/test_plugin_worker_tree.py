"""A worker that exits must take its process tree with it (audit S-PLUG-02).

Three exit paths, and only one of them used to be safe:

* timeout / crash while the leader is alive → ``_kill_tree`` signals the group, fine;
* **graceful shutdown** → the child handles the ``shutdown`` frame and exits 0, and
  nothing ever signalled the group, so helpers it forked kept running. Unloading a
  plugin did not unload it;
* the one-shot invocation path → same success-path hole, once per call.

`kill_group_after_exit` is the missing sweep; the Windows job-object handle is now held
per worker, so closing it also empties that worker's tree.
"""

from __future__ import annotations

import os
import subprocess
import sys
import time
from pathlib import Path

import pytest

from soapbot.plugins import job_object, supervisor
from soapbot.plugins.isolation import kill_group_after_exit

posix_only = pytest.mark.skipif(
    sys.platform == "win32",
    reason="POSIX process groups; on Windows a job object owns this and needs a real child",
)


def _alive(pid: int) -> bool:
    try:
        os.kill(pid, 0)
    except ProcessLookupError:
        return False
    except PermissionError:  # pragma: no cover - a live foreign process
        return True
    return True


def _wait_until(predicate, timeout: float = 5.0) -> bool:
    deadline = time.time() + timeout
    while time.time() < deadline:
        if predicate():
            return True
        time.sleep(0.05)
    return False


@posix_only
def test_helper_survives_a_graceful_leader_exit_until_the_sweep(tmp_path: Path) -> None:
    """Reproduces the leak, then closes it.

    The leader exits 0 the way a plugin worker does on ``shutdown``; the helper it
    forked is still running — the state ``unload`` used to leave behind.
    """
    pidfile = tmp_path / "helper.pid"
    proc = subprocess.Popen(
        ["sh", "-c", f"sleep 60 & echo $! > '{pidfile}'; exit 0"],
        start_new_session=True,
    )
    try:
        assert proc.wait(timeout=10) == 0
        helper = int(pidfile.read_text(encoding="utf-8").strip())
        assert _alive(helper), "the helper must still be running before the sweep"

        kill_group_after_exit(proc.pid)

        assert _wait_until(lambda: not _alive(helper)), (
            "the group sweep must reach a helper whose leader has already exited"
        )
    finally:
        if proc.poll() is None:  # pragma: no cover - defensive
            proc.kill()


@posix_only
def test_sweeping_an_already_empty_group_is_a_no_op() -> None:
    """Idempotence is what lets every exit path call this without ordering rules."""
    proc = subprocess.Popen(["sh", "-c", "exit 0"], start_new_session=True)
    assert proc.wait(timeout=10) == 0

    kill_group_after_exit(proc.pid)
    kill_group_after_exit(proc.pid)


def test_job_object_is_a_noop_off_windows() -> None:
    if os.name == "nt":  # pragma: no cover - the CI Windows job exercises attach for real
        pytest.skip("off-Windows contract does not apply here")
    assert job_object.attach(999_999_999) is None
    assert job_object.assign(12345) is False
    job_object.detach(None)
    job_object.detach(12345)


def test_release_tree_closes_the_job_exactly_once(monkeypatch) -> None:
    """The handle is the kill switch; closing it twice would signal nothing useful and
    a stale handle could belong to somebody else's job."""
    closed: list[int] = []
    sweeps: list[int] = []

    monkeypatch.setattr(supervisor, "kill_group_after_exit", lambda pid: sweeps.append(pid))
    monkeypatch.setattr(job_object, "detach", lambda handle: closed.append(handle))

    class _Worker:
        _job: int | None = 4242

    worker = _Worker()
    supervisor.PluginWorker._release_tree(worker, 1234)  # type: ignore[arg-type]
    supervisor.PluginWorker._release_tree(worker, 1234)  # type: ignore[arg-type]

    assert closed == [4242]
    assert sweeps == [1234, 1234]
    assert worker._job is None
