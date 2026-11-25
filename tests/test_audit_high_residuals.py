"""The two remaining audit Highs that are code-shaped, not product decisions.

* S-MSG-01 — ``/look`` let any group member read the operator's dedicated machine. The old
  floor (``USE_COMMAND``) was justified by "a disabled capture only yields a refusal
  token", which answers *can it run*, not *who may run it*.
* S-DEP-04 — the NapCat task ran as SYSTEM, executing ``cmd /c C:\\napcat\\napcat.bat``
  from a directory any local user could write, with unquoted paths. Drop a file where
  SYSTEM is about to execute and it becomes SYSTEM's code.
"""

from __future__ import annotations

from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def _text(relative: str) -> str:
    return (ROOT / relative).read_text(encoding="utf-8")


def test_look_is_admin_only() -> None:
    from soapbot.memory.stages import CommandStage
    from soapbot.security.principal import PERMISSION_MIN_ROLE, Permission, Role

    permission = CommandStage.COMMAND_PERMISSIONS["look"]
    assert permission is Permission.VIEW_SCREEN
    assert PERMISSION_MIN_ROLE[permission] is Role.ADMIN


def test_napcat_task_does_not_execute_from_a_writable_tree() -> None:
    script = _text("scripts/install_napcat_task.ps1")
    # Hardening must come before the task is registered, or there is a window in which
    # the task exists and the directory is still writable.
    acl = script.index("icacls.exe $NapCatDir /inheritance:r")
    register = script.index("Register-ScheduledTask")
    assert acl < register, "ACLs must be applied before the task is registered"
    # Users keep read/execute and lose write.
    assert "/grant '*S-1-5-32-545:(OI)(CI)RX'" in script
    assert "(OI)(CI)F" in script  # SYSTEM + Administrators keep full control


def test_napcat_task_arguments_are_quoted() -> None:
    script = _text("scripts/install_napcat_task.ps1")
    assert "'/c call \"{0}\"'" in script, "batch path must be quoted and called via cmd /c call"
    assert ">> \"{0}\" 2>&1" in script, "log redirect path must be quoted"
    # And the old unquoted *assignment* must be gone (the comment above it quotes the old
    # shape on purpose, so match the code line, not any mention of it).
    assert '$taskArgs = "/c $NapCatDir' not in script


def test_napcat_task_principal_is_a_parameter_not_a_constant() -> None:
    script = _text("scripts/install_napcat_task.ps1")
    assert "[string]$Account = 'SYSTEM'" in script
    assert "New-ScheduledTaskPrincipal -UserId $Account" in script


# ------------------------------------------------- S-DEP-01/02: the Windows bootstrap


def test_windows_bootstrap_verifies_before_executing() -> None:
    """The Python installer runs *elevated*; a signature check after that is decoration."""
    script = _text("deploy/windows-bootstrap.ps1")
    verify = script.index("Assert-AuthenticodeSigned $installer")
    execute = script.index("Start-Process $installer")
    assert verify < execute, "the signature check must run before the installer"


def test_windows_bootstrap_never_reuses_a_download() -> None:
    """Reusing `%TEMP%\\python-3.12.7-amd64.exe` is the UAC bypass: pre-place, run, elevate."""
    script = _text("deploy/windows-bootstrap.ps1")
    assert "if (-not (Test-Path $installer))" not in script, "a pre-placed file must not be reused"
    assert "/inheritance:r" in script, "the setup directory must be admin-only"
    # No download target may live in the user-writable temp directory (comments may
    # mention it; assignments may not).
    for line in script.splitlines():
        stripped = line.strip()
        if stripped.startswith("#"):
            continue
        assert "$env:TEMP" not in stripped, f"download path still in %TEMP%: {stripped}"


def test_windows_bootstrap_can_pin_the_archive_hash() -> None:
    script = _text("deploy/windows-bootstrap.ps1")
    assert "[string]$ExpectedSha256" in script
    assert "Get-FileHash -Algorithm SHA256" in script
    assert "archive hash mismatch" in script  # the failure is a hard stop, with both values
