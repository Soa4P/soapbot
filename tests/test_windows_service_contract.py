"""One Windows service name, one token policy.

What went wrong
---------------
Three entry points disagreed: ``scripts/install.ps1`` registered ``SoapbotBot``,
``deploy/windows-bootstrap.ps1`` registered ``SoapbotPanel``, ``docs/deployment.md``
said ``soapbot-panel``, and the desktop shell's offline page told the operator to run
``schtasks /Run /TN SoapbotBot``. Two installers that both claim to install "the
service" and produce different names is not cosmetic drift: whichever ran last decides
whether the bot comes back after a reboot, and the shell can only restart a name it
knows. The token policy had the same problem in the opposite direction — one script
printed the single-use token to the terminal, the other only printed its path.

Why static assertions
---------------------
Running these installers would register scheduled tasks and start services, which a
test must not do. What can be checked without executing anything is that every place
which *names* the service names the same one, and that the two service installers agree
on when it starts.
"""

from __future__ import annotations

import re
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
TASK = "SoapbotBot"

#: Declared, not inferred. ``start-panel.bat`` runs the panel in the foreground for a
#: local session, has no service to name, and is the only path that prints the one-time
#: token — a double-click user has no other way to read it. The exception is listed
#: here so that adding a second token-printing script fails this test.
TOKEN_PRINTING_EXEMPT = frozenset({"start-panel.bat"})

_LITERAL = re.compile(r"-TaskName\s+'([^']+)'")
_VARIABLE = re.compile(r"-TaskName\s+\$(\w+)")
_ASSIGNMENT = re.compile(r"\$(\w+)\s*=\s*'([^']+)'")


def _text(relative: str) -> str:
    return (ROOT / relative).read_text(encoding="utf-8", errors="replace")


def _registered_names(text: str) -> set[str]:
    """Every name a ``Register-ScheduledTask`` / ``Start-ScheduledTask`` can resolve to.

    ``-TaskName`` is on the first line of each call in this repo, so per-line scanning is
    enough; the PowerShell backtick only continues the *remaining* parameters.
    """
    assigned = dict(_ASSIGNMENT.findall(text))
    names: set[str] = set()
    for line in text.splitlines():
        if "ScheduledTask" not in line:
            continue
        names.update(_LITERAL.findall(line))
        for variable in _VARIABLE.findall(line):
            if variable in assigned:
                names.add(assigned[variable])
    return names


def test_both_windows_installers_register_the_same_name() -> None:
    for relative in ("scripts/install.ps1", "deploy/windows-bootstrap.ps1"):
        names = _registered_names(_text(relative))
        assert names == {TASK}, f"{relative} 注册的任务名是 {sorted(names)}，应为 {TASK}"


def test_the_task_definition_lives_in_one_place() -> None:
    """Same name with different triggers is worse than different names.

    ``Register-ScheduledTask -Force`` overwrites, so whichever script ran last would
    silently decide whether the bot returns after a reboot — and, since the fix below,
    *who* it runs as. The trigger, principal and action therefore moved into
    ``scripts/harden-windows.ps1`` and the installers only call it; an installer that
    grows its own ``Register-ScheduledTask`` again fails here.
    """
    harden = _text("scripts/harden-windows.ps1")
    assert "-AtStartup" in harden, "harden-windows.ps1 没有设置开机启动触发器"
    for relative in ("scripts/install.ps1", "deploy/windows-bootstrap.ps1"):
        text = _text(relative)
        assert "harden-windows.ps1" in text, f"{relative} 没有走统一的任务定义"
        assert "Register-ScheduledTask" not in text, (
            f"{relative} 又自己注册任务了；触发器与账号会重新分叉"
        )


#: ``SYSTEM`` in an ACL is correct (the OS still needs full control); ``SYSTEM`` as the
#: *task principal* is not, because ``plugins/supervisor.py`` refuses to start a plugin
#: worker as LocalSystem and the install would silently lose every plugin.
_SYSTEM_PRINCIPAL = re.compile(
    r"-UserId\s+'?(?:SYSTEM|NT AUTHORITY\\\\SYSTEM|S-1-5-18)'?", re.IGNORECASE
)


