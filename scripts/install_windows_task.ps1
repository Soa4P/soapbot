# Run soapbot as a scheduled task, not as a child of your remote shell.
#
# Why this exists
# ---------------
# A bot started from a WinRM/RDP session is a grandchild of that session. WinRM puts a
# shell's children in a job object and recycles the shell when it goes idle
# (`winrm get winrm/config/winrs` -> IdleTimeout, 2 hours by default here). When that
# happens the whole job is terminated — including a bot that has been happily running
# for hours. The symptom is nasty because nothing records it: no Python traceback, no
# Application event, no WER entry, no reboot. The process is simply gone, and `panel.err`
# ends mid-sentence with no "Shutting down".
#
# Measured on a real box: started 19:29 from WinRM, last log line 21:28:50, IdleTimeout
# 7200000 ms. The two-hour mark landed inside that window.
#
# A scheduled task under LocalService has no such parent: its ancestry is
# python.exe -> cmd.exe -> svchost.exe -> services.exe, so closing every remote session
# leaves it alone. It also starts at boot, which the manual start never did.
#
# LocalService rather than SYSTEM: `plugins/supervisor.py` refuses to start a plugin
# worker as LocalSystem, so a SYSTEM task runs with every plugin silently disabled. The
# ACLs that let this account read the install are set by scripts\harden-windows.ps1,
# which this script does not run — call it first if the directory was never hardened.
#
# Usage (elevated):
#   powershell -ExecutionPolicy Bypass -File scripts\harden-windows.ps1
#   powershell -ExecutionPolicy Bypass -File scripts\install_windows_task.ps1 -Start

param(
    [string]$InstallDir = 'C:\soapbot',
    [string]$TaskName = 'SoapbotBot',
    [string]$AccountSid = 'S-1-5-19',
    [switch]$Start
)

$ErrorActionPreference = 'Stop'

if (-not (Test-Path (Join-Path $InstallDir '.venv\Scripts\python.exe'))) {
    throw "no venv at $InstallDir\.venv — pass -InstallDir"
}

# NOTE: `&&` must be escaped as `&amp;&amp;`. Unescaped, Register-ScheduledTask rejects the
# whole XML with "The task XML is malformed", which reads like a schema problem rather
# than an escaping one.
$xml = @"
<?xml version="1.0" encoding="UTF-16"?>
<Task version="1.2" xmlns="http://schemas.microsoft.com/windows/2004/02/mit/task">
  <RegistrationInfo>
    <Description>soapbot QQ bot. Runs under LocalService so it is not a child of a remote shell, and so plugins have nothing to inherit.</Description>
  </RegistrationInfo>
  <Triggers>
    <BootTrigger>
      <Enabled>true</Enabled>
      <Delay>PT30S</Delay>
    </BootTrigger>
  </Triggers>
  <Principals>
    <Principal id="Author">
      <UserId>$AccountSid</UserId>
      <LogonType>ServiceAccount</LogonType>
      <RunLevel>LeastPrivilege</RunLevel>
    </Principal>
  </Principals>
  <Settings>
    <MultipleInstancesPolicy>IgnoreNew</MultipleInstancesPolicy>
    <DisallowStartIfOnBatteries>false</DisallowStartIfOnBatteries>
    <StopIfGoingOnBatteries>false</StopIfGoingOnBatteries>
    <AllowHardTerminate>true</AllowHardTerminate>
    <StartWhenAvailable>true</StartWhenAvailable>
    <RunOnlyIfNetworkAvailable>false</RunOnlyIfNetworkAvailable>
    <IdleSettings>
      <StopOnIdleEnd>false</StopOnIdleEnd>
      <RestartOnIdle>false</RestartOnIdle>
    </IdleSettings>
    <AllowStartOnDemand>true</AllowStartOnDemand>
    <Enabled>true</Enabled>
    <RunOnlyIfIdle>false</RunOnlyIfIdle>
    <ExecutionTimeLimit>PT0S</ExecutionTimeLimit>
    <RestartOnFailure>
      <Interval>PT1M</Interval>
      <Count>3</Count>
    </RestartOnFailure>
  </Settings>
  <Actions Context="Author">
    <Exec>
      <Command>cmd.exe</Command>
      <Arguments>/c "cd /d $InstallDir &amp;&amp; .venv\Scripts\python.exe -m soapbot.cli start >> $InstallDir\panel.log 2>> $InstallDir\panel.err"</Arguments>
      <WorkingDirectory>$InstallDir</WorkingDirectory>
    </Exec>
  </Actions>
</Task>
"@

$path = Join-Path $InstallDir 'soapbot-task.xml'
# UTF-16 to match the declaration above; a mismatched encoding is another way to get a
# malformed-task error that points at the wrong line.
[IO.File]::WriteAllText($path, $xml, [Text.Encoding]::Unicode)

Register-ScheduledTask -TaskName $TaskName -Xml ([IO.File]::ReadAllText($path)) -Force | Out-Null
Write-Host "registered $TaskName"

# ExecutionTimeLimit PT0S plus RestartOnFailure means the task is not killed for running
# long, and comes back if the process dies. Verify with:
#   Get-ScheduledTaskInfo -TaskName $TaskName
# LastTaskResult 267009 (0x41301) means "currently running", which is the healthy value.
if ($Start) {
    Start-ScheduledTask -TaskName $TaskName
    Write-Host "started $TaskName"
}

Get-ScheduledTask -TaskName $TaskName | Select-Object TaskName, State
