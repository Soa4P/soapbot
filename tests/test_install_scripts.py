"""The one-command installers: idempotent, credential-free, and consistent with the app.

These are text assertions, not executions. Running a real installer on every test would
need Windows, Linux, systemd and a network; the checks here are the ones that catch the
regressions that actually happened: a task name that disagreed with the panel, and a
token printed into a transcript.
"""

from __future__ import annotations

import re
from pathlib import Path
from types import SimpleNamespace

ROOT = Path(__file__).resolve().parents[1]
PS1 = ROOT / "scripts" / "install.ps1"
SH = ROOT / "scripts" / "install.sh"
README = ROOT / "README.md"


def test_both_installers_exist() -> None:
    assert PS1.is_file() and PS1.stat().st_size > 500
    assert SH.is_file() and SH.stat().st_size > 500


def test_windows_task_name_matches_the_panel_hint(monkeypatch) -> None:
    """The panel generates a restart command; it must name the task this creates.

    The hint is platform-dependent, so the Windows branch is pinned explicitly: on a
    Linux runner ``restart_hint()`` returns systemctl and this assertion would be
    checking the wrong string.
    """
    import soapbot.api.service_hint as hint

    monkeypatch.setattr(hint, "in_container", lambda: False)
    monkeypatch.setattr(hint, "os", SimpleNamespace(name="nt", environ={}))

    script = PS1.read_text(encoding="utf-8")
    assert "$TaskName = 'SoapbotBot'" in script
    assert "/TN SoapbotBot" in hint.restart_hint()


def test_installers_never_print_the_bootstrap_token() -> None:
    ps1 = PS1.read_text(encoding="utf-8")
    sh = SH.read_text(encoding="utf-8")
    # Printing the *path* is the point; reading the value into stdout is not.
    assert "init_token.txt" in ps1 and "init_token.txt" in sh
    assert not re.search(r"Get-Content[^\n]*init_token", ps1)
    assert not re.search(r"\bcat\b[^\n]*init_token", sh)


def test_installers_contain_no_credential_shaped_literals() -> None:
    patterns = (r"sk-[A-Za-z0-9_-]{16,}", r"ghp_[A-Za-z0-9]{20,}", r"AKIA[0-9A-Z]{16}")
    for path in (PS1, SH):
        text = path.read_text(encoding="utf-8")
        for pattern in patterns:
            assert not re.search(pattern, text), f"{path.name} looks like it embeds a credential"


def test_installers_are_idempotent_about_the_data_directory() -> None:
    ps1 = PS1.read_text(encoding="utf-8")
    sh = SH.read_text(encoding="utf-8")
    # Both must decide "keep it" before writing anything into data/.
    assert "keeping existing" in ps1 and "keeping existing" in sh
    assert "Test-Path -LiteralPath $envFile" in ps1
    assert '[ ! -f "$ENV_FILE" ]' in sh


def test_installers_fetch_code_even_when_the_directory_exists() -> None:
    """"Rerun to update" only works if the code is re-fetched, not just the venv."""
    ps1 = PS1.read_text(encoding="utf-8")
    sh = SH.read_text(encoding="utf-8")

    assert "reusing $Dir" not in ps1
    assert 'if [ ! -d "$DIR" ]' not in sh
    assert "soapbot-install.zip" in ps1
    assert "TARBALL" in sh


def test_shell_installer_fails_fast_and_cleans_up() -> None:
    sh = SH.read_text(encoding="utf-8")
    assert "set -euo pipefail" in sh
    assert "trap 'rm -rf" in sh
    assert "systemctl enable" in sh


def test_remote_panel_bat_does_not_build_a_command_line() -> None:
    """The bat used to expand ``%HOST%``/``%USER%`` into one ssh command string.

    cmd expands variables before ssh sees them, so a host of ``x & calc`` executed calc.
    The bat must stay a forwarder: parameters, not a concatenated command.
    """
    bat = (ROOT / "open-remote-panel.bat").read_text(encoding="utf-8")
    assert "connect-linux.ps1" in bat
    body = "\n".join(line for line in bat.splitlines() if not line.strip().lower().startswith("rem"))
    assert not re.search(r"\bssh(\.exe)?\s+-[piNL]", body), "bat 又自己拼 ssh 命令了"
    assert body.count('"%') >= 5, "参数没有全部加引号传出去"


def test_connect_linux_validates_before_ssh_and_pins_the_host_key() -> None:
    text = (ROOT / "scripts" / "connect-linux.ps1").read_text(encoding="utf-8")
    # A leading '-' in the hostname is parsed by ssh as an option (ProxyCommand RCE).
    assert "is not a hostname" in text
    assert "is not a valid Linux account name" in text
    # First connection must record the key; later connections must reject a changed one.
    assert "StrictHostKeyChecking=accept-new" in text
    assert "ExitOnForwardFailure=yes" in text


def test_readme_leads_with_the_three_paths() -> None:
    """Three ways in — and the Docker one must name a compose file that exists.

    This test used to assert the bare ``docker compose up -d``. That command is broken:
    the compose file lives at ``deploy/docker-compose.yml``, not at the repository root.
    Asserting the wrong string had turned a copy-paste failure into a contract, so the
    assertion now pins the ``-f`` form and forbids the bare one from coming back.
    """
    text = README.read_text(encoding="utf-8")
    deployment = text.split("## 启动", 1)[1].split("## 边界", 1)[0]
    assert "install.ps1" in deployment
    assert "install.sh" in deployment
    assert "docker compose -f deploy/docker-compose.yml up -d" in deployment
    assert "docker compose up -d" not in deployment
    assert "docs/deploy-quickstart.md" in text
