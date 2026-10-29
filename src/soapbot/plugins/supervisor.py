"""Resident plugin workers with host-side authorization.

Why a second module when ``isolation.py`` already runs subprocesses
--------------------------------------------------------------
``IsolatedRunner`` is a *one-shot* primitive: spawn, run one entry point, exit. That
contains crashes, but it cannot host a plugin, because a plugin has a lifecycle —
``setup()`` registers commands, and those commands are then invoked thousands of
times. Spawning per call would re-run ``setup`` on every message.

This module keeps a worker process **resident** and gives it a *bidirectional* pipe,
which is what makes the security story work::

    child (plugin)                      parent (host)
    --------------                      -------------
    ctx.memory.recall("cat")   --->     capability check   <-- unreachable from child
                                        scope := caller's session
                                        real MemoryStore query
                               <---     result or "denied"

The critical property: **the capability check and the session scope live in the
parent**. In-process, a plugin could ``import`` the guard and rewrite it (isolation
review defect I1 — mitigated by sealing, but sealing is a speed bump, not a
boundary). Here the guard is not in the child's address space at all, and the scope
is supplied by the parent, so a compromised plugin cannot express "read group 999":
the wire protocol has no field for it, exactly like ``ctx.memory.recall`` has no
``scope`` parameter.

Guaranteed (and tested)
-----------------------
* a plugin cannot reach host memory, DB handles, adapters or the audit log;
* a plugin crash / hang / fork bomb is contained to its own process tree;
* every privileged operation is authorized in the parent, per call;
* a plugin cannot widen its session scope, because it cannot name one.

Not guaranteed (same-uid process — stated, not hidden)
------------------------------------------------------
* filesystem and network reach. See ``docs/deploy-layer.md`` §残余风险 and the
  container profile that closes it. Confining cwd and stripping the environment
  remove the *accidental* paths; they do not remove an absolute path.

Failure handling
----------------
Workers are supervised: crash -> restart with exponential backoff; repeated crashes
inside a window -> circuit opens and the plugin stops being restarted, because a
plugin that dies on every message would otherwise become a restart loop costing more
CPU than serving traffic. Recovery is explicit, never silent.

Protocol (both directions, 4-byte big-endian length + UTF-8 JSON)
-----------------------------------------------------------------
parent -> child : {"type":"invoke","id":n,"handler":str,"caller":{...},"args":[...]}
parent -> child : {"type":"reply","cid":n,"ok":bool,"value":...,"error":str}
parent -> child : {"type":"shutdown"}
child -> parent : {"type":"ready","ok":bool,"commands":[...],"api":{...}}
child -> parent : {"type":"result","id":n,"ok":bool,"value":...,"error":str}
child -> parent : {"type":"call","cid":n,"surface":str,"args":{}}
child -> parent : {"type":"log","level":str,"message":str}
"""

from __future__ import annotations

import asyncio
import contextlib
import json
import logging
import sys
import time
from collections import deque
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from soapbot.plugins.isolation import (
    DEFAULT_PLUGIN_MEMORY_BYTES,
    MAX_FRAME_BYTES,
    IsolationError,
    PluginCrashedError,
    PluginTimeoutError,
    _kill_tree,
    sanitize_env,
)
from soapbot.plugins.sandbox import CapabilityDeniedError

logger = logging.getLogger(__name__)

#: Restart policy. Deliberately conservative: plugin crashes should be visible, not
#: papered over with an infinite retry loop.
MAX_RESTARTS_IN_WINDOW = 3
RESTART_WINDOW_SECONDS = 60.0
BACKOFF_BASE = 0.25
BACKOFF_CAP = 8.0

#: Surfaces a plugin may request from the host. Anything not in this set is refused
#: before it reaches any handler — the wire is an allowlist, so a new surface cannot
#: be exposed by accident.
ALLOWED_SURFACES = frozenset(
    {
        "memory.recall",
        "memory.about_me",
        "kb.search",
        "kb.list_documents",
        "session.view",
        "send.message",
        "http.request",
        "storage.get",
        "storage.set",
        "storage.delete",
        "log.write",
    }
)

#: Argument names the parent refuses to accept from the child, because accepting one
#: would hand the plugin control of a security decision. ``scope`` is the important
#: one: a plugin that could name a session could read another group's memories.
_FORBIDDEN_ARG_KEYS = frozenset(
    {"scope", "session_key", "plugin", "caller", "grant", "approved", "capability"}
)


class SurfaceDeniedError(RuntimeError):
    """The host refused a callback. Reported back to the child as an error string."""


@dataclass(slots=True)
class WorkerConfig:
    """Everything the child needs to boot. Sent once, then never updated."""

    plugin: str
    plugin_dir: Path
    attr: str = "Plugin"
    timeout: float = 8.0
    memory_bytes: int = DEFAULT_PLUGIN_MEMORY_BYTES
    #: Extra environment for the child. Host-controlled; the plugin never sees it
    #: being built and cannot add to it.
    extra_env: dict[str, str] = field(default_factory=dict)


class WorkerCrashedError(PluginCrashedError):
    """The worker died while a call was in flight."""


# --------------------------------------------------------------------------- child

