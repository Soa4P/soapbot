"""The deployment-host restart check must be safe to hand to an operator.

It sends a real SIGTERM, so the two things worth pinning are that it refuses to guess
when the supervisor is missing, and that it never pulls in a dependency a freshly
installed host would not have yet.
"""

from __future__ import annotations

import ast
import os
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SCRIPT = ROOT / "scripts" / "verify_restart.py"


def _invoke(*args: str, io_encoding: str | None = None) -> subprocess.CompletedProcess[str]:
    env = dict(os.environ)
    if io_encoding:
        env["PYTHONIOENCODING"] = io_encoding
    return subprocess.run(
        [sys.executable, str(SCRIPT), *args],
        capture_output=True,
        text=True,
        encoding="utf-8",
        errors="replace",
        timeout=30,
        cwd=ROOT,
        env=env,
    )


def test_help_explains_the_two_modes() -> None:
    result = _invoke("--help")

    assert result.returncode == 0
    assert "systemd" in result.stdout
    assert "compose" in result.stdout
    assert "--yes" in result.stdout


def test_help_works_on_a_non_utf8_console() -> None:
    """The Windows CI runner defaults to cp1252; Chinese help text used to kill it.

    `argparse.print_help()` writes straight to stdout, so fixing only our own print
    helper was not enough. Force this encoding explicitly so the test fails on any
    machine, including ones whose locale is already UTF-8.
    """
    result = _invoke("--help", io_encoding="cp1252")

    assert result.returncode == 0, result.stderr[-400:]
    assert "systemd" in result.stdout
    assert "UnicodeEncodeError" not in result.stderr


def test_a_missing_unit_fails_closed_without_signalling_anything() -> None:
    """No unit -> exit 2, no SIGTERM. A false PASS here would be a real outage."""
    result = _invoke("--mode", "systemd", "--unit", "definitely-not-a-real-unit", "--yes")

    assert result.returncode == 2, result.stdout + result.stderr
    assert "[FAIL]" in result.stdout


def test_a_missing_compose_file_fails_before_calling_docker() -> None:
    result = _invoke("--mode", "compose", "--compose-dir", "/nonexistent-soapbot-dir", "--yes")

    assert result.returncode == 2, result.stdout + result.stderr
    assert "[FAIL]" in result.stdout


def test_the_script_uses_only_the_standard_library() -> None:
    """It has to run before `pip install -e .` has ever been executed on the host."""
    tree = ast.parse(SCRIPT.read_text(encoding="utf-8"))
    imported: set[str] = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            imported.update(alias.name.split(".")[0] for alias in node.names)
        elif isinstance(node, ast.ImportFrom) and node.module:
            imported.add(node.module.split(".")[0])

    assert imported <= set(sys.stdlib_module_names) | {"__future__"}, (
        f"non-stdlib imports would break a fresh host: {imported - set(sys.stdlib_module_names)}"
    )


def test_the_script_checks_the_policy_it_depends_on() -> None:
    """A restart that comes back from systemd is only expected while Restart=always."""
    source = SCRIPT.read_text(encoding="utf-8")

    assert "Restart=always" in source
    assert "restart: unless-stopped" in source
    assert "SIGTERM" in source
