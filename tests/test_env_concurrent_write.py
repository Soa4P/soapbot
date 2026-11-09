"""`.env` saves must not lose each other's keys.

Four API endpoints used to hand-roll the same three steps:

    existing = path.read_text()
    updated = _rewrite_env(existing, updates)
    write_atomic(path, updated)

``write_atomic`` makes the final ``os.replace`` atomic, which is not the same thing as
making the *transaction* atomic. Two saves that both start from the same text each
rebuild the whole file, and whichever replaces last silently erases the other's keys.
The worst part is the response: both say ``written: true``, so the operator only finds
out after a restart, from a setting that reverted.

These tests exercise the locked entry point from threads *and* from separate processes,
because a thread lock alone cannot see into another uvicorn worker.
"""

from __future__ import annotations

import inspect
import os
import subprocess
import sys
import threading
import time
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

import pytest

from soapbot.api import admin, security, settings
from soapbot.core import config_write

_CHILD = """
import sys
import time
from pathlib import Path
from soapbot.core import config_write

env = Path(sys.argv[1])
key = sys.argv[2]
for i in range(20):
    config_write.write_env_updates(env, {key: str(i)})
    time.sleep(0.001)
"""

#: Holds byte 0 of a *zero-length* sidecar lock file. Windows permits locking a byte
#: range past EOF, so this is the exact state that used to make the writer's
#: "ensure one lockable byte" `os.write` fail with PermissionError instead of waiting.
_HOLDER = """
import msvcrt
import os
import sys
import time

fd = os.open(sys.argv[1], os.O_CREAT | os.O_RDWR, 0o600)
os.lseek(fd, 0, os.SEEK_SET)
msvcrt.locking(fd, msvcrt.LK_NBLCK, 1)
print("READY", flush=True)
time.sleep(0.6)
os.lseek(fd, 0, os.SEEK_SET)
msvcrt.locking(fd, msvcrt.LK_UNLCK, 1)
os.close(fd)
"""


def test_threaded_writers_keep_every_key(tmp_path: Path) -> None:
    env = tmp_path / ".env"
    env.write_text("# operator notes stay\nSOAPBOT_LOG_LEVEL=INFO\n", encoding="utf-8")
    keys = [f"SOAPBOT_TEST_KEY_{i}" for i in range(24)]
    barrier = threading.Barrier(len(keys))

    def worker(key: str) -> None:
        barrier.wait()
        config_write.write_env_updates(env, {key: "1"})

    with ThreadPoolExecutor(max_workers=len(keys)) as pool:
        list(pool.map(worker, keys))

    text = env.read_text(encoding="utf-8")
    for key in keys:
        assert f"{key}=1" in text, f"{key} was lost to another writer"
    # The rewrite is still a patch, not a regeneration from Settings.
    assert "# operator notes stay" in text
    assert "SOAPBOT_LOG_LEVEL=INFO" in text


def test_separate_processes_do_not_overwrite_each_other(tmp_path: Path) -> None:
    """A thread lock is invisible across processes; the sidecar file lock is not."""
    env = tmp_path / ".env"
    env.write_text("", encoding="utf-8")

    children = [
        subprocess.Popen(
            [sys.executable, "-c", _CHILD, str(env), f"SOAPBOT_PROC_KEY_{n}"],
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
        )
        for n in range(4)
    ]
    for child in children:
        _out, err = child.communicate(timeout=90)
        assert child.returncode == 0, err.decode("utf-8", "replace")

    text = env.read_text(encoding="utf-8")
    for n in range(4):
        assert f"SOAPBOT_PROC_KEY_{n}=19" in text, f"writer {n} was overwritten"


@pytest.mark.skipif(os.name != "nt", reason="the byte-range lock is the Windows branch")
def test_a_held_zero_length_lock_does_not_break_the_write(tmp_path: Path) -> None:
    """A foreign holder of byte 0 must make us *wait*, not die on `os.write`.

    Reproduces the 2026-11-08 Windows CI failure deterministically instead of relying
    on four racing processes: the holder locks byte 0 of a zero-length `.env.lock` and
    keeps it for 0.6 s. The old implementation saw `st_size == 0`, tried to
    `os.write(fd, b"\\0")` to "create a lockable byte", and Windows rejected that write
    with `PermissionError [Errno 13]` because another process already owned the range —
    the child then exited nonzero and the suite went red.

    The fix is to lock the range directly: Windows allows locking past EOF, so no
    process ever needs to write the sidecar file. This test fails on the old code with
    that exact PermissionError and passes once the write is gone.
    """
    env = tmp_path / ".env"
    env.write_text("", encoding="utf-8")
    lock_path = tmp_path / ".env.lock"
    lock_path.write_bytes(b"")

    holder = subprocess.Popen(
        [sys.executable, "-c", _HOLDER, str(lock_path)],
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        text=True,
    )
    try:
        assert holder.stdout is not None
        assert holder.stdout.readline().strip() == "READY", (
            "the holder never took the lock; "
            + (holder.stderr.read() if holder.poll() is not None else "")
        )
        result = config_write.write_env_updates(env, {"SOAPBOT_LOG_LEVEL": "DEBUG"})
        assert "SOAPBOT_LOG_LEVEL=DEBUG" in result
        assert env.read_text(encoding="utf-8") == result
    finally:
        _out, err = holder.communicate(timeout=15)
    # Outside the finally on purpose: when the body raises the real regression, an
    # assertion inside it would replace that traceback with "holder exited 0".
    assert holder.returncode == 0, err

    # No process may write the sidecar: that write is the whole race.
    assert lock_path.stat().st_size == 0, "the lock file gained a byte again"