#: Runs in the resident child. Kept as a string so a fresh ``-I`` interpreter can
#: execute it without importing the host package (which it must not be able to do).
_CHILD_WORKER = r'''
import asyncio, importlib.util, inspect, json, os, sys

_stdin = sys.stdin.buffer
_stdout = sys.stdout.buffer


def _read_frame():
    head = _stdin.read(4)
    if len(head) < 4:
        return None
    n = int.from_bytes(head, "big")
    if n <= 0 or n > 8 * 1024 * 1024:
        return None
    try:
        return json.loads(_stdin.read(n).decode("utf-8"))
    except Exception:
        return None


def _send(msg):
    try:
        data = json.dumps(msg, ensure_ascii=False, default=str).encode("utf-8")
    except Exception:
        data = json.dumps({"type": "log", "level": "error",
                           "message": "unserialisable frame"}).encode("utf-8")
    _stdout.write(len(data).to_bytes(4, "big"))
    _stdout.write(data)
    _stdout.flush()


_next_cid = [0]


def _call(surface, args):
    """Ask the host to do something privileged. Blocks until it answers.

    The child has no way to authorize itself: it can only *request*. Every request
    lands in the parent dispatcher, which re-checks the capability and supplies the
    session scope from the caller it recorded. That is why the pipe is bidirectional.
    """
    _next_cid[0] += 1
    cid = _next_cid[0]
    _send({"type": "call", "cid": cid, "surface": surface, "args": args})
    while True:
        frame = _read_frame()
        if frame is None:
            raise RuntimeError("host closed the channel")
        if frame.get("type") == "reply" and frame.get("cid") == cid:
            if not frame.get("ok"):
                raise PermissionError(frame.get("error") or "denied by host")
            return frame.get("value")
        # A reply for a previous cid cannot arrive (calls are serial), but skipping
        # unknown frames keeps the child tolerant of protocol evolution.


class _RemoteMemory:
    def __init__(self):
        self.available = True

    async def recall(self, query, limit=5):
        return _call("memory.recall", {"query": query, "limit": limit})

    async def about_me(self, limit=5):
        return _call("memory.about_me", {"limit": limit})


class _RemoteKB:
    def __init__(self):
        self.available = True

    async def search(self, query, limit=5):
        return _call("kb.search", {"query": query, "limit": limit})

    async def list_documents(self):
        return _call("kb.list_documents", {})


class _RemoteSession:
    def __getattr__(self, name):
        # Fetched per access so the snapshot reflects the current invocation rather
        # than whatever was true when setup() ran.
        view = _call("session.view", {})
        if name in view:
            return view[name]
        raise AttributeError(name)

    def to_dict(self):
        return _call("session.view", {})


class _RemoteStorage:
    async def get(self, key, default=None):
        return _call("storage.get", {"key": key, "default": default})

    async def set(self, key, value):
        return _call("storage.set", {"key": key, "value": value})

    async def delete(self, key):
        return _call("storage.delete", {"key": key})


class _RemoteCtx:
    """The façade a plugin sees inside the worker.

    Deliberately narrower than the in-process ``PluginContext``: no guard, no store,
    no ledger, no event loop is reachable from here. Anything privileged is a request
    to the host.
    """

    def __init__(self):
        self.memory = _RemoteMemory()
        self.kb = _RemoteKB()
        self.session = _RemoteSession()
        self.storage = _RemoteStorage()
        self._commands = {}
        self._api = {}

    def command(self, name, *, description="", usage="", min_role=None):
        def deco(fn):
            self._commands[name] = fn
            # ``min_role`` crosses as a plain string. The host re-checks it against
            # its own Role enum before dispatch; sending the value here only lets the
            # host describe the command in the UI. A plugin cannot self-authorise by
            # declaring a *lower* role, because the host compares against the caller's
            # resolved role regardless of what the plugin said.
            self._api[name] = {
                "description": description,
                "usage": usage,
                "min_role": str(min_role) if min_role is not None else "",
            }
            return fn

        return deco

    def tool(self, name, *, description="", parameters=None):
        """Tools are registered as commands too, with a marker.

        In isolated mode there is no separate tool table to maintain: the host asks
        the worker for a name and a JSON schema, and dispatch is identical to a
        command. That is one less surface to keep consistent between the two modes.
        """

        def deco(fn):
            self._commands[name] = fn
            self._api[name] = {
                "description": description,
                "usage": "",
                "kind": "tool",
                "parameters": parameters or {},
            }
            return fn

        return deco

    def message_hook(self, fn):
        return fn

    async def send(self, session_key, text):
        # session_key is *requested*, not trusted: the host re-checks it against the
        # ledger it owns. A plugin asking for another group gets PermissionError.
        return _call("send.message", {"session_key": session_key, "text": text})

    #: Raw escape hatch, present so the wire can be exercised end to end (including
    #: by a hostile plugin). It grants nothing: every request still lands in the
    #: parent's dispatcher, which re-checks the capability and rejects any argument
    #: the plugin is not allowed to supply. Exposing it is deliberate — a hostile
    #: plugin will find the pipe anyway (it can ``os.write(1, ...)``), so the honest
    #: design is to make the protocol itself safe rather than to hide it.
    request = staticmethod(lambda surface, args: _call(surface, args))

    async def http(self, *args, **kwargs):
        return _call(
            "http.request",
            {"args": [str(a) for a in args],
             "kwargs": {k: str(v) for k, v in kwargs.items()}},
        )

    def log(self, message, level="info"):
        _send({"type": "log", "level": level, "message": str(message)[:500]})


def _apply_limits():
    """Contain this worker only. Two limits were actively harmful here.

    ``RLIMIT_NPROC = 64`` is gone. It is counted per **real uid across the whole
    system**, not per process, and it counts *threads* as well as processes. On a
    shared account — every CI runner, and any host running several services as one
    user — the quota is already partly spent before this child starts, so the cap
    throttles bystanders instead of catching a fork bomb. Worse, the child needs a
    thread for its own frame reader: the first ``run_in_executor`` call creates one,
    and once the uid is at its quota that raises ``RuntimeError: can't start new
    thread`` inside the read loop. Measured shape: the worker reports ready, then dies
    with exit code 1 about ten milliseconds later on the first invoke, with the
    traceback only on stderr. That is precisely the intermittent Linux CI failure.
    Fork containment is ``killpg``'s job (see ``_kill_tree``), and it is already
    covered by test_spawned_helpers_die_with_the_worker.

    ``RLIMIT_AS`` is raised, not removed, because it counts **virtual** address space
    and a bare CPython already reserves a few hundred MiB of it: 256 MiB left no room
    for an 8 MiB thread stack, so a perfectly healthy plugin could be killed by its
    own memory limit at the first thread creation.
    """
    try:
        import resource
    except ImportError:
        # Windows: no rlimits at all. The only expected way to get here.
        return

    # The default MUST stay a literal. This function is part of _CHILD_WORKER, a
    # standalone script executed by a fresh ``-I`` interpreter that cannot import the
    # host package — referencing DEFAULT_PLUGIN_MEMORY_BYTES here raised NameError,
    # which a bare ``except: pass`` swallowed, so *every* limit silently stopped being
    # applied. Caught by test_child_has_room_for_its_own_memory.
    try:
        cap = int(os.environ.get("SOAPBOT_PLUGIN_MEM_BYTES") or 512 * 1024 * 1024)
        resource.setrlimit(resource.RLIMIT_AS, (cap, cap))
        resource.setrlimit(resource.RLIMIT_CORE, (0, 0))
    except Exception:
        # Visible rather than silent: this is a containment failure, and the host now
        # keeps the stderr tail so it can be read back later.
        import traceback
        traceback.print_exc(file=sys.stderr)


class _StubPlugin:
    """Stand-in for ``soapbot.plugins.base.Plugin`` inside the worker.

    Plugins are written as ``from soapbot.plugins.base import Plugin`` because that
    is what the in-process API offers, and forcing a different import for isolated
    mode would mean every plugin has two code paths — the kind of duplication where
    only one path gets tested.

    But the worker runs with ``-I`` and without ``soapbot`` on the path: importing the
    real package would pull in the database engine, the HTTP app and the audit log,
    which is precisely what the process boundary exists to keep away. So the worker
    installs this stub under those module names instead. A plugin that only needs the
    base class works unchanged; a plugin that imports ``soapbot.core.builder`` gets
    ModuleNotFoundError, which is the correct outcome.
    """

    async def setup(self, ctx):
        return None

    async def teardown(self):
        return None


def _install_stubs():
    """Install the tiny compatibility surface plugins import, without the host.

    The goal is that a plugin needs **one** source file that works in both modes.
    Anything a plugin legitimately touches is here; anything that would pull the
    host in (``soapbot.core``, ``soapbot.api``, ``soapbot.memory``) is absent on
    purpose, so an attempt to reach it fails at import with ModuleNotFoundError
    rather than silently working.

    Keep this list to *data types and constants*. If it grows behaviour, it becomes
    a second implementation of the host API, which is how the two drift apart.
    """
    import enum
    import types

    if "soapbot" in sys.modules:
        return

    pkg = types.ModuleType("soapbot")
    plugins = types.ModuleType("soapbot.plugins")
    security = types.ModuleType("soapbot.security")

    base = types.ModuleType("soapbot.plugins.base")
    base.Plugin = _StubPlugin

    ctx_mod = types.ModuleType("soapbot.plugins.context")
    ctx_mod.CallerContext = dict
    ctx_mod.PluginResult = dict
    # ``PluginContext`` is imported only for the type annotation in most plugins.
    # A stub class keeps ``from ... import PluginContext`` working; the real object
    # never crosses the boundary.
    ctx_mod.PluginContext = type("PluginContext", (), {})

    principal = types.ModuleType("soapbot.security.principal")

    class _Role(enum.StrEnum):
        """Mirror of ``soapbot.security.principal.Role``.

        Values must match the host's exactly: a plugin declaring ``min_role=Role.ADMIN``
        sends the string "admin" over the wire, and the host compares it against its
        own enum. If the two ever disagree, an admin-only command would silently
        become member-accessible, so the host-side comparison is what actually decides
        and this copy is only a convenience for plugin authors.
        """

        ANONYMOUS = "anonymous"
        GUEST = "guest"
        MEMBER = "member"
        ADMIN = "admin"
        OWNER = "owner"

    principal.Role = _Role

    plugins.base = base
    plugins.context = ctx_mod
    security.principal = principal
    pkg.plugins = plugins
    pkg.security = security

    sys.modules["soapbot"] = pkg
    sys.modules["soapbot.plugins"] = plugins
    sys.modules["soapbot.plugins.base"] = base
    sys.modules["soapbot.plugins.context"] = ctx_mod
    sys.modules["soapbot.security"] = security
    sys.modules["soapbot.security.principal"] = principal


async def _serve():
    boot = _read_frame()
    if not boot:
        return
    _apply_limits()
    _install_stubs()
    sys.path.insert(0, boot["plugin_dir"])
    ctx = _RemoteCtx()
    try:
        spec = importlib.util.spec_from_file_location(
            "plugin_main", os.path.join(boot["plugin_dir"], "main.py")
        )
        mod = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(mod)
        attr = boot.get("attr") or "Plugin"
        cls = getattr(mod, attr, None)
        if cls is None or cls is _StubPlugin:
            # ``attr`` defaulted to "Plugin", which resolves to the *imported base
            # class* rather than the plugin. Binding that would silently run the stub's
            # no-op setup: the worker would come up reporting zero commands and every
            # call would fail with "no such handler" — a configuration bug that looks
            # exactly like a broken plugin.
            cls = None
            for value in vars(mod).values():
                if (
                    isinstance(value, type)
                    and issubclass(value, _StubPlugin)
                    and value is not _StubPlugin
                ):
                    cls = value
                    break
            if cls is None:
                raise RuntimeError("no plugin class found in main.py")
        inst = cls()
        setup = getattr(inst, "setup", None)
        if setup is not None:
            out = setup(ctx)
            if inspect.isawaitable(out):
                await out
    except BaseException as exc:
        _send({"type": "ready", "ok": False, "error": type(exc).__name__})
        return

    _send({"type": "ready", "ok": True,
           "commands": sorted(ctx._commands), "api": ctx._api})

    loop = asyncio.get_running_loop()
    while True:
        # ``run_in_executor`` creates a thread on its first call and that is the one
        # place in this loop that can fail for environmental reasons (thread or memory
        # quota). Unprotected, the exception escaped ``_serve``, escaped
        # ``asyncio.run``, and the process died with code 1 having said nothing on the
        # protocol channel — the host could only report "died (code=1)". Reporting it
        # as a frame turns a mystery into a diagnosis.
        try:
            frame = await loop.run_in_executor(None, _read_frame)
        except BaseException as exc:
            _send({"type": "fatal",
                   "error": type(exc).__name__ + ": " + str(exc)[:200]})
            return
        if frame is None:
            return
        kind = frame.get("type")
        if kind == "shutdown":
            return
        if kind != "invoke":
            continue
        name = frame.get("handler")
        fn = ctx._commands.get(name)
        if fn is None:
            _send({"type": "result", "id": frame.get("id"), "ok": False,
                   "error": "no such handler"})
            continue
        caller = frame.get("caller") or {}
        args = frame.get("args") or []
        # Tools and commands share the invoke frame but not the argument shape: a
        # command receives a list of words, a tool receives one JSON object. The
        # host wraps tool arguments in a one-element list to reuse the frame, so
        # unwrap it here. Without this, a tool handler written as
        # ``def handler(caller, args: dict)`` would receive ``[dict]`` and every
        # ``args["x"]`` lookup would raise TypeError — the tool would appear in the
        # model's list and fail on first use, in isolated mode only.
        if ctx._api.get(name, {}).get("kind") == "tool":
            args = args[0] if args and isinstance(args[0], dict) else {}
        try:
            try:
                params = list(inspect.signature(fn).parameters.values())
            except (TypeError, ValueError):
                params = []
            if len(params) >= 2:
                out = fn(caller, args)
            elif len(params) == 1:
                out = fn(caller)
            else:
                out = fn()
            if inspect.isawaitable(out):
                out = await out
            if not isinstance(out, (str, int, float, bool, type(None), dict, list)):
                _send({"type": "result", "id": frame.get("id"), "ok": False,
                       "error": "non-serialisable result"})
                continue
            _send({"type": "result", "id": frame.get("id"), "ok": True, "value": out})
        except BaseException as exc:
            _send({"type": "result", "id": frame.get("id"), "ok": False,
                   "error": type(exc).__name__})


asyncio.run(_serve())
'''


