"""One status call: task state, install log tail, and whether the pieces exist."""

import sys

import winrm
from impacket.smbconnection import SMBConnection

sys.stdout.reconfigure(encoding="utf-8", errors="replace")

HOST = "152.175.241.226"
SESSION = winrm.Session(
    f"http://{HOST}:5985/wsman", auth=("Administrator", "zGObanpBktwg8Z3t"), transport="basic"
)

probe = r"""
$task = Get-ScheduledTask -TaskName 'SoapbotDeploy' -ErrorAction SilentlyContinue
if ($task) { 'TASK ' + $task.State } else { 'TASK none' }
'PYTHON ' + (Test-Path 'C:\Program Files\Python312\python.exe')
'REPO ' + (Test-Path 'C:\soapbot\pyproject.toml')
'VENV ' + (Test-Path 'C:\soapbot\.venv\Scripts\python.exe')
try {
  $h = Invoke-WebRequest 'http://127.0.0.1:6185/api/health' -UseBasicParsing -TimeoutSec 3
  'HEALTH ' + $h.Content
} catch { 'HEALTH down' }
"""
result = SESSION.run_ps(probe)
print(result.std_out.decode("utf-8", "replace"))

conn = SMBConnection(HOST, HOST, sess_port=445)
conn.login("Administrator", "zGObanpBktwg8Z3t")
chunks: list[bytes] = []
try:
    conn.getFile("C$", "\\soapbot-setup\\install.log", chunks.append)
    data = b"".join(chunks)
    text = data.decode("utf-16-le", "replace") if b"\x00" in data else data.decode("utf-8", "replace")
    print("--- install.log tail ---")
    print(text[-1500:])
except Exception as exc:
    print("no log:", type(exc).__name__, str(exc)[:60])
conn.logoff()
