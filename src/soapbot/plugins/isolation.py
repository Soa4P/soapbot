"""Process-level isolation for plugins.

Why this module exists
----------------------
The plugin façade (``context.py`` / ``sandbox.py``) makes *sanctioned* operations
authorised and auditable, but it cannot make an in-process plugin harmless: the
plugin shares this interpreter, so it can ``import httpx`` itself, call
``os._exit()``, rewrite ``AuditLog.record``, or walk ``gc.get_objects()`` to find
the runtime. Every one of those was reproduced during the isolation review.

The user-facing requirement was "a plugin must not be able to affect the host under
any circumstances". That is **not achievable while the plugin runs in this
process**, so this module provides the only mechanism that *can* deliver it: run
the plugin in a separate process and talk to it over a pipe.

What the boundary actually guarantees
-------------------------------------
With ``IsolatedRunner``:

* a plugin that hangs, crashes, segfaults or calls ``os._exit`` takes down only its
  own process — the host observes EOF/timeout and reports a failure;
* a plugin that eats memory dies at ``RLIMIT_AS`` instead of OOM-killing the bot;
* the child never holds the host's DB connection, adapters, audit log or the admin
  event loop, so "monkeypatch the audit log" is no longer expressible;
* a plugin that loops forever is killed on the deadline.

What it does **not** guarantee (stated plainly, not hidden)
-----------------------------------------------------------
* Filesystem and network access are **not** virtally confined: the child is a
  normal process owned by the same user. It can still read files the user can read
  and make outbound connections with ``import requests``. Closing that needs OS
  sandboxing (container, ``seccomp``/``Job Objects``, or a separate uid) — see
  ``docs/plugin-isolation.md`` §"残余风险" for the deployment guidance.
* ``RLIMIT_*`` is POSIX-only. On Windows the limits are skipped, so a memory-bomb
  plugin can still exhaust the machine; the timeout and process boundary do hold.

Honesty about "absolute"
------------------------
Nothing in userspace gives "cannot affect the host under any circumstances". A
plugin is code with the same OS privileges as the bot. What this module delivers is
that the *host's* integrity — its state, its audit trail, its uptime for other
sessions — survives anything a plugin does, and that the residual risk is a
documented, deployable decision rather than an unbounded one.
"""

from __future__ import annotations

import asyncio
import contextlib
import json
import logging
import os
import signal
import sys
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

logger = logging.getLogger(__name__)

#: Windows process-creation flag for a new process group. Read defensively because
#: the constant only exists on Windows.
_CREATE_NEW_PROCESS_GROUP = getattr(__import__("subprocess"), "CREATE_NEW_PROCESS_GROUP", 0)


def _kill_tree(proc: asyncio.subprocess.Process) -> None:
    """Kill the child *and* anything it spawned.

    ``proc.kill()`` signals one pid. A plugin that forks helpers (measured: 20
    children, all surviving) keeps burning CPU after the direct child dies, so the
    timeout would contain the hang but not the resource use. Killing the group is
    what makes "the plugin occupies resources" bounded rather than merely reported.
    """
    if proc.returncode is not None:
        return
    if sys.platform == "win32":
        # taskkill /T is the only portable way to take a tree down on Windows.
        with contextlib.suppress(Exception):
            __import__("subprocess").run(
                ["taskkill", "/F", "/T", "/PID", str(proc.pid)],
                capture_output=True,
                timeout=5,
                check=False,
            )
    else:
        with contextlib.suppress(ProcessLookupError, PermissionError, OSError):
            os.killpg(os.getpgid(proc.pid), signal.SIGKILL)
    with SuppressProcessLookup():
        proc.kill()

#: A plugin invocation must finish inside this window. Enforced by the parent, so
#: it holds even if the child ignores SIGTERM or is stuck in C code.
DEFAULT_TIMEOUT = 8.0

#: Hard cap on a single IPC frame, so a plugin cannot make the parent allocate an
#: arbitrary buffer by writing a huge length header.
MAX_FRAME_BYTES = 4 * 1024 * 1024