# -------------------------------------------------------------------------- parent


async def _read_frame(reader: asyncio.StreamReader) -> dict[str, Any] | None:
    """Read one length-prefixed frame. ``None`` means clean EOF."""
    try:
        header = await reader.readexactly(4)
    except asyncio.IncompleteReadError:
        return None
    length = int.from_bytes(header, "big")
    if length <= 0 or length > MAX_FRAME_BYTES:
        raise IsolationError(f"refusing frame of {length} bytes")
    body = await asyncio.wait_for(reader.readexactly(length), timeout=30)
    return json.loads(body.decode("utf-8"))


async def _write_frame(writer: asyncio.StreamWriter, msg: dict[str, Any]) -> None:
    data = json.dumps(msg, ensure_ascii=False, default=str).encode("utf-8")
    writer.write(len(data).to_bytes(4, "big"))
    writer.write(data)
    await writer.drain()


def _caller_payload(caller: Any) -> dict[str, Any]:
    """The caller view a worker may see: scalars only, no principal or permissions."""
    if caller is None:
        return {}
    return {
        "user_id": getattr(caller, "user_id", ""),
        "display_name": getattr(caller, "display_name", ""),
        "role": str(getattr(caller, "role", "")),
        "scene": getattr(caller, "scene", ""),
        "group_id": getattr(caller, "group_id", ""),
        "is_privileged": bool(getattr(caller, "is_privileged", False)),
    }


