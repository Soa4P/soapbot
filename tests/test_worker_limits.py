"""The limits the worker sets on itself must not kill honest plugins.

These exist because the opposite was true and CI could not say why. The worker
reported ready, then died with exit code 1 about ten milliseconds later on the first
invoke, and its stderr was only forwarded to a DEBUG logger — so the failure looked
intermittent for several rounds.

Two self-inflicted limits were responsible:

* ``RLIMIT_NPROC = 64`` — counted per real uid across the whole system, and it counts
  threads. On a shared account (every CI runner) the quota is partly spent before the
  worker starts, so the first ``run_in_executor`` call — which creates the frame
  reader's thread — fails with "can't start new thread" and the process exits 1.
* ``RLIMIT_AS = 256 MiB`` — counts *virtual* address space, of which a bare CPython
  reserves a few hundred MiB before any plugin code runs.

Both are POSIX-only, which is why the Windows job never failed and the Linux one did.
"""

from __future__ import annotations

import asyncio
import sys
from pathlib import Path

import pytest

from soapbot.plugins.supervisor import PluginSupervisor, WorkerConfig, WorkerCrashedError

POSIX_ONLY = pytest.mark.skipif(
    sys.platform == "win32",
    reason="resource/RLIMIT_* is POSIX-only; the child applies no limits on Windows",
)

_PLUGIN = """
import resource, threading

class Plugin:
    async def setup(self, ctx):
        @ctx.command("limits")
        async def limits(caller, args):
            nproc_soft, _ = resource.getrlimit(resource.RLIMIT_NPROC)
            as_soft, _ = resource.getrlimit(resource.RLIMIT_AS)
            return {"nproc": nproc_soft, "as": as_soft}

        @ctx.command("thread")
        async def thread(caller, args):
            # Exactly what the frame reader does on its first call.
            t = threading.Thread(target=lambda: None)
            t.start()
            t.join()
            return "ok"
"""


class _Caller:
    user_id = "1"
    role = "admin"
    session_key = "group:1"


async def _boot(tmp_path: Path):
    plugin_dir = tmp_path / "plug"
    plugin_dir.mkdir()
    (plugin_dir / "main.py").write_text(_PLUGIN, encoding="utf-8")

    sup = PluginSupervisor()
    sup.bind_surface_handler(lambda *a, **k: None)
    sup.register(WorkerConfig(plugin="limits", plugin_dir=plugin_dir, timeout=10.0))
    worker = await sup.start("limits")
    return sup, worker


@POSIX_ONLY
async def test_child_does_not_lower_the_process_quota(tmp_path: Path) -> None:
    """A per-uid quota set by one child throttles every sibling process.

    That is not containment, it is self-harm: the child cannot even create its own
    reader thread once the account is busy.
    """
    sup, worker = await _boot(tmp_path)
    try:
        got = await worker.invoke("limits", caller=_Caller(), timeout=10.0)
    finally:
        await sup.stop_all()

    import resource

    parent_soft, _ = resource.getrlimit(resource.RLIMIT_NPROC)
    assert got["nproc"] == parent_soft, (
        "the worker changed the whole account's process quota: "
        f"parent={parent_soft} child={got['nproc']}"
    )


@POSIX_ONLY
async def test_child_has_room_for_its_own_memory(tmp_path: Path) -> None:
    """RLIMIT_AS counts virtual space; the interpreter alone uses ~250 MiB of it."""
    sup, worker = await _boot(tmp_path)
    try:
        got = await worker.invoke("limits", caller=_Caller(), timeout=10.0)
    finally:
        await sup.stop_all()

    assert got["as"] >= 512 * 1024 * 1024, (
        "memory cap is below what a bare interpreter reserves, so an innocent "
        f"thread creation can fail: {got['as']}"
    )


@POSIX_ONLY
async def test_child_can_create_a_thread_on_the_first_invoke(tmp_path: Path) -> None:
    """The regression itself: this is the call that used to kill the worker."""
    sup, worker = await _boot(tmp_path)
    try:
        assert await worker.invoke("thread", caller=_Caller(), timeout=10.0) == "ok"
    finally:
        await sup.stop_all()