#: Environment variables a plugin subprocess is allowed to inherit.
#:
#: This is an **allowlist, not a denylist**, and that choice is the whole point.
#:
#: The inherited environ was measured leaking all four of these to a plugin
#: child (``_probe_deploy.py``, PROBE 1, 90 variables inherited):
#:
#:   SOAPBOT_MASTER_KEY   -> decrypts every API key in the database (``SecretBox``)
#:   SOAPBOT_JWT_SECRET   -> mints admin tokens
#:   SOAPBOT_DB_URL       -> contains the Postgres password when not SQLite
#:   OPENAI_API_KEY       -> direct billing fraud
#:
#: A denylist ("strip anything containing KEY/SECRET/TOKEN") cannot work here.
#: Operators legitimately use ``AWS_*``, ``*_CREDENTIALS``, ``DATABASE_URL``,
#: ``PGPASSWORD``, cloud SDK provider chains — an unbounded set, and every miss is
#: silent. The allowlist inverts the failure mode: a variable the platform needs
#: but nobody listed makes the child fail *loudly at startup*, which is fixable,
#: instead of quietly handing out a credential.
#:
#: ``SOAPBOT_PLUGIN_*`` is the one prefix forwarded, so an operator can pass
#: deliberate plugin configuration without exposing the host's own secrets.
_SAFE_ENV_KEYS = frozenset(
    {
        # Required for the interpreter to start and for system libraries to resolve.
        "PATH",
        "SYSTEMROOT",  # Windows: winsock/dll loading fails without it
        "SYSTEMDRIVE",
        "WINDIR",
        "COMSPEC",
        "PATHEXT",
        # Locale / encoding: without these a plugin writing Chinese text crashes on
        # a POSIX box with a C locale, which reads as "the plugin is broken".
        "LANG",
        "LC_ALL",
        "LC_CTYPE",
        "PYTHONIOENCODING",
        "PYTHONUTF8",
        # Temp + home: tmpfile() and ~ expansion need these to resolve. They are
        # not secrets (the child can reach the same paths from Python anyway).
        "TMPDIR",
        "TEMP",
        "TMP",
        "HOME",
        "USERPROFILE",
        # Certificate store location; without it outbound TLS fails confusingly.
        "SSL_CERT_FILE",
        "SSL_CERT_DIR",
        "REQUESTS_CA_BUNDLE",
    }
)

#: Prefix forwarded so operators can pass *plugin* config deliberately.
_SAFE_ENV_PREFIX = "SOAPBOT_PLUGIN_"


def sanitize_env(base: dict[str, str] | None = None, extra: dict[str, str] | None = None) -> dict[str, str]:
    """Return the environment a plugin subprocess may see.

    Keeps :data:`_SAFE_ENV_KEYS` and the ``SOAPBOT_PLUGIN_*`` prefix, drops
    everything else. ``extra`` is applied last for values the host wants to inject
    (resource caps, plugin config) — host code controls it, never the plugin.
    """
    src = os.environ if base is None else base
    env = {
        k: v
        for k, v in src.items()
        if k in _SAFE_ENV_KEYS or k.startswith(_SAFE_ENV_PREFIX)
    }
    if extra:
        env.update({str(k): str(v) for k, v in extra.items()})
    return env


class IsolationError(RuntimeError):
    """The plugin process misbehaved at the transport level."""


class PluginCrashedError(IsolationError):
    """The plugin process died (exit, signal, segfault, ``os._exit``)."""


class PluginTimeoutError(IsolationError):
    """The plugin process did not answer within the deadline."""


class _HostAuthority:
    """Marker proving a call comes from host code that holds this instance.

    Not a cryptographic control — a plugin running in this interpreter could import
    this module and reach the singleton. It exists to stop the *naive* escalation
    (``ctx._session_ledger.record("me", "any-group")``) and to make the intent of
    the API obvious. The unbypassable boundary is the process split; see the module
    docstring for why that distinction matters and is stated rather than blurred.
    """

    __slots__ = ()

    def __repr__(self) -> str:  # pragma: no cover - debugging aid
        return "<host authority>"


HOST_AUTHORITY = _HostAuthority()


@dataclass(slots=True)
class SessionLedger:
    """Host-owned record of which sessions each plugin may send to.

    The previous design kept a plain ``set`` on ``PluginContext``, so a plugin could
    call ``ctx._observed_sessions.add("onebot11:group:<any>")`` and then message any
    group it liked. The set moved here, writes require :data:`HOST_AUTHORITY`, and
    the context only ever calls :meth:`permits`.
    """

    _by_plugin: dict[str, set[str]] = field(default_factory=dict)

    def record(self, plugin: str, session_key: str, *, authority: Any = None) -> None:
        if authority is not HOST_AUTHORITY:
            raise PermissionError("session grants may only be written by the host")
        self._by_plugin.setdefault(plugin, set()).add(session_key)

    def permits(self, plugin: str, session_key: str) -> bool:
        return session_key in self._by_plugin.get(plugin, ())

    def sessions_for(self, plugin: str) -> frozenset[str]:
        return frozenset(self._by_plugin.get(plugin, ()))

    def forget_plugin(self, plugin: str, *, authority: Any = None) -> None:
        """Drop a plugin's grant on unload, so a reload starts from nothing."""
        if authority is not HOST_AUTHORITY:
            raise PermissionError("session grants may only be cleared by the host")
        self._by_plugin.pop(plugin, None)