class PluginWorker:
    """One resident plugin process, with host-side authorization on every callback.

    ``surface_handler`` is the host dispatcher: it receives
    ``(surface: str, args: dict, caller)`` and must perform the capability check
    itself. This class does not know about capabilities — it only guarantees that
    every callback passes through that one function, so there is a single place where
    authorization is decided and a single place to audit.
    """

    def __init__(
        self,
        config: WorkerConfig,
        *,
        surface_handler,
        stderr_sink=None,
    ) -> None:
        self.config = config
        # The handler receives the plugin name from *this* worker, not from the
        # frame. Identity comes from which pipe the request arrived on, which a
        # plugin cannot forge by putting a name in the JSON body.
        self._surface_handler = surface_handler
        self._stderr_sink = stderr_sink or (lambda line: None)
        #: Last few stderr lines, kept so a crash can explain itself.
        #:
        #: Without this, a worker that dies from an uncaught exception is reported as
        #: "died (code=1)" and nothing else: the traceback went to stderr, and stderr
        #: was only forwarded to a DEBUG logger. That is how a real Linux-only crash
        #: survived several CI rounds looking like "flaky".
        self._stderr_tail: deque[str] = deque(maxlen=40)
        self._proc: asyncio.subprocess.Process | None = None
        self._stderr_task: asyncio.Task | None = None
        self.commands: list[str] = []
        self.api: dict[str, Any] = {}
        self.started_at: float = 0.0
        self.invocations = 0
        self.last_error: str = ""
        #: Set as soon as the pipe reports EOF or a kill is issued. See ``alive``.
        self._dead: bool = False

    @property
    def alive(self) -> bool:
        """Whether the worker can still serve a call.

        ``returncode is None`` alone is not enough: after a child calls
        ``os._exit``, the kernel has reaped it but the event loop may not have
        delivered the exit notification yet, so ``returncode`` stays ``None`` for a
        tick. Treating that as alive makes the supervisor hand calls to a dead pipe
        and — worse — makes health reports say a crashed plugin is fine. ``_dead`` is
        set the moment a frame read hits EOF, which is the earliest reliable signal.
        """
        if self._dead:
            return False
        return self._proc is not None and self._proc.returncode is None

    async def start(self, *, timeout: float = 20.0) -> None:
        if self.alive:
            return
        self._dead = False
        env = sanitize_env(
            extra={
                "SOAPBOT_PLUGIN_MEM_BYTES": str(self.config.memory_bytes),
                **self.config.extra_env,
            }
        )
        try:
            self._proc = await asyncio.create_subprocess_exec(
                sys.executable,
                "-I",
                "-c",
                _CHILD_WORKER,
                stdin=asyncio.subprocess.PIPE,
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE,
                env=env,
                # Own session/group so a kill reaches grandchildren (measured: a
                # plugin could spawn 20 helpers that survived the parent).
                cwd=str(self.config.plugin_dir),
                start_new_session=(sys.platform != "win32"),
            )
        except OSError as exc:  # pragma: no cover - environment dependent
            raise IsolationError(f"could not start plugin worker: {exc}") from exc

        assert self._proc.stdin and self._proc.stdout and self._proc.stderr
        # Drain stderr unconditionally. A child writing more than the pipe buffer
        # blocks on its next write, which looks exactly like a plugin hang — a
        # self-inflicted deadlock misread as malicious behaviour.
        self._stderr_task = asyncio.create_task(self._drain_stderr())

        await _write_frame(
            self._proc.stdin,
            {
                "plugin": self.config.plugin,
                "plugin_dir": str(self.config.plugin_dir),
                "attr": self.config.attr,
            },
        )
        try:
            ready = await asyncio.wait_for(_read_frame(self._proc.stdout), timeout=timeout)
        except TimeoutError:
            _kill_tree(self._proc)
            with contextlib.suppress(Exception):
                await self._proc.wait()
            raise PluginTimeoutError("plugin setup did not finish in time") from None
        if ready is None:
            raise WorkerCrashedError("plugin worker died during setup")
        if not ready.get("ok"):
            raise WorkerCrashedError(f"plugin setup failed: {ready.get('error', 'error')}")
        self.commands = list(ready.get("commands") or [])
        self.api = dict(ready.get("api") or {})
        self.started_at = time.time()
        logger.info(
            "plugin worker up plugin=%s pid=%s commands=%d",
            self.config.plugin,
            self._proc.pid,
            len(self.commands),
        )

    async def _drain_stderr(self) -> None:
        assert self._proc and self._proc.stderr
        while True:
            try:
                line = await self._proc.stderr.readline()
            except (asyncio.CancelledError, ValueError):
                return
            if not line:
                return
            text = line.decode("utf-8", "replace").rstrip("\r\n")
            # Retained before redaction as well: the sink is what decides what is
            # safe to *log*, but the tail is only ever shown through the same
            # redaction at crash time, so keeping the raw line here adds no exposure.
            self._stderr_tail.append(text[:500])
            # Never log raw stderr: it is plugin-authored and routinely contains
            # paths, tokens or another user's data. The sink redacts.
            with contextlib.suppress(Exception):
                self._stderr_sink(text[:500])

    async def _await_stderr_settled(self) -> None:
        """Wait for the stderr drain to reach EOF so a crash can be explained."""
        task = self._stderr_task
        if task is not None and not task.done():
            await asyncio.shield(task)

    def crash_tail(self, limit: int = 8) -> list[str]:
        """Recent stderr lines, redacted, newest last.

        Redaction is not optional here: stderr is plugin-controlled and this text is
        surfaced in an exception message, which lands in API responses and CI logs.
        """
        from soapbot.security.injection import redact

        out: list[str] = []
        for line in list(self._stderr_tail)[-limit:]:
            if not line.strip():
                continue
            with contextlib.suppress(Exception):
                line = redact(line)
            out.append(line[:300])
        return out

    async def stop(self, *, timeout: float = 5.0) -> None:
        proc = self._proc
        if proc is None:
            return
        self._dead = True
        if proc.returncode is None:
            with contextlib.suppress(Exception):
                assert proc.stdin
                await _write_frame(proc.stdin, {"type": "shutdown"})
            try:
                await asyncio.wait_for(proc.wait(), timeout=timeout)
            except TimeoutError:
                _kill_tree(proc)
                with contextlib.suppress(Exception):
                    await proc.wait()
        if self._stderr_task is not None:
            self._stderr_task.cancel()
            with contextlib.suppress(Exception):
                await self._stderr_task
            self._stderr_task = None
        self._proc = None

    async def invoke(
        self,
        handler: str,
        *,
        caller: Any,
        # ``list[Any]``, not ``list[str]``: a command's arguments are words, but a
        # tool's argument is one JSON object. Coercing that to ``str`` would either
        # lose the structure or force the worker to re-parse it.
        args: list[Any] | None = None,
        timeout: float | None = None,
    ) -> Any:
        """Call ``handler`` in the worker, proxying its callbacks through the host.

        The read loop is the security-relevant part: a callback is *never* answered
        locally. It goes to ``surface_handler``, which re-checks the capability and
        supplies the scope.
        """
        if not self.alive:
            raise WorkerCrashedError("plugin worker is not running")
        proc = self._proc
        assert proc and proc.stdin and proc.stdout

        self.invocations += 1
        await _write_frame(
            proc.stdin,
            {
                "type": "invoke",
                "id": self.invocations,
                "handler": handler,
                "caller": _caller_payload(caller),
                "args": list(args or []),
            },
        )

        limit = timeout if timeout is not None else self.config.timeout
        deadline = time.monotonic() + limit
        while True:
            remaining = deadline - time.monotonic()
            if remaining <= 0:
                await self._abort("timeout")
                raise PluginTimeoutError(
                    f"plugin {self.config.plugin} did not answer within {limit:.1f}s"
                )
            try:
                frame = await asyncio.wait_for(_read_frame(proc.stdout), timeout=remaining)
            except TimeoutError:
                await self._abort("timeout")
                raise PluginTimeoutError(
                    f"plugin {self.config.plugin} did not answer in time"
                ) from None
            except (asyncio.IncompleteReadError, IsolationError, ValueError):
                frame = None

            if frame is None:
                # EOF is the earliest reliable death signal; record it before the
                # event loop has necessarily noticed the exit.
                self._dead = True
                code = proc.returncode
                with contextlib.suppress(Exception):
                    await asyncio.wait_for(proc.wait(), timeout=1.0)
                    code = proc.returncode
                self.last_error = f"crash:{code}"
                # The stderr drain task is asynchronous and may still be behind the
                # pipe's EOF, so give it a moment: the traceback explaining a code=1
                # exit is the single most useful line in the whole failure, and
                # reporting "died (code=1)" with it omitted is what made a real
                # Linux-only crash look like flakiness for several CI rounds.
                # ``CancelledError`` is a BaseException, so suppress(Exception) alone
                # would let a cancelled drain task propagate out of the crash path and
                # replace the real diagnosis with a cancellation.
                with contextlib.suppress(asyncio.CancelledError, Exception):
                    await asyncio.wait_for(self._await_stderr_settled(), timeout=1.0)
                tail = self.crash_tail()
                logger.error(
                    "plugin worker crashed plugin=%s code=%s stderr=%s",
                    self.config.plugin,
                    code,
                    " | ".join(tail) if tail else "(empty)",
                )
                detail = f" (code={code})"
                if tail:
                    detail += f"; stderr tail: {' | '.join(tail)}"
                raise WorkerCrashedError(
                    f"plugin worker {self.config.plugin} died{detail}"
                )

            kind = frame.get("type")
            if kind == "result":
                if not frame.get("ok"):
                    raise WorkerCrashedError(f"plugin reported {frame.get('error', 'error')}")
                return frame.get("value")

            if kind == "fatal":
                # The child hit something it could not survive and said so before
                # exiting. Report its words: they are the whole diagnosis, and the
                # alternative (waiting for EOF) yields only a numeric exit code.
                self._dead = True
                self.last_error = f"fatal:{frame.get('error', 'unknown')}"
                logger.error(
                    "plugin worker fatal plugin=%s err=%s",
                    self.config.plugin,
                    self.last_error,
                )
                raise WorkerCrashedError(
                    f"plugin worker {self.config.plugin} failed: "
                    f"{frame.get('error', 'unknown')}"
                )

            if kind == "log":
                logger.debug(
                    "plugin log plugin=%s level=%s msg=%s",
                    self.config.plugin,
                    frame.get("level"),
                    str(frame.get("message", ""))[:300],
                )
                continue

            if kind == "call":
                await self._handle_callback(proc, frame, caller)
                continue

            # Unknown frame types are ignored rather than fatal: a newer child
            # protocol must not wedge an older host.

    async def _abort(self, reason: str) -> None:
        proc = self._proc
        if proc is None:
            return
        self.last_error = reason
        self._dead = True
        _kill_tree(proc)
        with contextlib.suppress(Exception):
            await proc.wait()

    async def _handle_callback(
        self, proc: asyncio.subprocess.Process, frame: dict[str, Any], caller: Any
    ) -> None:
        cid = frame.get("cid")
        surface = frame.get("surface") or ""
        raw_args = frame.get("args") or {}
        assert proc.stdin
        try:
            if surface not in ALLOWED_SURFACES:
                raise SurfaceDeniedError(f"surface not available: {surface}")
            if not isinstance(raw_args, dict):
                raise SurfaceDeniedError("malformed arguments")
            # Refuse scope-bearing keys outright. Silently dropping them would be
            # worse: the plugin would believe it read group 999 and act on an empty
            # result. Failing makes the attempt visible in the audit trail.
            forbidden = _FORBIDDEN_ARG_KEYS.intersection(raw_args)
            if forbidden:
                raise SurfaceDeniedError(
                    "arguments may not be supplied by the plugin: "
                    + ", ".join(sorted(forbidden))
                )
            value = await self._surface_handler(
                self.config.plugin, surface, raw_args, caller
            )
            await _write_frame(
                proc.stdin, {"type": "reply", "cid": cid, "ok": True, "value": value}
            )
        except SurfaceDeniedError as exc:
            # Log the reason on the host side. The child only receives a short error
            # string, but an operator debugging "my plugin's recall stopped working"
            # needs to know *which* rule rejected it. Without this line the only
            # symptom is a bare PermissionError in the plugin.
            logger.warning(
                "plugin surface denied plugin=%s surface=%s reason=%s",
                self.config.plugin,
                surface,
                exc,
            )
            await _write_frame(
                proc.stdin, {"type": "reply", "cid": cid, "ok": False, "error": str(exc)}
            )
        except CapabilityDeniedError as exc:
            # An expected refusal, not a fault. It is already recorded by the audit
            # log (``AUTHZ DENY action=surface:...``) with the capability and the
            # reason, so a traceback here would add nothing but noise — and noise in
            # the security log is how real events get missed. A plugin that polls a
            # surface it was never granted would otherwise emit a stack trace on every
            # single call.
            logger.info(
                "plugin surface refused plugin=%s surface=%s reason=%s",
                self.config.plugin,
                surface,
                exc,
            )
            await _write_frame(
                proc.stdin,
                {"type": "reply", "cid": cid, "ok": False, "error": "PermissionError"},
            )
        except Exception as exc:
            # Type only crosses the boundary; the traceback stays here. A host-side
            # fault must still be diagnosable, otherwise a bug in a surface handler
            # presents to the plugin author as "your plugin is denied", which sends
            # them debugging the wrong side of the pipe.
            logger.exception(
                "plugin surface failed plugin=%s surface=%s", self.config.plugin, surface
            )
            await _write_frame(
                proc.stdin,
                {"type": "reply", "cid": cid, "ok": False, "error": type(exc).__name__},
            )


