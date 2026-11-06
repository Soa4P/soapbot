"""Offline audit of the plugin process / IPC boundary.

Why a static gate
-----------------
Most of the properties that make the plugin boundary safe are *negative*: no pickle,
no unbounded frame, no host module name inside a child script, no callback that
skips the parent's authorization point. A unit test can prove one attack is refused
today; it cannot prove somebody did not quietly reintroduce the primitive tomorrow.

This script reads the source only. It does not start a plugin, a container or a
network connection, so it runs identically on a laptop, in CI and before a release.
Every result prints the evidence line it relied on; exit code is non-zero when any
blocking invariant is missing.
"""

from __future__ import annotations

import ast
import re
import sys
from dataclasses import dataclass
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
PLUGINS = ROOT / "src" / "soapbot" / "plugins"
SUPERVISOR = PLUGINS / "supervisor.py"
ISOLATION = PLUGINS / "isolation.py"
LOADER = PLUGINS / "loader.py"
APP = ROOT / "src" / "soapbot" / "app.py"
CONFIG = ROOT / "src" / "soapbot" / "config.py"
BUILDER = ROOT / "src" / "soapbot" / "core" / "builder.py"
CI = ROOT / ".github" / "workflows" / "ci.yml"
MAKEFILE = ROOT / "Makefile"
GUARD = ROOT / "scripts" / "plugin_worker_guard.py"
GUARD_SERVICE = ROOT / "deploy" / "plugin-worker-guard.service"
GUARD_TIMER = ROOT / "deploy" / "plugin-worker-guard.timer"

#: Names that exist only in the host module. A child script runs under a fresh ``-I``
#: interpreter, so referencing one raises NameError — historically swallowed by a
#: bare ``except: pass`` and therefore invisible until a Linux-only crash.
FORBIDDEN_CHILD_NAMES = {
    "DEFAULT_PLUGIN_MEMORY_BYTES",
    "sanitize_env",
    "IsolationError",
    "_kill_tree",
    "MAX_FRAME_BYTES",
    "WorkerConfig",
}


@dataclass
class Result:
    code: str
    ok: bool
    detail: str
    evidence: str = ""


def _text(path: Path) -> str:
    return path.read_text(encoding="utf-8")


def _line_of(text: str, needle: str) -> str:
    for number, line in enumerate(text.splitlines(), 1):
        if needle in line:
            return f"line {number}: {line.strip()[:110]}"
    return f"missing {needle!r}"


def _require(path: Path, needle: str, code: str, detail: str) -> Result:
    text = _text(path)
    return Result(code, needle in text, detail, f"{path.name} {_line_of(text, needle)}")


def _forbid(path: Path, needle: str, code: str, detail: str) -> Result:
    text = _text(path)
    return Result(
        code, needle not in text, detail, f"{path.name} {_line_of(text, needle) if needle in text else 'absent'}"
    )


def _child_script(path: Path, name: str) -> str:
    """Extract the raw child-program string without importing the host package."""
    tree = ast.parse(_text(path))
    for node in tree.body:
        if not isinstance(node, ast.Assign):
            continue
        if not any(isinstance(t, ast.Name) and t.id == name for t in node.targets):
            continue
        if isinstance(node.value, ast.Constant) and isinstance(node.value.value, str):
            return node.value.value
    raise AssertionError(f"{name} string literal not found in {path}")


def _child_nodes(script: str) -> list[ast.AST]:
    return list(ast.walk(ast.parse(script)))


def _child_names(nodes: list[ast.AST]) -> set[str]:
    return {node.id for node in nodes if isinstance(node, ast.Name)}


def _child_attrs(nodes: list[ast.AST]) -> set[str]:
    return {node.attr for node in nodes if isinstance(node, ast.Attribute)}


def _child_functions(nodes: list[ast.AST]) -> set[str]:
    return {
        node.name
        for node in nodes
        if isinstance(node, ast.FunctionDef | ast.AsyncFunctionDef)
    }


