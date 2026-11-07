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
import subprocess
import sys
import threading
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

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