@dataclass(slots=True)
class WorkerHealth:
    plugin: str
    alive: bool
    restarts: int
    circuit_open: bool
    last_error: str
    uptime_seconds: float


class PluginSupervisor:
    """Owns one worker per plugin and decides when to restart it.

    Restart policy is the interesting part. Naive "always restart" turns a plugin
    that crashes on every message into a fork storm — each message spawns a process
    that dies, costing more than the message. So restarts are bounded:

    * exponential backoff (0.25s doubling, capped at 8s) so a fast crash loop cannot
      saturate the CPU;
    * at most :data:`MAX_RESTARTS_IN_WINDOW` restarts per
      :data:`RESTART_WINDOW_SECONDS`;
    * when that budget is spent the circuit **opens**: the plugin stops, callers get
      a clean failure, and an operator must intervene. Recovery is explicit. A silent
      auto-recover would hide a plugin that is broken or hostile.
    """

    def __init__(self) -> None:
        self._workers: dict[str, PluginWorker] = {}
        self._configs: dict[str, WorkerConfig] = {}
        self._surface_handler = None
        self._restarts: dict[str, list[float]] = {}
        self._circuit: dict[str, bool] = {}
        self._last_error: dict[str, str] = {}
        self._backoff: dict[str, float] = {}

    def bind_surface_handler(self, handler) -> None:
        """Install the host dispatcher. Without it a worker cannot authorize anything."""
        self._surface_handler = handler

    def register(self, config: WorkerConfig) -> None:
        self._configs[config.plugin] = config
        self._restarts.setdefault(config.plugin, [])
        self._circuit.setdefault(config.plugin, False)
        self._backoff.setdefault(config.plugin, BACKOFF_BASE)
        self._last_error.setdefault(config.plugin, "")

    def _record_restart(self, plugin: str) -> None:
        now = time.time()
        history = [t for t in self._restarts.get(plugin, []) if now - t < RESTART_WINDOW_SECONDS]
        history.append(now)
        self._restarts[plugin] = history
        if len(history) > MAX_RESTARTS_IN_WINDOW:
            self._circuit[plugin] = True
            logger.error(
                "plugin %s crash-looped %d times in %.0fs; circuit open, no further "
                "restarts until an operator reloads it",
                plugin,
                len(history),
                RESTART_WINDOW_SECONDS,
            )

    async def start(self, plugin: str) -> PluginWorker:
        if self._surface_handler is None:
            raise IsolationError(
                "supervisor has no surface handler; refusing to start a worker that "
                "could not authorize its own calls"
            )
        config = self._configs.get(plugin)
        if config is None:
            raise IsolationError(f"plugin not registered: {plugin}")
        if self._circuit.get(plugin):
            raise IsolationError(
                f"plugin {plugin} is in a crash loop and is not being restarted; "
                "reload it explicitly to retry"
            )
        existing = self._workers.get(plugin)
        if existing is not None and existing.alive:
            return existing

        worker = PluginWorker(
            config,
            surface_handler=self._surface_handler,
            stderr_sink=lambda line, p=plugin: logger.debug(
                "plugin stderr plugin=%s %s", p, line
            ),
        )
        try:
            await worker.start()
        except Exception as exc:
            self._last_error[plugin] = type(exc).__name__
            await worker.stop()
            self._record_restart(plugin)
            raise
        self._workers[plugin] = worker
        return worker

    async def ensure_running(self, plugin: str) -> PluginWorker:
        """Start or *restart* the worker, honouring backoff and the circuit breaker.

        Called after a crash. Sleeps the current backoff first so a plugin that dies
        immediately cannot spin the supervisor in a tight loop.

        Restart accounting happens **here**, not only in ``start``'s failure path.
        The measured bug: a plugin whose handler loops forever is killed on the
        deadline by the parent (a *successful* kill), so the subsequent relaunch
        succeeds and never reached the old bookkeeping — ``restarts`` stayed 0 and the
        circuit breaker could never open. A plugin could then crash-loop forever at
        whatever rate traffic arrived. Counting every relaunch of a previously-dead
        worker is what makes the breaker actually bound the damage.
        """
        if self._circuit.get(plugin):
            raise IsolationError(
                f"plugin {plugin} is in a crash loop (circuit open); reload it to retry"
            )
        existing = self._workers.get(plugin)
        if existing is not None and existing.alive:
            return existing

        relaunching = existing is not None
        if relaunching:
            # Back off before burning another process, then record the attempt so a
            # fast crash loop trips the breaker instead of spinning silently.
            delay = self._backoff.get(plugin, BACKOFF_BASE)
            await asyncio.sleep(delay)
            self._backoff[plugin] = min(delay * 2, BACKOFF_CAP)
            self._last_error[plugin] = existing.last_error or "died"
            self._record_restart(plugin)
            await self.stop(plugin)

        return await self.start(plugin)

    def worker(self, plugin: str) -> PluginWorker | None:
        return self._workers.get(plugin)

    def health(self) -> list[WorkerHealth]:
        now = time.time()
        out: list[WorkerHealth] = []
        for name in self._configs:
            worker = self._workers.get(name)
            out.append(
                WorkerHealth(
                    plugin=name,
                    alive=bool(worker and worker.alive),
                    restarts=len(
                        [t for t in self._restarts.get(name, []) if now - t < RESTART_WINDOW_SECONDS]
                    ),
                    circuit_open=bool(self._circuit.get(name)),
                    last_error=self._last_error.get(name, "") or (worker.last_error if worker else ""),
                    uptime_seconds=(now - worker.started_at) if worker and worker.started_at else 0.0,
                )
            )
        return out

    def reset_circuit(self, plugin: str) -> None:
        """Operator action: clear the crash-loop state so a reload can succeed.

        Explicit rather than automatic. If the circuit reopened itself on a timer, a
        plugin that is broken or hostile would keep being retried forever and the log
        would show a steady trickle of crashes nobody is expected to notice.
        """
        self._circuit[plugin] = False
        self._restarts[plugin] = []
        self._backoff[plugin] = BACKOFF_BASE

    async def stop(self, plugin: str, *, timeout: float = 5.0) -> None:
        worker = self._workers.pop(plugin, None)
        if worker is not None:
            await worker.stop(timeout=timeout)

    async def stop_all(self, *, timeout: float = 5.0) -> None:
        for name in list(self._workers):
            await self.stop(name, timeout=timeout)