def test_no_script_runs_the_bot_as_system() -> None:
    for relative in (
        "scripts/install.ps1",
        "deploy/windows-bootstrap.ps1",
        "scripts/harden-windows.ps1",
        "scripts/install_windows_task.ps1",
    ):
        text = _text(relative)
        assert not _SYSTEM_PRINCIPAL.search(text), f"{relative} 仍把 SYSTEM 当任务主体"
        assert "<UserId>S-1-5-18</UserId>" not in text

    harden = _text("scripts/harden-windows.ps1")
    assert "NT AUTHORITY\\LocalService" in harden, "默认账号不是低权限账号"
    assert "-RunLevel Limited" in harden or "-RunLevel LeastPrivilege" in harden


def test_the_hardening_script_replaces_rather_than_extends_the_acl() -> None:
    """Adding an ACE would leave the drive root's ``Authenticated Users`` in place."""
    harden = _text("scripts/harden-windows.ps1")
    assert "D:PAI" in harden, "没有用受保护的 DACL 替换继承来的权限项"
    assert "S-1-5-11" not in harden, "脚本自己给 Authenticated Users 发了权限"
    for sub in ("data", "config", "plugins"):
        assert f"'{sub}'" in harden, f"没有单独处理 {sub} 目录的写权限"


def test_the_desktop_shell_restarts_the_same_name() -> None:
    shell = _text("desktop/src-tauri/src/main.rs")
    assert f'"{TASK}"' in shell, "桌面壳的 Windows fallback 与服务名不一致"
    page = _text("desktop/ui/index.html")
    assert f"/TN {TASK}" in page, "离线页提示的任务名与服务名不一致"


def test_the_docs_name_the_same_task() -> None:
    deployment = _text("docs/deployment.md")
    assert TASK in deployment, "deployment.md 没有给出真实任务名"
    assert "soapbot-panel" not in deployment, "deployment.md 还留着不存在的任务名"
    assert TASK in _text("docs/deploy-quickstart.md")


def test_service_installers_do_not_print_the_one_time_token() -> None:
    for relative in ("scripts/install.ps1", "deploy/windows-bootstrap.ps1"):
        text = _text(relative)
        assert "cli token" not in text, (
            f"{relative} 又把令牌取出来打印了；一次性令牌不该留在终端记录里"
        )
        assert "init_token.txt" in text, f"{relative} 没有告诉用户令牌文件在哪里"


def test_only_the_foreground_script_prints_the_token() -> None:
    """The exemption is explicit, so a new printing script cannot slip in unnoticed."""
    printing: set[str] = set()
    for path in sorted(ROOT.glob("*.bat")):
        if "init_token.txt" in path.read_text(encoding="utf-8", errors="replace"):
            printing.add(path.name)
    for path in sorted((ROOT / "scripts").glob("*.ps1")) + sorted(
        (ROOT / "deploy").glob("*.ps1")
    ):
        if re.search(r"^\s*type\s+.*init_token", path.read_text(encoding="utf-8"), re.M):
            printing.add(path.name)
    assert printing <= TOKEN_PRINTING_EXEMPT, (
        f"这些脚本会打印一次性令牌但不在 allowlist 里：{sorted(printing - TOKEN_PRINTING_EXEMPT)}"
    )
    assert any(
        "init_token.txt" in path.read_text(encoding="utf-8", errors="replace")
        for path in ROOT.glob("*.bat")
    ), "前台脚本不见了；豁免清单需要重新确认"


def test_the_parser_catches_a_divergent_name() -> None:
    """Reverse case: a silent parser would make every assertion above vacuous."""
    literal = "Register-ScheduledTask -TaskName 'SoapbotPanel' -Action $a -Force\n"
    assert _registered_names(literal) == {"SoapbotPanel"}

    variable = "$TaskName = 'SoapbotBot'\nRegister-ScheduledTask -TaskName $TaskName\n"
    assert _registered_names(variable) == {"SoapbotBot"}

    assert _registered_names("Write-Host 'no service here'\n") == set()
