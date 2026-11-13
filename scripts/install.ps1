#Requires -Version 5.1
<#
.SYNOPSIS
    Install or update soapbot on Windows with one command.

.DESCRIPTION
    Idempotent: an existing data directory is never overwritten, an existing virtual
    environment is reused, and the scheduled task is re-registered with the same
    definition — same name, same account — so re-running an old install migrates it
    instead of leaving two policies behind.

    The script does not print the bootstrap token. It prints the path, because a token
    in a console transcript outlives the token.

.PARAMETER Dir
    Install directory. Default C:\soapbot.

.PARAMETER Port
    Panel port, bound to 127.0.0.1. Default 6185.

.PARAMETER Account
    Account the scheduled task runs as. Default NT AUTHORITY\LocalService.

    Not SYSTEM, and not for a cosmetic reason: `plugins/supervisor.py` refuses to start a
    plugin worker under LocalSystem, so a SYSTEM install runs with every plugin silently
    disabled. LocalService is non-admin, needs no stored password and still reaches the
    network for provider calls.

.PARAMETER Tag
    Install from a pinned tag instead of master (e.g. v0.1.0). Pinned installs are
    reproducible: the downloaded archive cannot change under you the way a branch ref
    can. Omit to follow master.

.EXAMPLE
    irm https://raw.githubusercontent.com/Soa4P/soapbot/master/scripts/install.ps1 | iex

.EXAMPLE
    .\install.ps1 -Dir D:\soapbot -Port 7000

.EXAMPLE
    .\install.ps1 -Tag v0.1.0
#>
[CmdletBinding()]
param(
    [string]$Dir = 'C:\soapbot',
    [int]$Port = 6185,
    [string]$Account = 'NT AUTHORITY\LocalService',
    [string]$Tag = ''
)

$ErrorActionPreference = 'Stop'
$TaskName = 'SoapbotBot'
if ($Tag -and $Tag -notmatch '^v[0-9]') {
    throw "-Tag must look like v0.1.0 (a tag ref, not a branch)"
}
$ZipUrl = if ($Tag) {
    "https://codeload.github.com/Soa4P/soapbot/zip/refs/tags/$Tag"
} else {
    'https://codeload.github.com/Soa4P/soapbot/zip/refs/heads/master'
}

function Write-Step([string]$Message) { Write-Host "==> $Message" -ForegroundColor Cyan }
function Write-Ok([string]$Message) { Write-Host "    $Message" -ForegroundColor Green }

function Resolve-Python {
    foreach ($candidate in @('py -3.12', 'py -3', 'python')) {
        $parts = $candidate.Split(' ')
        $exe = $parts[0]
        $command = Get-Command $exe -ErrorAction SilentlyContinue
        if (-not $command) { continue }
        $args = @()
        if ($parts.Length -gt 1) { $args += $parts[1..($parts.Length - 1)] }
        try {
            $version = & $exe @args -c "import sys; print('%d.%d' % sys.version_info[:2])" 2>$null
        } catch { continue }
        if ($LASTEXITCODE -ne 0) { continue }
        $major, $minor = $version.Trim().Split('.')
        if ([int]$major -eq 3 -and [int]$minor -ge 12) { return @{ Exe = $exe; Args = $args } }
    }
    return $null
}

Write-Step "checking Python 3.12+"
$python = Resolve-Python
if (-not $python) {
    Write-Host "No Python 3.12+ found." -ForegroundColor Red
    Write-Host "Install it from https://www.python.org/downloads/windows/ (tick 'Add python.exe to PATH'), then rerun this script."
    exit 1
}
Write-Ok "found $($python.Exe)"

# Always fetch. An earlier version only downloaded when the directory was missing, so
# "rerun the installer to update" silently kept the old code — the one thing a
# one-command installer has to get right. The archive contains no data/ or .venv, so
# copying over an existing install leaves both alone.
Write-Step "fetching the current code into $Dir"
$zip = Join-Path $env:TEMP 'soapbot-install.zip'
Invoke-WebRequest -Uri $ZipUrl -OutFile $zip -UseBasicParsing
$unpacked = Join-Path $env:TEMP ('soapbot-unpacked-' + [guid]::NewGuid().ToString('N'))
Expand-Archive -LiteralPath $zip -DestinationPath $unpacked -Force
$inner = Get-ChildItem -LiteralPath $unpacked -Directory | Select-Object -First 1
New-Item -ItemType Directory -Path $Dir -Force | Out-Null
Copy-Item -Path (Join-Path $inner.FullName '*') -Destination $Dir -Recurse -Force
Remove-Item -LiteralPath $zip, $unpacked -Recurse -Force -ErrorAction SilentlyContinue
Write-Ok "code updated; data\ and .venv untouched"