@pytest.mark.skipif(os.name != "nt", reason="the bounded retry is the Windows branch")
def test_a_held_lock_times_out_with_a_named_error(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """A lock that cannot be taken must fail loudly, on budget, and say which file.

    ``msvcrt.LK_LOCK`` used to block for a fixed ten seconds and then raise a bare
    ``OSError``, which is why the concurrency test above was flaky rather than wrong:
    under contention the budget ran out and the child died. The replacement is only an
    improvement if it (a) still raises instead of degrading to "no lock", (b) raises
    something a log reader can act on, and (c) actually honours its own deadline. This
    asserts all three without waiting thirty seconds.
    """
    import msvcrt

    env = tmp_path / ".env"
    env.write_text("", encoding="utf-8")

    def always_contended(_fd: int, _mode: int, _nbytes: int) -> None:
        raise OSError("simulated: another writer holds the byte range")

    monkeypatch.setattr(msvcrt, "locking", always_contended)
    monkeypatch.setattr(config_write, "_ENV_LOCK_TIMEOUT", 0.05)

    started = time.monotonic()
    with pytest.raises(config_write.EnvLockError) as caught:
        config_write.write_env_updates(env, {"SOAPBOT_LOG_LEVEL": "DEBUG"})
    elapsed = time.monotonic() - started

    assert ".env.lock" in str(caught.value), "the error must name the lock file"
    assert "another writer" in str(caught.value)
    assert elapsed < 1.0, f"the deadline was not honoured ({elapsed:.2f}s for a 0.05s budget)"
    # The failed save must not have written anything: a half-applied transaction is
    # worse than a refused one.
    assert env.read_text(encoding="utf-8") == ""


def test_the_lock_timeout_is_an_oserror_so_existing_handlers_still_apply() -> None:
    """Four API writers catch ``OSError`` and answer ``api.write_failed``.

    A timeout is a write that did not happen, so that mapping is already correct; this
    pins the inheritance down so a future refactor to ``Exception`` cannot silently
    turn a refused save into a 500 with a traceback.
    """
    assert issubclass(config_write.EnvLockError, OSError)
    assert issubclass(config_write.EnvLockError, TimeoutError)


def test_the_lock_sidecar_never_becomes_part_of_the_env(tmp_path: Path) -> None:
    env = tmp_path / ".env"
    config_write.write_env_updates(env, {"SOAPBOT_LOG_LEVEL": "DEBUG"})

    assert (tmp_path / ".env.lock").exists()
    assert env.read_text(encoding="utf-8") == "SOAPBOT_LOG_LEVEL=DEBUG\n"


def test_rewrite_env_preserves_comments_order_and_unknown_keys() -> None:
    existing = (
        "# why this value\n"
        "SOAPBOT_LOG_LEVEL=INFO\n"
        "OPERATOR_ONLY=keep\n"
        "SOAPBOT_PORT=6185\n"
    )
    updated = config_write.rewrite_env(existing, {"SOAPBOT_LOG_LEVEL": "DEBUG"})

    assert updated == (
        "# why this value\n"
        "SOAPBOT_LOG_LEVEL=DEBUG\n"
        "OPERATOR_ONLY=keep\n"
        "SOAPBOT_PORT=6185\n"
    )


def test_every_runtime_env_writer_uses_the_locked_entry_point() -> None:
    """A fifth hand-rolled read-modify-write would reintroduce the bug silently.

    This is a structural assertion rather than a behaviour one on purpose: each
    endpoint already has its own behavioural tests, and none of them would notice if a
    future edit inlined the three steps again while still passing on an uncontended file.
    """
    writers = (
        (settings, "write_settings"),
        (security, "write_authority"),
        (security, "write_group_scope"),
        (admin, "write_persona_binding"),
    )
    for module, name in writers:
        source = inspect.getsource(getattr(module, name))
        assert "write_env_updates" in source, f"{module.__name__}.{name} bypasses the lock"
        assert "read_text" not in source, f"{module.__name__}.{name} reads .env itself"