class _FakeStdin:
    def __init__(self) -> None:
        self.written: list[bytes] = []

    def write(self, data: bytes) -> None:
        self.written.append(data)

    async def drain(self) -> None:
        return None


class _FakeProc:
    """Just enough process for ``PluginWorker.invoke`` to write and read."""

    returncode = None

    def __init__(self) -> None:
        self.stdin = _FakeStdin()
        self.stdout = object()


async def test_a_fatal_frame_is_reported_instead_of_becoming_an_exit_code(
    monkeypatch,
) -> None:
    """The child used to die silently; now it says why and the host repeats it.

    Without this the operator gets "died (code=1)", which is a number, not a cause.
    """
    from soapbot.plugins import supervisor as sup_mod

    async def _fatal(_reader):
        return {"type": "fatal", "error": "RuntimeError: can't start new thread"}

    monkeypatch.setattr(sup_mod, "_read_frame", _fatal)

    worker = sup_mod.PluginWorker(
        WorkerConfig(plugin="limits", plugin_dir=Path(".")),
        surface_handler=lambda *a, **k: None,
    )
    worker._proc = _FakeProc()

    with pytest.raises(WorkerCrashedError, match="can't start new thread"):
        await worker.invoke("thread", caller=_Caller(), timeout=1.0)
    assert worker.last_error.startswith("fatal:")


async def test_child_script_does_not_reference_host_module_names() -> None:
    """The child runs in a fresh ``-I`` interpreter and cannot import ``soapbot``.

    This guard exists because a real regression got through: ``_apply_limits`` was
    changed to use ``DEFAULT_PLUGIN_MEMORY_BYTES``, a name that exists only in the
    parent module. Inside the child it raised ``NameError``, which a bare
    ``except: pass`` swallowed — so every resource limit silently stopped being
    applied, and only the Linux job could notice. Checking the source here makes the
    mistake fail on every platform, immediately.
    """
    import ast

    from soapbot.plugins import supervisor as sup_mod

    child = sup_mod._CHILD_WORKER
    tree = ast.parse(child)  # also proves the embedded script is valid Python

    forbidden = {
        "DEFAULT_PLUGIN_MEMORY_BYTES",
        "sanitize_env",
        "IsolationError",
        "_kill_tree",
        "MAX_FRAME_BYTES",
        "WorkerConfig",
    }
    # Names, not substrings: these identifiers are mentioned in the child's comments
    # (explaining this very bug), so a text search would report a false positive.
    used = {node.id for node in ast.walk(tree) if isinstance(node, ast.Name)}
    leaked = sorted(used & forbidden)
    assert not leaked, (
        "the child script must not reference names from the host module; they do not "
        f"exist there and any NameError would be swallowed: {leaked}"
    )


async def test_the_reader_thread_failure_is_reproducible() -> None:
    """Pins the *shape* of the old failure so the diagnosis does not get lost.

    ``run_in_executor`` raising inside the read loop ends the process with code 1 and
    a traceback on stderr, with nothing at all on the protocol channel. That is what
    CI observed, and it is why the fix had to add a fatal frame rather than only
    remove the quota.
    """
    child = """
import asyncio

class Boom(RuntimeError):
    pass

async def _serve():
    print("ready", flush=True)
    loop = asyncio.get_running_loop()

    def _no_threads(*a, **k):
        raise Boom("can't start new thread")

    loop.run_in_executor = _no_threads
    await loop.run_in_executor(None, lambda: None)

asyncio.run(_serve())
"""
    proc = await asyncio.create_subprocess_exec(
        sys.executable,
        "-c",
        child,
        stdout=asyncio.subprocess.PIPE,
        stderr=asyncio.subprocess.PIPE,
    )
    out, err = await proc.communicate()

    assert proc.returncode == 1
    assert b"ready" in out
    assert b"can't start new thread" in err
