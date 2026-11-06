"""Regression tests for the plugin process / IPC boundary.

These pin the properties that are easy to lose in a refactor: a response belongs to
one specific request, a callback cannot be replayed, both ends agree on the frame
budget, stdout is drained even when nobody is calling, dead children are reaped, and
the number of children is bounded. The offline static gate in
``scripts/check_plugin_ipc.py`` guards the same invariants at source level; this file
guards them at runtime.
"""

from __future__ import annotations

import asyncio
import importlib.util
import json
import sys
from pathlib import Path

import pytest

from soapbot.plugins import isolation as iso
from soapbot.plugins import supervisor as sup
from soapbot.plugins.isolation import (
    MAX_FRAME_BYTES,
    IsolatedRunner,
    IsolationError,
    PluginCrashedError,
)
from soapbot.plugins.supervisor import PluginSupervisor, PluginWorker, WorkerConfig

SCRIPTS = Path(__file__).resolve().parents[1] / "scripts"


class _Caller:
    user_id = "1"
    role = "admin"
    session_key = "onebot11:group:555"
    display_name = "tester"
    scene = "group"
    group_id = "555"
    is_privileged = False


class _Writer:
    def __init__(self) -> None:
        self.written: list[bytes] = []

    def write(self, data: bytes) -> None:
        self.written.append(data)

    async def drain(self) -> None:
        return None


class _FakeProc:
    returncode = None

    def __init__(self, stdout=None) -> None:
        self.stdin = _Writer()
        self.stdout = stdout if stdout is not None else object()


def _worker(*, stdout=None, handler=None) -> tuple[PluginWorker, _FakeProc]:
    worker = PluginWorker(
        WorkerConfig(plugin="ipc-test", plugin_dir=Path(".")),
        surface_handler=handler or (lambda *a, **k: None),
    )
    proc = _FakeProc(stdout)
    worker._proc = proc
    worker._frames = asyncio.Queue()
    return worker, proc


def _load_script(name: str):
    path = SCRIPTS / name
    spec = importlib.util.spec_from_file_location(name.removesuffix(".py"), path)
    assert spec and spec.loader
    module = importlib.util.module_from_spec(spec)
    # dataclass resolves annotations through sys.modules; without this the two
    # script modules fail at import with a confusing NoneType.__dict__ error.
    sys.modules[spec.name] = module
    try:
        spec.loader.exec_module(module)
    except BaseException:
        sys.modules.pop(spec.name, None)
        raise
    return module


# --------------------------------------------------------------- correlation ids


async def test_a_result_with_a_foreign_id_is_never_returned(monkeypatch) -> None:
    """A stale or forged answer must not be handed to the current caller."""
    monkeypatch.setattr(sup.secrets, "token_hex", lambda _n: "rid-fixed")
    worker, _proc = _worker()
    await worker._frames.put(
        {"type": "result", "id": "attacker", "ok": True, "value": "forged"}
    )
    await worker._frames.put(
        {"type": "result", "id": "rid-fixed", "ok": True, "value": "real"}
    )

    assert await worker.invoke("ping", caller=_Caller(), timeout=2.0) == "real"
    assert worker._mismatched_frames == 1


async def test_a_callback_without_the_active_rid_is_refused_before_dispatch(
    monkeypatch,
) -> None:
    """The privileged surface handler is not even looked up for a stale callback."""
    monkeypatch.setattr(sup.secrets, "token_hex", lambda _n: "rid-fixed")
    seen: list[str] = []

    async def handler(plugin, surface, args, caller):
        seen.append(surface)
        return "should-not-run"

    worker, proc = _worker(handler=handler)
    await worker._frames.put(
        {
            "type": "call",
            "cid": 1,
            "rid": "stale",
            "surface": "memory.recall",
            "args": {},
        }
    )
    await worker._frames.put(
        {"type": "result", "id": "rid-fixed", "ok": True, "value": "done"}
    )

    assert await worker.invoke("ping", caller=_Caller(), timeout=2.0) == "done"
    assert seen == []
    assert b"request id mismatch" in b"".join(proc.stdin.written)


async def test_a_callback_with_the_active_rid_still_dispatches(monkeypatch) -> None:
    """Positive control: the new binding must not break legitimate callbacks."""
    monkeypatch.setattr(sup.secrets, "token_hex", lambda _n: "rid-fixed")
    seen: list[str] = []

    async def handler(plugin, surface, args, caller):
        seen.append(surface)
        return {"items": []}

    worker, proc = _worker(handler=handler)
    await worker._frames.put(
        {
            "type": "call",
            "cid": 1,
            "rid": "rid-fixed",
            "surface": "memory.recall",
            "args": {"query": "cat"},
        }
    )
    await worker._frames.put(
        {"type": "result", "id": "rid-fixed", "ok": True, "value": "done"}
    )

    assert await worker.invoke("ping", caller=_Caller(), timeout=2.0) == "done"
    assert seen == ["memory.recall"]
    assert b'"ok": true' in b"".join(proc.stdin.written)


