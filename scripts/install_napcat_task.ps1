# Run NapCat (the OneBot protocol end) as a scheduled task WITHOUT a 72-hour limit.
#
# Why this exists
# ---------------
# NapCat is a second long-lived process. On Windows it is usually installed by hand and
# started from a shell or a one-off scheduled task. Both shapes die quietly:
#
#   * started from WinRM/RDP -> the shell's job object is recycled after IdleTimeout
#     (2 hours here) and takes NapCat's whole process tree with it;
#   * registered as a scheduled task with the DEFAULT settings -> Task Scheduler's
#     ExecutionTimeLimit is PT72H, so it terminates the task and every child exactly
#     72 hours after it started.
#
# The second one is what actually happened in production:
#     LastRunTime        2026/10/31 22:10:10
#     ExecutionTimeLimit PT72H
#     72 hours later    2026/11/03 22:10:10
#     first refused bot connection  22:10:24
#     C:\napcat\run.log last write 22:10:20  (no shutdown line: killed, not exited)
#     LastTaskResult     267014 (0x41306, "task terminated")
#
# Killing NapCat this way also loses the QQ session, so on restart it asks for a fresh
# QR scan and port 3001 never opens. Meanwhile the bot keeps retrying with no idea what
# is wrong. The whole thing reads as "the bot randomly dies".
#
# This script sets:
#   * ExecutionTimeLimit PT0S  -> never killed for running too long (THE fix)
#   * BootTrigger with a delay -> comes back after a reboot, once the network is up
#   * RestartOnFailure         -> recovers from a crash instead of staying Ready
#   * -q <QQ number>           -> quick login, so a clean restart does not need a QR scan
#   * SYSTEM principal         -> not tied to anybody's interactive session
#
# The -q flag only works when NapCat has a saved session for that account. After a
# forced kill the session may be gone; a human has to scan the QR code ONCE through the
# WebUI on :6099. Once logged in, set `autoLoginAccount` in webui.json to the same
# number (this script does that too) and later restarts are automatic.
#
# Usage (elevated):
#   powershell -ExecutionPolicy Bypass -File scripts\install_napcat_task.ps1 -QQNumber 2268360864
#   ... add -Start to launch it immediately.

param(
    [string]$NapCatDir = 'C:\napcat',
    [string]$TaskName = 'NapCat',
    [string]$QQNumber = '',
    [string]$Account = 'SYSTEM',
    [switch]$Start
)

$ErrorActionPreference = 'Stop'

if (-not (Test-Path (Join-Path $NapCatDir 'napcat.bat'))) {
    throw "no napcat.bat at $NapCatDir — pass -NapCatDir"
}

# ---- ACLs before the task exists (audit S-DEP-04) --------------------------------------
# The task ran as SYSTEM and executed `cmd /c C:\napcat\napcat.bat`, from a directory any
# local user could write. That is a straight local escalation: drop a file where SYSTEM is
# about to execute and it becomes SYSTEM's code. The account choice below softens the
# blast radius; this does the actual work — the install tree becomes read/execute for
# users and write only for SYSTEM/Administrators. NapCat itself writes here, but it runs
# as the task principal, so it keeps its own access.
$napcatBat = Join-Path $NapCatDir 'napcat.bat'
& icacls.exe $NapCatDir /inheritance:r `
    /grant '*S-1-5-18:(OI)(CI)F' `
    /grant '*S-1-5-32-544:(OI)(CI)F' `
    /grant '*S-1-5-32-545:(OI)(CI)RX' | Out-Null
if ($LASTEXITCODE -ne 0) {
    throw "icacls failed on $NapCatDir; a world-writable install dir would let any local user replace what this task runs"
}
# run.log is opened through a shell redirect by the task principal; make sure an inherited
# "users may write" ACE on a pre-existing file cannot undo the directory change above.
$log = Join-Path $NapCatDir 'run.log'
if (Test-Path $log) {
    & icacls.exe $log /inheritance:r `
        /grant '*S-1-5-18:F' /grant '*S-1-5-32-544:F' | Out-Null
}

# ---- arguments, quoted ----------------------------------------------------------------
# `"/c $NapCatDir\napcat.bat"` breaks on `C:\Program Files\...` and, worse, lets a path with
# spaces turn the rest of the line into separate arguments. `cmd /c call` with quoted paths
# is the form that survives both.
$taskArgs = '/c call "{0}"' -f $napcatBat
if ($QQNumber) { $taskArgs += ' -q {0}' -f $QQNumber }
$taskArgs += ' >> "{0}" 2>&1' -f $log

# Set autoLoginAccount so the WebUI path also attempts a quick login without -q.
if ($QQNumber) {
    $webui = Join-Path $NapCatDir 'napcat\config\webui.json'
    if (Test-Path $webui) {
        $raw = [System.IO.File]::ReadAllText($webui, [System.Text.Encoding]::UTF8)
        if ($raw -match '"autoLoginAccount"\s*:\s*""') {
            [System.IO.File]::WriteAllText(
                "$webui.bak", $raw, [System.Text.Encoding]::UTF8)
            $updated = $raw -replace '"autoLoginAccount"\s*:\s*""',
                ('"autoLoginAccount": "' + $QQNumber + '"')
            [System.IO.File]::WriteAllText(
                $webui, $updated, (New-Object System.Text.UTF8Encoding($false)))
            Write-Host "autoLoginAccount set to $QQNumber (backup: $webui.bak)"
        }
    }
}

$action = New-ScheduledTaskAction -Execute 'cmd.exe' -Argument $taskArgs
# Principal: SYSTEM by default because NapCat must start before anyone logs in and needs
# no interactive session; the ACL block above is what makes that acceptable (nothing
# writable it executes). `-Account` lets an operator pick a different identity, which also
# removes SYSTEM from the picture entirely.
$principal = New-ScheduledTaskPrincipal -UserId $Account `
    -LogonType ServiceAccount -RunLevel Highest
$boot = New-ScheduledTaskTrigger -AtStartup
$boot.Delay = 'PT45S'
$settings = New-ScheduledTaskSettingsSet `
    -ExecutionTimeLimit ([timespan]::Zero) `
    -RestartCount 3 -RestartInterval (New-TimeSpan -Minutes 1) `
    -MultipleInstances IgnoreNew -StartWhenAvailable

Register-ScheduledTask -TaskName $TaskName -Action $action -Principal $principal `
    -Trigger $boot -Settings $settings -Force | Out-Null

$t = Get-ScheduledTask -TaskName $TaskName
Write-Host ("Installed {0}: running as {1}, ExecutionTimeLimit={2} triggers={3}" -f `
    $TaskName, $Account, $t.Settings.ExecutionTimeLimit, $t.Triggers.Count)
Write-Host ("  args: {0}" -f $t.Actions.Arguments)

if ($t.Settings.ExecutionTimeLimit -ne [timespan]::Zero) {
    throw 'ExecutionTimeLimit was not cleared — the 72h kill would still apply'
}

# Prove the ACL actually took: a world-writable install directory is the escalation this
# script exists to close, and `icacls` can "succeed" on a path that then inherits a broad
# ACE back from its parent when another tool re-enables inheritance.
$usersAce = (& icacls.exe $NapCatDir 2>$null | Select-String -SimpleMatch 'Users' | ForEach-Object { $_.Line }) -join ' '
if ($usersAce -match '\((F|M)\)') {
    Write-Host '  warning: Users still have write/full control on the install dir; re-run icacls /inheritance:r' -ForegroundColor Yellow
}

if ($Start) { Start-ScheduledTask -TaskName $TaskName }
