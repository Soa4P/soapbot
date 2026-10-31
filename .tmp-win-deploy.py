"""Provision the Windows test box: files over SMB, commands over WinRM.

Mixing the two is deliberate: SMB is a reliable file channel (WinRM chunked-upload through
many short shells corrupted the script to 2 bytes), and WinRM is the reliable command
channel. Each stage is idempotent and logs to C:\\soapbot-setup\\install.log, which this
runner reads back over SMB so a failure is visible rather than a shrug.
"""

from __future__ import annotations

import sys
import time

import winrm
from impacket.smbconnection import SMBConnection

sys.stdout.reconfigure(encoding="utf-8", errors="replace")

HOST = "152.175.241.226"
USER = "Administrator"
PASSWORD = "zGObanpBktwg8Z3t"

SESSION = winrm.Session(
    f"http://{HOST}:5985/wsman", auth=(USER, PASSWORD), transport="basic"
)

PS = r"""
$ErrorActionPreference = 'Continue'
New-Item -ItemType Directory -Force -Path C:\soapbot-setup | Out-Null
Start-Transcript -Path C:\soapbot-setup\install.log -Force | Out-Null
function Step($t) { Write-Host ("== " + $t + " ==") }

Step 'python'
$py = 'C:\Program Files\Python312\python.exe'
if (-not (Test-Path $py)) {
    $installer = 'C:\soapbot-setup\python-3.12.7-amd64.exe'
    if (-not (Test-Path $installer)) {
        Invoke-WebRequest 'https://www.python.org/ftp/python/3.12.7/python-3.12.7-amd64.exe' -OutFile $installer -UseBasicParsing
    }
    Start-Process $installer -ArgumentList '/quiet','InstallAllUsers=1','PrependPath=1','Include_pip=1' -Wait
}
if (Test-Path $py) { & $py --version } else { Write-Host 'PYTHON-MISSING' }

Step 'checkout'
if (-not (Test-Path 'C:\soapbot\pyproject.toml')) {
    $zip = 'C:\soapbot-setup\soapbot.zip'
    if (-not (Test-Path $zip)) {
        Invoke-WebRequest 'https://codeload.github.com/Soa4P/soapbot/zip/refs/heads/master' -OutFile $zip -UseBasicParsing
    }
    Expand-Archive -Path $zip -DestinationPath 'C:\soapbot-setup\unpacked' -Force
    $inner = Get-ChildItem 'C:\soapbot-setup\unpacked' -Directory | Select-Object -First 1
    if (Test-Path 'C:\soapbot') { Remove-Item 'C:\soapbot' -Recurse -Force }
    Move-Item $inner.FullName 'C:\soapbot'
}
Get-ChildItem 'C:\soapbot' -Name | Select-Object -First 6

Step 'venv'
$venvPy = 'C:\soapbot\.venv\Scripts\python.exe'
if (-not (Test-Path $venvPy)) { & $py -m venv 'C:\soapbot\.venv' }
& $venvPy -m pip install --quiet --upgrade pip
& $venvPy -m pip install --quiet -e C:\soapbot
& $venvPy -c "import soapbot, sys; print('SOAPBOT-OK', soapbot.__version__, sys.version.split()[0])"

Step 'env'
$envFile = 'C:\soapbot\.env'
if (-not (Test-Path $envFile)) { Copy-Item 'C:\soapbot\.env.example' $envFile }
New-Item -ItemType Directory -Force -Path C:\soapbot\data | Out-Null
$pairs = [ordered]@{
  'SOAPBOT_HOST' = '127.0.0.1'
  'SOAPBOT_PORT' = '6185'
  'SOAPBOT_DATA_DIR' = 'C:\soapbot\data'
  'SOAPBOT_ENV_FILE' = 'C:\soapbot\.env'
  'SOAPBOT_ENABLE_RUNTIME' = 'false'
}
$content = Get-Content $envFile
foreach ($key in $pairs.Keys) {
    if ($content -match "^$key=") { $content = $content -replace "^$key=.*", "$key=$($pairs[$key])" }
    else { $content += "$key=$($pairs[$key])" }
}
Set-Content -Path $envFile -Value $content -Encoding ASCII

Step 'panel'
if (-not (Get-NetTCPConnection -LocalPort 6185 -State Listen -ErrorAction SilentlyContinue)) {
    Start-Process $venvPy -ArgumentList '-m','soapbot.cli','start' -WorkingDirectory 'C:\soapbot' -WindowStyle Hidden
}
for ($i = 0; $i -lt 40; $i++) {
    Start-Sleep -Seconds 2
    try {
        $h = Invoke-WebRequest 'http://127.0.0.1:6185/api/health' -UseBasicParsing -TimeoutSec 3
        Write-Host ('HEALTH ' + $h.StatusCode + ' ' + $h.Content); break
    } catch { }
}

Step 'done'
Stop-Transcript | Out-Null
"""


def smb_put(name: str, text: str) -> None:
    data = text.encode("utf-8-sig")  # PowerShell 5.1 needs the BOM to read UTF-8
    cursor = {"at": 0}

    def chunk(_offset: int) -> bytes:
        start = cursor["at"]
        piece = data[start : start + 4096]
        cursor["at"] = start + len(piece)
        return piece

    conn = SMBConnection(HOST, HOST, sess_port=445)
    conn.login(USER, PASSWORD)
    try:
        conn.putFile("C$", f"\\{name}", chunk)
    finally:
        conn.logoff()


def smb_read(name: str) -> str:
    chunks: list[bytes] = []
    conn = SMBConnection(HOST, HOST, sess_port=445)
    conn.login(USER, PASSWORD)
    try:
        conn.getFile("C$", f"\\{name}", chunks.append)
    except Exception:
        return ""
    finally:
        conn.logoff()
    data = b"".join(chunks)
    return data.decode("utf-8", "replace") if data else ""


if __name__ == "__main__":
    smb_put("soapbot-deploy.ps1", PS)
    print("script uploaded:", len(PS), "chars")
    SESSION.run_ps(
        "Start-Process powershell -ArgumentList '-NoProfile','-ExecutionPolicy','Bypass',"
        "'-File','C:\\soapbot-deploy.ps1' -WindowStyle Hidden"
    )
    print("started")
    for _ in range(40):
        time.sleep(20)
        log = smb_read("soapbot-setup\\install.log")
        if "Step 'done'" in log or "HEALTH" in log or "PYTHON-MISSING" in log:
            print(log[-2500:])
            break
        print("...", len(log), "bytes of log")