def collect() -> list[Result]:
    out: list[Result] = []

    # --- serialization -----------------------------------------------------
    for path in sorted(PLUGINS.glob("*.py")):
        text = _text(path)
        bad = [
            token
            for token in ("import pickle", "pickle.loads", "pickle.dumps", "cPickle")
            if token in text
        ]
        out.append(
            Result(
                "ipc.no-pickle",
                not bad,
                f"{path.name}: IPC stays JSON-only",
                f"{path.name} {_line_of(text, bad[0]) if bad else 'no pickle primitives'}",
            )
        )

    # --- frame budget: one constant, injected into both children ------------
    out.append(
        _require(ISOLATION, "MAX_FRAME_BYTES = 4 * 1024 * 1024", "ipc.frame-budget", "single frame budget constant")
    )
    out.append(
        _require(SUPERVISOR, "from soapbot.plugins.isolation import (", "ipc.frame-budget", "supervisor reuses the budget")
    )
    out.append(
        _forbid(SUPERVISOR, "8 * 1024 * 1024", "ipc.frame-budget", "no divergent hardcoded child limit")
    )
    for path in (SUPERVISOR, ISOLATION):
        out.append(
            _require(path, '.replace("__MAX_FRAME_BYTES__", str(MAX_FRAME_BYTES))', "ipc.frame-budget", f"{path.name} injects the budget")
        )
    out.append(
        _require(SUPERVISOR, "if len(data) > MAX_FRAME_BYTES:", "ipc.outbound-cap", "parent outbound frames are capped")
    )
    out.append(
        _require(ISOLATION, "if len(request) > MAX_FRAME_BYTES:", "ipc.outbound-cap", "one-shot request is capped")
    )
    for path, name in ((SUPERVISOR, "_CHILD_WORKER"), (ISOLATION, "_CHILD_BOOTSTRAP")):
        script = _child_script(path, name)
        out.append(
            Result(
                "ipc.child-cap",
                (
                    ("__MAX_FRAME_BYTES__" in script and "len(data) > _frame_limit[0]" in script)
                    or (name == "_CHILD_BOOTSTRAP" and "len(data) > _MAX_FRAME_BYTES" in script)
                ),
                f"{name} enforces inbound and outbound caps",
                f"{path.name}: placeholder and cap expression present",
            )
        )
        nodes = _child_nodes(script)
        names = _child_names(nodes)
        leaked = sorted(names & FORBIDDEN_CHILD_NAMES)
        out.append(
            Result(
                "ipc.child-no-host-names",
                not leaked,
                f"{name} references no host module names",
                f"{path.name}: {leaked or 'clean'}",
            )
        )
        attrs = _child_attrs(nodes)
        path_ok = "_boot_path" in _child_functions(nodes) and "realpath" in attrs
        out.append(
            Result(
                "ipc.child-path-check",
                path_ok,
                f"{name} re-checks plugin_dir with realpath",
                f"{path.name}: _boot_path and os.path.realpath {'present' if path_ok else 'missing'}",
            )
        )

    # --- correlation id and parent-side authorization ----------------------
    for needle, code, detail in (
        ('"id": rid', "ipc.correlation", "invoke carries a random request id"),
        ('rid = secrets.token_hex(', "ipc.correlation", "request id is random, not a counter"),
        ('frame.get("id") != rid', "ipc.correlation", "result frames are bound to the active id"),
        ('"rid": _current_rid[0]', "ipc.correlation", "child callbacks carry the active id"),
        ('frame.get("rid") != rid', "ipc.correlation", "parent refuses unbound callbacks"),
        ('_surface_handler is None', "ipc.authz-in-parent", "supervisor refuses to run without a host gate"),
        ('ALLOWED_SURFACES', "ipc.authz-in-parent", "surface allowlist remains in the parent"),
    ):
        out.append(_require(SUPERVISOR, needle, code, detail))
    out.append(
        _forbid(SUPERVISOR, '"id": self.invocations', "ipc.correlation", "counter-based ids are gone")
    )

    # --- process governance ------------------------------------------------
    out.append(_require(SUPERVISOR, "_drain_stdout", "proc.stdout-drain", "stdout has a resident reader"))
    out.append(_require(SUPERVISOR, "_FRAME_QUEUE_SIZE", "proc.stdout-drain", "reader uses a bounded queue"))
    out.append(
        _forbid(SUPERVISOR, "await self._abort(\"frame flood\")", "proc.deadlock", "reader never awaits proc.wait() in its own flood path")
    )
    out.append(_require(SUPERVISOR, "self.last_error = \"frame flood\"", "proc.deadlock", "flood kills the child synchronously"))
    out.append(_require(SUPERVISOR, "\"_exit_task\"", "proc.reap", "exit watcher is cancellable"))
    out.append(_require(SUPERVISOR, "await asyncio.wait_for(proc.wait(), timeout=1.0)", "proc.deadlock", "aborts and kills bound proc.wait()"))
    out.append(_require(SUPERVISOR, "_watch_exit", "proc.reap", "exit watcher reaps idle deaths"))
    out.append(_require(SUPERVISOR, "_cancel_tasks", "proc.reap", "stop cancels reader/watcher/drain tasks"))
    out.append(_require(SUPERVISOR, "len(self._configs) >= self.max_workers", "proc.cap", "register enforces the ceiling"))
    out.append(_require(SUPERVISOR, "self.live_worker_count() >= self.max_workers", "proc.cap", "start enforces the ceiling"))
    out.append(_require(SUPERVISOR, "_lifecycle_lock", "proc.cap", "capacity check and spawn are atomic"))
    out.append(_require(SUPERVISOR, "def unregister(self, plugin: str)", "proc.cap", "unloaded plugins release capacity"))
    out.append(_require(LOADER, "self.supervisor.unregister(name)", "proc.cap", "unload releases the capacity booking"))
    out.append(_require(BUILDER, "max_workers=settings.max_plugin_workers", "proc.cap", "builder wires the configured cap"))
    out.append(_require(CONFIG, "le=64", "proc.cap", "config ceiling matches the supervisor hard limit"))
    out.append(_require(LOADER, "await self.supervisor.stop_all()", "proc.reap", "unload_all reaps every worker"))
    out.append(_require(APP, "await supervisor.stop_all()", "proc.reap", "app shutdown reaps even after an unload failure"))
    out.append(
        _forbid(ISOLATION, "proc.communicate(request)", "ipc.outbound-cap", "one-shot runner does not buffer unbounded stdout")
    )
    out.append(_require(ISOLATION, "proc.stdout.readexactly(length)", "ipc.outbound-cap", "one-shot runner reads exactly one bounded frame"))

    sup_text = _text(SUPERVISOR)
    cfg_text = _text(CONFIG)
    sup_cap = re.search(r"^MAX_PLUGIN_WORKERS = (\d+)$", sup_text, re.M)
    cfg_cap = re.search(r"Field\(ge=1, le=(\d+)\)", cfg_text)
    agree = bool(sup_cap and cfg_cap and sup_cap.group(1) == cfg_cap.group(1))
    out.append(
        Result(
            "proc.cap",
            agree,
            "supervisor hard limit and config ceiling agree",
            f"supervisor={sup_cap.group(1) if sup_cap else '?'} config={cfg_cap.group(1) if cfg_cap else '?'}",
        )
    )

    # --- ops wiring --------------------------------------------------------
    for path in (GUARD, GUARD_SERVICE, GUARD_TIMER):
        out.append(
            Result(
                "ops.guard",
                path.is_file(),
                f"{path.name} exists",
                str(path.relative_to(ROOT)),
            )
        )
    if GUARD_SERVICE.is_file():
        out.append(
            _require(GUARD_SERVICE, "plugin_worker_guard.py", "ops.guard", "service ExecStart points at the real script")
        )
    if GUARD_TIMER.is_file():
        out.append(_require(GUARD_TIMER, "WantedBy=timers.target", "ops.guard", "timer is installable"))
    out.append(_require(CI, "check_plugin_ipc.py", "ops.gate", "CI runs the audit"))
    out.append(_require(MAKEFILE, "check_plugin_ipc.py", "ops.gate", "make check runs the audit"))
    return out


def main() -> int:
    results = collect()
    for item in results:
        mark = "ok  " if item.ok else "FAIL"
        print(f"{mark} {item.code:26} {item.detail}")
        print(f"       evidence: {item.evidence}")
    failed = [item for item in results if not item.ok]
    if failed:
        print(f"\nplugin IPC audit: {len(failed)} blocking finding(s)")
        return 1
    print(f"\nplugin IPC audit: {len(results)} invariants hold")
    return 0


if __name__ == "__main__":
    sys.exit(main())
