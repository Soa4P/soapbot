"""Start the uploaded deploy script as SYSTEM through Task Scheduler.

`Start-Process` inside a WinRM session dies with the session (the WinRM host puts children
in a job object), so the script has to be owned by something that outlives it. A scheduled
task running as SYSTEM is that something, and it also matches how the panel itself would be
started on a real machine.
"""

import sys

import winrm

sys.stdout.reconfigure(encoding="utf-8", errors="replace")

SESSION = winrm.Session(
    "http://152.175.241.226:5985/wsman",
    auth=("Administrator", "zGObanpBktwg8Z3t"),
    transport="basic",
)

PS = r"""
$action = New-ScheduledTaskAction -Execute 'powershell.exe' -Argument '-NoProfile -ExecutionPolicy Bypass -File C:\soapbot-deploy.ps1'
$principal = New-ScheduledTaskPrincipal -UserId 'SYSTEM' -LogonType ServiceAccount -RunLevel Highest
Register-ScheduledTask -TaskName 'SoapbotDeploy' -Action $action -Principal $principal -Force | Out-Null
Start-ScheduledTask -TaskName 'SoapbotDeploy'
(Get-ScheduledTask -TaskName 'SoapbotDeploy').State
"""

result = SESSION.run_ps(PS)
print(result.std_out.decode("utf-8", "replace"))
print(result.std_err.decode("utf-8", "replace")[:500])
