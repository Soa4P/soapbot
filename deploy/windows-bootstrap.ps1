# One command from a bare Windows box to a running panel.
#
#   powershell -ExecutionPolicy Bypass -File windows-bootstrap.ps1
#
# Same shape as the Linux installer, for the same reason: the person in front of the machine
# should not have to assemble Python, a checkout and a virtualenv by hand. What differs is
# the tail — there is no systemd here, so it ends with the panel started and the URL printed.
#
# Deliberately NOT included: QQ and NapCat. Both are interactive installers (QQ wants a
# login, NapCat wants the QQ it will attach to), and silently installing a chat client on
# someone's machine is not a convenience. The panel detects them once they are there.
#
# Notes learned on a real Server 2019 host:
#   * `$ProgressPreference = 'SilentlyContinue'` is not cosmetic — Invoke-WebRequest draws a
#     progress bar per chunk and is several times slower with it, which turns a 25 MB
#     download into minutes;
#   * a process started inside a WinRM session is killed when the session ends, so anything
#     that must outlive the call has to be started through Task Scheduler, not Start-Process.

[CmdletBinding()]
param(
    [string]$Dir = 'C:\soapbot',
    [int]$Port = 6185,
    [string]$HostAddress = '127.0.0.1',
    [switch]$Start
)

$ErrorActionPreference = 'Stop'
$ProgressPreference = 'SilentlyContinue'

function Step($text) { Write-Host ("`n== " + $text + " ==") }
function Fail($text) { Write-Host ("`n[x] " + $text) -ForegroundColor Red; exit 1 }

New-Item -ItemType Directory -Force -Path (Split-Path $Dir -Parent) | Out-Null

# ---------------------------------------------------------------------- 1. python
Step 'python 3.12'
$python = Join-Path $Dir '.venv\Scripts\python.exe'
if (-not (Test-Path $python)) {
    $systemPython = 'C:\Program Files\Python312\python.exe'
    if (-not (Test-Path $systemPython)) {
        $installer = Join-Path $env:TEMP 'python-3.12.7-amd64.exe'
        if (-not (Test-Path $installer)) {
            Write-Host '   downloading python (25 MB)'
            Invoke-WebRequest 'https://www.python.org/ftp/python/3.12.7/python-3.12.7-amd64.exe' -OutFile $installer -UseBasicParsing
        }
        Write-Host '   installing silently'
        Start-Process $installer -ArgumentList '/quiet', 'InstallAllUsers=1', 'PrependPath=1', 'Include_pip=1' -Wait
    }
    if (-not (Test-Path $systemPython)) { Fail 'python did not install; install 3.12 from python.org and re-run' }
    Write-Host "   $(& $systemPython --version)"
    & $systemPython -m venv (Join-Path $Dir '.venv')
}

# --------------------------------------------------------------------- 2. checkout
Step "checkout in $Dir"
if (-not (Test-Path (Join-Path $Dir 'pyproject.toml'))) {
    $zip = Join-Path $env:TEMP 'soapbot.zip'
    Invoke-WebRequest 'https://codeload.github.com/Soa4P/soapbot/zip/refs/heads/master' -OutFile $zip -UseBasicParsing
    $unpacked = Join-Path $env:TEMP 'soapbot-unpacked'
    if (Test-Path $unpacked) { Remove-Item $unpacked -Recurse -Force }
    Expand-Archive -Path $zip -DestinationPath $unpacked -Force
    $inner = Get-ChildItem $unpacked -Directory | Select-Object -First 1
    Move-Item $inner.FullName $Dir
}

# ------------------------------------------------------------------------ 3. install
Step 'installing (editable)'
& $python -m pip install --quiet --upgrade pip
& $python -m pip install --quiet -e $Dir
& $python -c "import soapbot, sys; print('   soapbot', soapbot.__version__, 'on', sys.version.split()[0])"

# --------------------------------------------------------------------------- 4. env
Step 'configuration'
$envFile = Join-Path $Dir '.env'
if (-not (Test-Path $envFile)) { Copy-Item (Join-Path $Dir '.env.example') $envFile }
New-Item -ItemType Directory -Force -Path (Join-Path $Dir 'data') | Out-Null

# Absolute paths, for the same reason as on Linux: a service started from another working
# directory would otherwise create a second data directory and look empty afterwards.
$pairs = [ordered]@{
    'SOAPBOT_HOST'           = $HostAddress
    'SOAPBOT_PORT'           = "$Port"
    'SOAPBOT_DATA_DIR'       = (Join-Path $Dir 'data')
    'SOAPBOT_ENV_FILE'       = $envFile
}
$lines = Get-Content $envFile
foreach ($key in $pairs.Keys) {
    if ($lines -match "^$key=") { $lines = $lines -replace "^$key=.*", "$key=$($pairs[$key])" }
    else { $lines += "$key=$($pairs[$key])" }
}
Set-Content -Path $envFile -Value $lines -Encoding ASCII

# ------------------------------------------------------------------------- 5. start
if ($Start) {
    Step 'starting the panel'
    # Registered as a scheduled task, NOT `Start-Process`. Two reasons, both learned the hard
    # way: a process started inside a remote/WinRM session is killed when that session ends
    # (so "it was running" one minute and gone the next, with nothing in any log), and a
    # hidden child of an RDP session dies when the operator closes the window — which for a
    # bot means it stops answering the moment you stop watching it.
    $action = New-ScheduledTaskAction -Execute 'cmd.exe' `
        -Argument "/c cd /d $Dir && `"$python`" -m soapbot.cli start >> `"$Dir\panel.log`" 2>&1"
    $principal = New-ScheduledTaskPrincipal -UserId 'SYSTEM' -LogonType ServiceAccount -RunLevel Highest
    $settings = New-ScheduledTaskSettingsSet -AllowStartIfOnBatteries -DontStopIfGoingOnBatteries `
        -RestartCount 3 -RestartInterval (New-TimeSpan -Minutes 1)
    Register-ScheduledTask -TaskName 'SoapbotPanel' -Action $action -Principal $principal `
        -Settings $settings -Force | Out-Null
    Start-ScheduledTask -TaskName 'SoapbotPanel'
    for ($i = 0; $i -lt 45; $i++) {
        Start-Sleep -Seconds 2
        try {
            $health = Invoke-WebRequest "http://$HostAddress`:$Port/api/health" -UseBasicParsing -TimeoutSec 3
            Write-Host ("   " + $health.Content)
            break
        } catch { }
    }
}

$token = & $python -m soapbot.cli token 2>$null
Write-Host ''
Write-Host '===================================================================='
Write-Host "  panel : http://${HostAddress}:$Port"
Write-Host "  token : $token"
Write-Host "  data  : $(Join-Path $Dir 'data')"
Write-Host '  next  : install NapCat (napcat.napneko.icu), log the bot QQ in, then'
Write-Host '          open page 07 and press "Scan this machine".'
Write-Host '===================================================================='
