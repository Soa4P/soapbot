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

import signal
import subprocess
import sys
from pathlib import Path

import pytest

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
