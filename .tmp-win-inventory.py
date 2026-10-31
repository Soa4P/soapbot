"""Inventory the Windows box through WinRM (no shell quoting in the middle)."""

import sys

import winrm

sys.stdout.reconfigure(encoding="utf-8", errors="replace")

SESSION = winrm.Session(
    "http://152.175.241.226:5985/wsman",
    auth=("Administrator", "zGObanpBktwg8Z3t"),
    transport="basic",
)

SCRIPT = r"""
$os = Get-CimInstance Win32_OperatingSystem
"OS: {0} {1}" -f $os.Caption, $os.Version
"RAM_GB: {0}" -f [math]::Round($os.TotalVisibleMemorySize / 1MB, 1)
$c = Get-PSDrive C
"DISK: used {0} GB, free {1} GB" -f [math]::Round($c.Used/1GB,1), [math]::Round($c.Free/1GB,1)
foreach ($name in 'python','py','git','docker','node') {
  $cmd = Get-Command $name -ErrorAction SilentlyContinue
  if ($cmd) { "FOUND $name -> $($cmd.Source)" } else { "MISSING $name" }
}
foreach ($p in 'C:\Program Files\Tencent','C:\Program Files (x86)\Tencent','C:\Program Files\NapCat','C:\Program Files\Docker') {
  if (Test-Path $p) { "PATH-EXISTS $p" } else { "PATH-NONE $p" }
}
# Installed programs, filtered: the list is the fastest way to see whether QQ NT is there.
Get-ItemProperty 'HKLM:\Software\Microsoft\Windows\CurrentVersion\Uninstall\*','HKLM:\Software\WOW6432Node\Microsoft\Windows\CurrentVersion\Uninstall\*' -ErrorAction SilentlyContinue |
  Where-Object { $_.DisplayName } |
  Select-Object -ExpandProperty DisplayName |
  Sort-Object -Unique |
  Where-Object { $_ -match 'QQ|NapCat|Python|Git|Docker|Tencent' }
"""

result = SESSION.run_ps(SCRIPT)
print(result.std_out.decode("utf-8", "replace"))
if result.std_err:
    print("--- stderr ---")
    print(result.std_err.decode("utf-8", "replace")[:800])