# ------------------------------------------------------------------- frame budget


def test_both_child_scripts_share_the_parent_frame_budget() -> None:
    assert MAX_FRAME_BYTES == 4 * 1024 * 1024
    assert str(MAX_FRAME_BYTES) in sup._CHILD_WORKER
    assert str(MAX_FRAME_BYTES) in iso._CHILD_BOOTSTRAP
    assert "8 * 1024 * 1024" not in sup._CHILD_WORKER
    assert "__MAX_FRAME_BYTES__" not in sup._CHILD_WORKER
    assert "__MAX_FRAME_BYTES__" not in iso._CHILD_BOOTSTRAP


async def test_inbound_length_header_error_names_the_limit() -> None:
    reader = asyncio.StreamReader()
    reader.feed_data((MAX_FRAME_BYTES + 1).to_bytes(4, "big"))
    reader.feed_eof()
    with pytest.raises(IsolationError, match=f"limit {MAX_FRAME_BYTES}"):
        await sup._read_frame(reader)


async def test_outbound_frame_is_refused_with_actual_size_and_limit() -> None:
    writer = _Writer()
    with pytest.raises(sup.FrameTooLargeError) as info:
        await sup._write_frame(writer, {"value": "x" * (MAX_FRAME_BYTES + 10)})
    message = str(info.value)
    assert f"limit {MAX_FRAME_BYTES}" in message
    reported = int(message.split("frame of ", 1)[1].split(" bytes", 1)[0])
    assert reported > MAX_FRAME_BYTES
    assert writer.written == []


# -------------------------------------------------------------- stdout / process


async def test_idle_frame_flood_is_detected_and_aborted(monkeypatch) -> None:
    """A child writing frames with no caller must not fill host memory."""
    reader = asyncio.StreamReader()
    worker, proc = _worker(stdout=reader)
    worker._frames = asyncio.Queue(maxsize=sup._FRAME_QUEUE_SIZE)

    for index in range(12):
        payload = json.dumps(
            {"type": "log", "level": "info", "message": str(index)}
        ).encode()
        reader.feed_data(len(payload).to_bytes(4, "big") + payload)
    reader.feed_eof()

    killed: list[object] = []
    monkeypatch.setattr(sup, "_kill_tree", lambda p: killed.append(p))
    await worker._drain_stdout(proc, worker._frames)

    # The kill must be synchronous: awaiting proc.wait() from inside the reader
    # would deadlock on a child that is still writing into a full stdout pipe.
    assert killed == [proc]
    assert worker.last_error == "frame flood"
    assert worker._dead is True
    buffered = []
    while not worker._frames.empty():
        buffered.append(worker._frames.get_nowait())
    assert sup._CHANNEL_CLOSED in buffered


async def test_protocol_error_kills_the_child_and_poisons_no_worker(monkeypatch) -> None:
    """A broken frame must not leave an `alive` worker whose reader has stopped."""
    reader = asyncio.StreamReader()
    reader.feed_data((0xFFFFFFFF).to_bytes(4, "big"))
    reader.feed_eof()
    worker, proc = _worker(stdout=reader)
    killed: list[object] = []
    monkeypatch.setattr(sup, "_kill_tree", lambda p: killed.append(p))

    await worker._drain_stdout(proc, worker._frames)

    assert killed == [proc]
    assert worker._dead is True
    assert worker.last_error == "protocol error"


async def test_abort_never_waits_forever_for_a_stuck_child(monkeypatch) -> None:
    """The invoke lock must be releasable even if the child never delivers EOF."""
    class _StuckProc:
        returncode = None

        async def wait(self):
            await asyncio.Event().wait()

    worker, _proc = _worker()
    proc = _StuckProc()
    worker._proc = proc
    monkeypatch.setattr(sup, "_kill_tree", lambda _p: None)

    await asyncio.wait_for(worker._abort("timeout"), timeout=2.5)
    assert worker.last_error == "timeout"


async def test_unregister_releases_capacity_after_unload() -> None:
    supervisor = PluginSupervisor(max_workers=1)
    supervisor.bind_surface_handler(lambda *a: None)
    supervisor.register(WorkerConfig(plugin="a", plugin_dir=Path(".")))
    with pytest.raises(IsolationError, match="limit reached"):
        supervisor.register(WorkerConfig(plugin="b", plugin_dir=Path(".")))
    await supervisor.stop("a")
    supervisor.unregister("a")
    supervisor.register(WorkerConfig(plugin="b", plugin_dir=Path(".")))
    assert [row.plugin for row in supervisor.health()] == ["b"]


