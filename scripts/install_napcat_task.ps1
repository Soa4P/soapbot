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
    [switch]$Start
)

$ErrorActionPreference = 'Stop'

if (-not (Test-Path (Join-Path $NapCatDir 'napcat.bat'))) {
    throw "no napcat.bat at $NapCatDir — pass -NapCatDir"
}

$log = Join-Path $NapCatDir 'run.log'
$taskArgs = "/c $NapCatDir\napcat.bat"
if ($QQNumber) { $taskArgs += " -q $QQNumber" }
$taskArgs += " > $log 2>&1"

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
$principal = New-ScheduledTaskPrincipal -UserId 'SYSTEM' `
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
Write-Host ("Installed {0}: ExecutionTimeLimit={1} triggers={2} args={3}" -f `
    $TaskName, $t.Settings.ExecutionTimeLimit, $t.Triggers.Count, $t.Actions.Arguments)

if ($t.Settings.ExecutionTimeLimit -ne [timespan]::Zero) {
    throw 'ExecutionTimeLimit was not cleared — the 72h kill would still apply'
}

if ($Start) { Start-ScheduledTask -TaskName $TaskName }
