"""The restart strategy and the supervisor's restart policy have to agree.

This is the part of a Linux/systemd smoke test that does not need systemd itself:
`_perform_now()` must actually terminate a real process in the way the supervisor is
configured to bring back. The unit tests in ``test_system_restart.py`` use a fake `os`
to pin the branch; these spawn a real child so a SIGTERM handler installed by a future
dependency (or an accidental `sys.exit(0)`) cannot make the assertion pass in theory
while starting a service that never comes back in practice.

The CI runner for ``ubuntu-latest`` is a Linux machine, so the POSIX cases run there
for real on every push. The static half checks the deployment files those signals rely
on — a `Restart=always` that someone removes in an installer edit is a dead restart
button with no failing test.
"""

from __future__ import annotations

import os
import signal
import subprocess
import sys
import time
from pathlib import Path

import pytest

from soapbot.core import config_write

ROOT = Path(__file__).resolve().parents[1]


def _child(body: str) -> subprocess.CompletedProcess[bytes]:
    code = f"from soapbot.api import system\n{body}\n"
    return subprocess.run(
        [sys.executable, "-c", code],
        capture_output=True,
        timeout=30,
        cwd=ROOT,
    )


@pytest.mark.skipif(sys.platform == "win32", reason="POSIX signal semantics")
def test_linux_restart_really_sends_sigterm_to_a_live_process() -> None:
    """On the Linux CI runner: a real child really dies of SIGTERM, not exit 0."""
    result = _child(
        "system.in_container = lambda: False\n"
        "system._perform_now()\n"
        "import sys; sys.exit(0)  # a clean exit would NOT be restarted by systemd\n"
    )

    assert result.returncode == -signal.SIGTERM, (
        f"expected death by SIGTERM, got rc={result.returncode}; "
        f"stderr={result.stderr.decode('utf-8', 'replace')[-300:]}"
    )


def test_container_restart_really_exits_nonzero() -> None:
    """A real child exits 75, which `restart: unless-stopped` brings back."""
    result = _child(
        "system.in_container = lambda: True\n"
        "system._perform_now()\n"
        "import sys; sys.exit(0)  # must be unreachable\n"
    )

    assert result.returncode == 75, (
        f"compose needs a non-zero exit, got {result.returncode}; "
        f"stderr={result.stderr.decode('utf-8', 'replace')[-300:]}"
    )


def test_systemd_unit_is_configured_to_restart_the_sigterm_exit() -> None:
    """The Linux branch is only correct while the unit says Restart=always."""
    bootstrap = (ROOT / "scripts" / "bootstrap.py").read_text(encoding="utf-8")

    assert "Restart=always" in bootstrap
    assert "RestartSec=" in bootstrap
    assert "KillSignal=" not in bootstrap, (
        "a custom KillSignal would change what the panel's SIGTERM means"
    )


def test_compose_policy_matches_the_nonzero_exit() -> None:
    compose = (ROOT / "deploy" / "docker-compose.yml").read_text(encoding="utf-8")

    assert "restart: unless-stopped" in compose
    assert "restart: no" not in compose


def test_windows_restart_does_not_rely_on_an_exit_code() -> None:
    """The `-AtStartup` task only restarts *failed* runs.

    A process exiting 0 is a successful run, so the Windows path has to drive
    `schtasks /End` + `/Run` itself. If that ever changes back to "just exit", the
    deployment files need to change with it — and this assertion should fail.
    """
    from soapbot.api import system

    assert hasattr(system, "_spawn_windows_restart")
    source = (ROOT / "src" / "soapbot" / "api" / "system.py").read_text(encoding="utf-8")
    assert '"/End"' in source and '"/Run"' in source
    # The docstring explains why cmd.exe used to be dangerous, so match the actual
    # call rather than the word. A shell here would reopen the injection hole.
    assert '"cmd.exe", "/c"' not in source
    assert '["schtasks", *args]' in source


# ---------------------------------------------------------------- real restart loop
#
# The tests above pin each half of the contract in isolation. These two walk the whole
# loop with real operating-system processes: save a config change, let the process exit
# the way `_perform_now()` exits it, have a supervisor bring it back, and assert the
# *new* process reads the *new* file. That last step is the one an operator actually
# cares about — "I saved the list and after the restart it took effect" — and it is the
# part no mock can prove.
#
# The supervisor here is a few lines of `Popen` instead of systemd/compose, because
# neither is available on a hosted runner. What it does reproduce exactly is the
# contract the deployment files promise: a process that dies is started again with the
# same argv. `scripts/verify_restart.py` is the companion check for a real systemd host.