$venv = Join-Path $Dir '.venv'
$venvPython = Join-Path $venv 'Scripts\python.exe'
if (-not (Test-Path -LiteralPath $venvPython)) {
    Write-Step "creating virtual environment"
    & $python.Exe @($python.Args) -m venv $venv
    Write-Ok $venv
} else {
    Write-Ok "virtual environment already present"
}

Write-Step "installing dependencies"
Push-Location $Dir
try {
    & $venvPython -m pip install --quiet --upgrade pip
    if (Test-Path -LiteralPath (Join-Path $Dir 'pyproject.toml')) {
        & $venvPython -m pip install --quiet -e .
    } else {
        & $venvPython -m pip install --quiet -r (Join-Path $Dir 'requirements.txt')
    }
    if ($LASTEXITCODE -ne 0) { throw "dependency installation failed" }
} finally {
    Pop-Location
}
Write-Ok "dependencies installed"

$dataDir = Join-Path $Dir 'data'
$envFile = Join-Path $dataDir '.env'
New-Item -ItemType Directory -Path $dataDir -Force | Out-Null
if (-not (Test-Path -LiteralPath $envFile)) {
    Write-Step "writing $envFile"
    @(
        'SOAPBOT_HOST=127.0.0.1'
        "SOAPBOT_PORT=$Port"
        "SOAPBOT_DATA_DIR=$dataDir"
        "SOAPBOT_ENV_FILE=$envFile"
    ) | Set-Content -LiteralPath $envFile -Encoding utf8
    Write-Ok "panel will bind to 127.0.0.1:$Port"
} else {
    Write-Ok "keeping existing $envFile"
}

Write-Step "locking down $Dir and registering $TaskName"
# ACLs and the task principal are one unit: a task running as an account that cannot read
# the install would fail silently at every restart, and an account that can write the
# install can patch the program it is running inside. scripts/harden-windows.ps1 owns
# both, so an existing install is migrated off SYSTEM by simply re-running this script.
#
# Spawned as a separate process on purpose: the script ends with `exit 1` on failure, and
# `irm ... | iex` runs this file inside the caller's session, where a bare `exit` would
# close the operator's console instead of reporting one error.
$harden = Join-Path $Dir 'scripts\harden-windows.ps1'
if (-not (Test-Path -LiteralPath $harden)) { throw "missing $harden; the archive looks incomplete" }
& powershell.exe -NoProfile -ExecutionPolicy Bypass -File $harden -Dir $Dir -Account $Account -TaskName $TaskName
if ($LASTEXITCODE -ne 0) { throw "hardening failed; fix the message above and re-run this script" }
Write-Ok "restricted to $Account"

Write-Step "starting the service"
# Start-ScheduledTask on an already-running task is a no-op, so an update would keep
# the old code in memory and look like the install did nothing. Stop first.
$currentState = (Get-ScheduledTask -TaskName $TaskName -ErrorAction SilentlyContinue).State
if ($currentState -eq 'Running') {
    Stop-ScheduledTask -TaskName $TaskName
    Start-Sleep -Seconds 2
}
Start-ScheduledTask -TaskName $TaskName
$deadline = (Get-Date).AddSeconds(60)
$healthy = $false
while ((Get-Date) -lt $deadline) {
    try {
        $response = Invoke-WebRequest -Uri "http://127.0.0.1:$Port/api/health" -UseBasicParsing -TimeoutSec 3
        if ($response.StatusCode -eq 200) { $healthy = $true; break }
    } catch { Start-Sleep -Seconds 2 }
}
if (-not $healthy) {
    Write-Host "The service did not answer within 60s." -ForegroundColor Yellow
    Write-Host "Check $Dir\panel.log, then rerun this script."
    exit 1
}
Write-Ok "healthy"

Write-Host ''
Write-Host "soapbot is running." -ForegroundColor Green
Write-Host "  panel : http://127.0.0.1:$Port"
Write-Host ''
Write-Host '  FIRST LOGIN - one-time token (ON THIS SERVER, not on your own PC):' -ForegroundColor Yellow
Write-Host "    $dataDir\init_token.txt"
Write-Host '  Open it here, on the server:'
Write-Host "    notepad `"$dataDir\init_token.txt`""
Write-Host '  Already logged in? The file is deleted and a restart will NOT create'
Write-Host '  another one. Recovery: docs\deploy-quickstart.md, section "first login".'
Write-Host ''
Write-Host "  restart: schtasks /End /TN $TaskName && schtasks /Run /TN $TaskName"
Write-Host "  logs  : $Dir\panel.log"
