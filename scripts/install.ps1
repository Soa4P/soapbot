#Requires -Version 5.1
<#
.SYNOPSIS
    Install or update soapbot on Windows with one command.

.DESCRIPTION
    Idempotent: an existing data directory is never overwritten, an existing virtual
    environment is reused, and an existing scheduled task is left alone unless -Force.

    The script does not print the bootstrap token. It prints the path, because a token
    in a console transcript outlives the token.

.PARAMETER Dir
    Install directory. Default C:\soapbot.

.PARAMETER Port
    Panel port, bound to 127.0.0.1. Default 6185.

.PARAMETER Force
    Re-register the scheduled task and reinstall dependencies.

.EXAMPLE
    irm https://raw.githubusercontent.com/Soa4P/soapbot/master/scripts/install.ps1 | iex

.EXAMPLE
    .\install.ps1 -Dir D:\soapbot -Port 7000
#>
[CmdletBinding()]
param(
    [string]$Dir = 'C:\soapbot',
    [int]$Port = 6185,
    [switch]$Force
)

$ErrorActionPreference = 'Stop'
$TaskName = 'SoapbotBot'
$ZipUrl = 'https://codeload.github.com/Soa4P/soapbot/zip/refs/heads/master'

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

if (-not (Test-Path -LiteralPath $Dir)) {
    Write-Step "downloading soapbot into $Dir"
    $zip = Join-Path $env:TEMP 'soapbot-install.zip'
    Invoke-WebRequest -Uri $ZipUrl -OutFile $zip -UseBasicParsing
    $unpacked = Join-Path $env:TEMP ('soapbot-unpacked-' + [guid]::NewGuid().ToString('N'))
    Expand-Archive -LiteralPath $zip -DestinationPath $unpacked -Force
    $inner = Get-ChildItem -LiteralPath $unpacked -Directory | Select-Object -First 1
    New-Item -ItemType Directory -Path $Dir -Force | Out-Null
    Copy-Item -Path (Join-Path $inner.FullName '*') -Destination $Dir -Recurse -Force
    Remove-Item -LiteralPath $zip, $unpacked -Recurse -Force -ErrorAction SilentlyContinue
    Write-Ok "code extracted"
} else {
    Write-Step "reusing $Dir"
    Write-Ok "existing data directory kept as-is"
}

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

Write-Step "registering scheduled task $TaskName"
$existing = Get-ScheduledTask -TaskName $TaskName -ErrorAction SilentlyContinue
if ($existing -and -not $Force) {
    Write-Ok "task already registered (use -Force to replace)"
} else {
    if ($existing) { Unregister-ScheduledTask -TaskName $TaskName -Confirm:$false }
    $action = New-ScheduledTaskAction -Execute 'cmd.exe' `
        -Argument "/c cd /d `"$Dir`" && `"$venvPython`" -m soapbot.cli start >> `"$Dir\panel.log`" 2>&1"
    $trigger = New-ScheduledTaskTrigger -AtStartup
    $principal = New-ScheduledTaskPrincipal -UserId 'SYSTEM' -LogonType ServiceAccount -RunLevel Highest
    $settings = New-ScheduledTaskSettingsSet -AllowStartIfOnBatteries -DontStopIfGoingOnBatteries `
        -ExecutionTimeLimit ([TimeSpan]::Zero) -RestartCount 3 -RestartInterval (New-TimeSpan -Minutes 1)
    Register-ScheduledTask -TaskName $TaskName -Action $action -Trigger $trigger `
        -Principal $principal -Settings $settings -Force | Out-Null
    Write-Ok "registered"
}

Write-Step "starting the service"
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
Write-Host "  token : $dataDir\init_token.txt   (open it on this machine; it is not printed here)"
Write-Host "  restart: schtasks /End /TN $TaskName && schtasks /Run /TN $TaskName"
Write-Host "  logs  : $Dir\panel.log"
