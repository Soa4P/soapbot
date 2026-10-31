"""What the panel reports on Windows — the same questions we asked the Linux box."""

import json
import sys

import winrm

sys.stdout.reconfigure(encoding="utf-8", errors="replace")

SESSION = winrm.Session(
    "http://152.175.241.226:5985/wsman",
    auth=("Administrator", "zGObanpBktwg8Z3t"),
    transport="basic",
)

PS = r"""
function Get-Json($url) {
  try { (Invoke-WebRequest $url -UseBasicParsing -TimeoutSec 20).Content } catch { "ERR " + $_.Exception.Message }
}
'--- settings ---'
Get-Json 'http://127.0.0.1:6185/api/settings'
'--- protocol scan ---'
Get-Json 'http://127.0.0.1:6185/api/protocol/scan'
'--- napcat status ---'
Get-Json 'http://127.0.0.1:6185/api/protocol/napcat/status'
"""

out = SESSION.run_ps(PS).std_out.decode("utf-8", "replace")
print(out)