_SERVICE = """
import os
import sys
import time
from pathlib import Path

env = Path(sys.argv[1])
log = Path(sys.argv[2])
mode = sys.argv[3] if len(sys.argv) > 3 else "stay"
value = env.read_text(encoding="utf-8").strip().split("=", 1)[-1]
with log.open("a", encoding="utf-8") as handle:
    handle.write(f"{os.getpid()}:{value}\\n")
    handle.flush()
if mode == "exit":
    from soapbot.api import system
    system.in_container = lambda: True
    system._perform_now()
while True:
    time.sleep(0.05)
"""


def _spawn_service(env: Path, log: Path, mode: str = "stay") -> subprocess.Popen:
    return subprocess.Popen(
        [sys.executable, "-c", _SERVICE, str(env), str(log), mode],
        cwd=ROOT,
        stdin=subprocess.DEVNULL,
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
    )


def _stop(proc: subprocess.Popen) -> None:
    if proc.poll() is not None:
        return
    proc.terminate()
    try:
        proc.wait(timeout=5)
    except subprocess.TimeoutExpired:
        proc.kill()
        proc.wait(timeout=5)


def _wait_starts(log: Path, count: int, timeout: float = 20.0) -> list[str]:
    deadline = time.time() + timeout
    while time.time() < deadline:
        if log.is_file():
            lines = [line for line in log.read_text(encoding="utf-8").splitlines() if line.strip()]
            if len(lines) >= count:
                return lines
        time.sleep(0.05)
    raise AssertionError(f"only saw {log.read_text(encoding='utf-8') if log.is_file() else '(no log)'!r}; wanted {count} starts")


def _assert_restart_took_effect(lines: list[str]) -> None:
    first_pid, first_value = lines[0].split(":")
    second_pid, second_value = lines[1].split(":")
    assert first_pid != second_pid, "the supervisor must start a genuinely new process"
    assert first_value == "before"
    assert second_value == "after", "the restarted process still reads the pre-save .env"


@pytest.mark.skipif(sys.platform == "win32", reason="POSIX signal semantics")
def test_supervised_linux_restart_serves_the_saved_configuration(tmp_path: Path) -> None:
    """SIGTERM -> `Restart=always` -> new process reads the saved .env."""
    env = tmp_path / ".env"
    env.write_text("SOAPBOT_RESTART_MARKER=before\n", encoding="utf-8")
    log = tmp_path / "starts.log"

    first = _spawn_service(env, log)
    lines: list[str] = []
    try:
        _wait_starts(log, 1)
        config_write.write_env_updates(env, {"SOAPBOT_RESTART_MARKER": "after"})
        os.kill(first.pid, signal.SIGTERM)
        assert first.wait(timeout=20) == -signal.SIGTERM

        second = _spawn_service(env, log)  # what systemd's Restart=always does
        try:
            lines = _wait_starts(log, 2)
        finally:
            _stop(second)
    finally:
        _stop(first)

    _assert_restart_took_effect(lines)


def test_supervised_container_restart_serves_the_saved_configuration(tmp_path: Path) -> None:
    """exit 75 -> `restart: unless-stopped` -> new container reads the saved .env.

    Unlike the SIGTERM case this runs on Windows too, so the whole loop is exercised on
    the maintainer's machine as well as on both CI runners.
    """
    env = tmp_path / ".env"
    env.write_text("SOAPBOT_RESTART_MARKER=before\n", encoding="utf-8")
    log = tmp_path / "starts.log"

    first = _spawn_service(env, log, "exit")
    lines: list[str] = []
    try:
        assert first.wait(timeout=20) == 75
        _wait_starts(log, 1)
        config_write.write_env_updates(env, {"SOAPBOT_RESTART_MARKER": "after"})

        second = _spawn_service(env, log, "stay")
        try:
            lines = _wait_starts(log, 2)
        finally:
            _stop(second)
    finally:
        _stop(first)

    _assert_restart_took_effect(lines)