class NullLedger:
    """A ledger that permits nothing and records nothing.

    The default on a bare ``PluginContext``: an object that has not been bound to a
    host must not be able to send anywhere, so the safe default is "no sessions"
    rather than "a writable set".
    """

    __slots__ = ()

    def record(self, plugin: str, session_key: str, *, authority: Any = None) -> None:
        return None

    def permits(self, plugin: str, session_key: str) -> bool:
        return False

    def sessions_for(self, plugin: str) -> frozenset[str]:
        return frozenset()

    def forget_plugin(self, plugin: str, *, authority: Any = None) -> None:
        return None


# --------------------------------------------------------------------------- ipc

#: Runs inside the child. Kept as a module-level constant (not a nested function)
#: so it is importable by path from a fresh interpreter.
_CHILD_BOOTSTRAP = r'''
import asyncio, importlib.util, inspect, json, os, sys

class _HostPackageBlocker:
    """Refuse to import the host package inside a plugin process.

    ``-I`` drops PYTHON* variables and the *user* site directory, but it keeps the
    interpreter's own site-packages on sys.path. The host package is installed there
    in every real deployment (the Dockerfile does ``pip install``), so ``import
    soapbot`` succeeded in the child and the guarantee in docs/plugin-isolation.md
    only held on a machine where the package was *not* installed. Measured on Linux
    CI, where ``pip install -e .`` made that test fail; it passed locally for the
    wrong reason.

    A meta path finder is the narrow fix: third-party libraries stay importable
    (plugins legitimately use httpx), only the host namespace is refused.
    """

    def find_spec(self, name, path=None, target=None):
        if name == "soapbot" or name.startswith("soapbot."):
            raise ImportError("plugin processes may not import " + name)
        return None


sys.meta_path.insert(0, _HostPackageBlocker())

def _send(msg):
    data = json.dumps(msg, ensure_ascii=False).encode("utf-8")
    sys.stdout.buffer.write(len(data).to_bytes(4, "big"))
    sys.stdout.buffer.write(data)
    sys.stdout.buffer.flush()

def _apply_limits():
    """Lower the child's own ceilings. Best effort; POSIX only."""
    try:
        import resource
        # Address space: a memory-bomb plugin dies alone instead of taking the bot
        # down with it (the OOM killer picks the largest process, not the guilty one).
        cap = int(os.environ.get("SOAPBOT_PLUGIN_MEM_BYTES", 256 * 1024 * 1024))
        resource.setrlimit(resource.RLIMIT_AS, (cap, cap))
        # No core dumps: a dump of this process can contain host memory inherited
        # before exec, which would turn a crash into a disclosure.
        resource.setrlimit(resource.RLIMIT_CORE, (0, 0))
    except Exception:
        pass  # Windows, or a platform without these limits.

async def _invoke(fn, payload):
    caller = payload.get("caller") or {}
    args = payload.get("args") or []
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
    return out

def main():
    _apply_limits()
    req = json.loads(sys.stdin.buffer.read().decode("utf-8"))
    sys.path.insert(0, req["plugin_dir"])
    try:
        spec = importlib.util.spec_from_file_location(
            "plugin_main", os.path.join(req["plugin_dir"], "main.py")
        )
        mod = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(mod)
        target = getattr(mod, req["attr"])

        handler = req.get("handler")
        if handler:
            # Entry point is a class: instantiate, then resolve the named handler.
            inst = target()
            fn = getattr(inst, handler, None)
            if fn is None:
                _send({"ok": False, "error": "no such handler"})
                return
        else:
            fn = target

        result = asyncio.run(_invoke(fn, req.get("payload") or {}))
        # Only JSON-able results cross the boundary. Refusing anything else stops
        # the child from handing the parent a pickled object graph to revive.
        if not isinstance(result, (str, int, float, bool, type(None), dict, list)):
            _send({"ok": False, "error": "non-serialisable result"})
            return
        _send({"ok": True, "result": result})
    except BaseException as exc:
        # Report the type only: the message is plugin-controlled and routinely
        # contains paths, tokens or another user's data.
        _send({"ok": False, "error": type(exc).__name__})

if __name__ == "__main__":
    main()
'''