async def test_exit_watcher_reaps_an_idle_death_and_is_generation_safe() -> None:
    class _WaitProc:
        def __init__(self, code: int) -> None:
            self.code = code

        async def wait(self) -> int:
            return self.code

    worker, _proc = _worker()
    proc = _WaitProc(7)
    queue = asyncio.Queue()
    worker._proc = proc
    worker._frames = queue

    await worker._watch_exit(proc, queue)
    assert worker._dead is True
    assert worker.last_error == "exit:7"
    assert queue.get_nowait() is sup._CHANNEL_CLOSED

    # A watcher from a previous process generation must not mark a new worker dead.
    worker._dead = False
    worker.last_error = ""
    worker._proc = _WaitProc(0)
    await worker._watch_exit(proc, queue)
    assert worker._dead is False
    assert worker.last_error == ""


def test_worker_cap_is_bounded_and_rejects_invalid_values() -> None:
    for bad in (0, -1, 65, True, "16"):
        with pytest.raises(IsolationError):
            PluginSupervisor(max_workers=bad)

    supervisor = PluginSupervisor(max_workers=2)
    supervisor.bind_surface_handler(lambda *a: None)
    for name in ("a", "b"):
        supervisor.register(WorkerConfig(plugin=name, plugin_dir=Path(".")))
    with pytest.raises(IsolationError, match="limit reached"):
        supervisor.register(WorkerConfig(plugin="c", plugin_dir=Path(".")))
    health = supervisor.health()
    assert len(health) == 2
    assert all(row.max_workers == 2 and row.live_workers == 0 for row in health)
    assert supervisor.max_workers == 2


# --------------------------------------------------------------- one-shot runner


async def test_one_shot_rejects_bad_attr_and_oversize_request(tmp_path) -> None:
    (tmp_path / "main.py").write_text("class Plugin:\n    pass\n", encoding="utf-8")
    runner = IsolatedRunner(timeout=3.0)
    with pytest.raises(IsolationError, match="invalid plugin entry attribute"):
        await runner.run_entry(plugin_dir=tmp_path, attr="Plugin.__class__")
    with pytest.raises(IsolationError, match="refusing to send request"):
        await runner.run_entry(
            plugin_dir=tmp_path,
            attr="Plugin",
            payload={"blob": "x" * (MAX_FRAME_BYTES + 1)},
        )


async def test_one_shot_child_refuses_an_invalid_entry_file(tmp_path) -> None:
    """The child re-checks the path; a non-file main.py never reaches importlib."""
    (tmp_path / "main.py").mkdir()
    runner = IsolatedRunner(timeout=3.0)
    with pytest.raises(PluginCrashedError):
        await runner.run_entry(plugin_dir=tmp_path, attr="Plugin")


async def test_one_shot_reply_is_bounded_before_buffering(tmp_path) -> None:
    """A plugin writing junk to fd 1 cannot make the host buffer an unbounded reply."""
    (tmp_path / "main.py").write_text(
        "import os\n"
        "class Plugin:\n"
        "    def handler(self, caller, args):\n"
        "        os.write(1, b'\\xff\\xff\\xff\\xff')\n"
        "        os._exit(0)\n",
        encoding="utf-8",
    )
    runner = IsolatedRunner(timeout=3.0)
    with pytest.raises(IsolationError, match=f"limit {MAX_FRAME_BYTES}"):
        await runner.run_entry(
            plugin_dir=tmp_path,
            attr="Plugin",
            handler="handler",
            payload={"caller": {}, "args": []},
        )


# ------------------------------------------------------------------ ops gates


def test_guard_self_test_is_read_only_and_asserts_parsing() -> None:
    guard = _load_script("plugin_worker_guard.py")
    report = guard.self_test()
    assert report.worker_processes == 2
    assert report.zombies == 1
    assert report.container_status == "Up (healthy)"
    assert report.restart_performed is False
    assert guard.main(["--self-test", "--json"]) == 0


def test_offline_audit_gate_detects_a_removed_invariant(monkeypatch) -> None:
    audit = _load_script("check_plugin_ipc.py")
    assert all(result.ok for result in audit.collect())

    real_text = audit._text

    def tampered(path):
        text = real_text(path)
        if path == audit.SUPERVISOR:
            return text.replace("if len(data) > MAX_FRAME_BYTES:", "if False:")
        return text

    monkeypatch.setattr(audit, "_text", tampered)
    results = audit.collect()
    assert any(not r.ok and r.code == "ipc.outbound-cap" for r in results)


def test_authorization_stays_in_the_parent() -> None:
    assert "CapabilityGuard" not in sup._CHILD_WORKER
    assert "ALLOWED_SURFACES" in Path(sup.__file__).read_text(encoding="utf-8")
    assert "_surface_handler" in Path(sup.__file__).read_text(encoding="utf-8")