async def _read_frame(reader: asyncio.StreamReader) -> dict[str, Any]:
    header = await reader.readexactly(4)
    length = int.from_bytes(header, "big")
    if length <= 0 or length > MAX_FRAME_BYTES:
        raise IsolationError(f"refusing frame of {length} bytes")
    body = await reader.readexactly(length)
    return json.loads(body.decode("utf-8"))


class IsolatedRunner:
    """Runs a plugin entry point in a child process and returns its reply.

    Usage is intentionally narrow: this is a *measurement/execution primitive*, not
    a second plugin system. It exists so the host has a way to run untrusted code
    whose failure cannot reach host state.
    """

    def __init__(
        self,
        *,
        timeout: float = DEFAULT_TIMEOUT,
        memory_bytes: int = 256 * 1024 * 1024,
    ) -> None:
        self.timeout = timeout
        self.memory_bytes = memory_bytes

    def _limits_supported(self) -> bool:
        return sys.platform != "win32"

    async def run_entry(
        self,
        *,
        plugin_dir: Path,
        attr: str = "Plugin",
        handler: str = "",
        payload: Any = None,
    ) -> Any:
        """Execute ``plugin_dir/main.py:attr`` in a child process.

        Returns the decoded reply, or raises :class:`PluginTimeoutError` /
        :class:`PluginCrashedError`. The caller never sees an exception type from the
        plugin: only these three, all host-defined.
        """
        # Allowlist, not the inherited environ: see ``sanitize_env``. This is the
        # difference between "a plugin process" and "a plugin process holding the
        # master key".
        env = sanitize_env(extra={"SOAPBOT_PLUGIN_MEM_BYTES": str(self.memory_bytes)})

        request = json.dumps(
            {
                "plugin_dir": str(plugin_dir),
                "attr": attr,
                "handler": handler,
                "payload": payload,
            }
        ).encode("utf-8")

        try:
            proc = await asyncio.create_subprocess_exec(
                sys.executable,
                "-I",  # isolated mode: ignore PYTHON* env and user site-packages
                "-c",
                _CHILD_BOOTSTRAP,
                stdin=asyncio.subprocess.PIPE,
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE,
                env=env,
                # Run *inside* the plugin's own directory rather than the host's cwd.
                # Measured before the fix: a child started in the repo root could
                # ``open("../../_pwned.txt", "w")`` and write next to the source tree,
                # and a relative ``.env`` read would resolve against the host layout.
                # Confining cwd does not stop an absolute path (same uid — see the
                # module docstring), but it removes the accidental reach into the
                # deployment tree that a relative path gives for free.
                cwd=str(plugin_dir) if plugin_dir.is_dir() else None,
                # Own process group/session, so a kill reaches grandchildren too.
                # Without this a plugin that spawns 20 helpers (measured working)
                # leaves them running after the parent is reaped: the timeout kills
                # the direct child and the orphans keep holding CPU and memory.
                start_new_session=(sys.platform != "win32"),
                creationflags=(_CREATE_NEW_PROCESS_GROUP if sys.platform == "win32" else 0),
            )
        except OSError as exc:  # pragma: no cover - depends on environment
            raise IsolationError(f"could not start plugin process: {exc}") from exc

        try:
            stdout, stderr = await asyncio.wait_for(
                proc.communicate(request), timeout=self.timeout
            )
        except TimeoutError as exc:
            # The parent kills the child *tree*. This is the guarantee that a hung
            # plugin cannot wedge a session: the plugin's own SIGTERM handling is
            # irrelevant, and its helpers die with it.
            _kill_tree(proc)
            with SuppressProcessLookup():
                await proc.wait()
            raise PluginTimeoutError(
                f"plugin did not answer within {self.timeout:.1f}s"
            ) from exc

        if proc.returncode != 0:
            # Never include stderr text in the exception: it is plugin-controlled and
            # routinely contains paths, tokens or another user's data.
            raise PluginCrashedError(
                f"plugin process exited with code {proc.returncode}"
            )

        if not stdout:
            raise PluginCrashedError("plugin process produced no output")

        try:
            length = int.from_bytes(stdout[:4], "big")
            body = stdout[4 : 4 + length]
            reply = json.loads(body.decode("utf-8"))
        except (ValueError, UnicodeDecodeError) as exc:
            raise IsolationError("plugin sent a malformed frame") from exc

        if not reply.get("ok"):
            raise PluginCrashedError(f"plugin reported {reply.get('error', 'error')}")
        return reply.get("result")


class SuppressProcessLookup:
    """Swallow the race where the child already exited before ``kill()``."""

    def __enter__(self) -> None:
        return None

    def __exit__(self, exc_type, exc, tb) -> bool:
        return exc_type is not None and issubclass(exc_type, ProcessLookupError)
