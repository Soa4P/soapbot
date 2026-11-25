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
    [string]$Account = 'NT AUTHORITY\LocalService',
    # Optional pin for the source archive. Without it the download relies on TLS alone,
    # which is the honest limit of a bootstrap that has no release-hash feed yet.
    [string]$ExpectedSha256 = '',
    [switch]$Start
)

$ErrorActionPreference = 'Stop'
$ProgressPreference = 'SilentlyContinue'

function Step($text) { Write-Host ("`n== " + $text + " ==") }
function Fail($text) { Write-Host ("`n[x] " + $text) -ForegroundColor Red; exit 1 }

# ---- downloads go into an admin-only directory, always fresh ------------------------
# The old shape downloaded to `$env:TEMP\python-3.12.7-amd64.exe` and *reused the file if
# it already existed*. %TEMP% is writable by the invoking user, so anyone who could drop
# that file before the installer ran got code executed by the elevated process — a UAC
# bypass with a predictable name (audit S-DEP-01/02). Two changes: a random directory whose
# ACL grants only SYSTEM and Administrators, and never reusing an existing download.
$SetupRoot = Join-Path $env:ProgramData ('soapbot-setup-' + [guid]::NewGuid().ToString('N'))
New-Item -ItemType Directory -Force -Path $SetupRoot | Out-Null
& icacls.exe $SetupRoot /inheritance:r `
    /grant '*S-1-5-18:(OI)(CI)F' `
    /grant '*S-1-5-32-544:(OI)(CI)F' | Out-Null
if ($LASTEXITCODE -ne 0) {
    Fail "could not lock down $SetupRoot; refusing to download into a directory other users can write"
}
$script:cleanup = $SetupRoot
trap { if (Test-Path $script:cleanup) { Remove-Item $script:cleanup -Recurse -Force -ErrorAction SilentlyContinue } }

function Assert-AuthenticodeSigned($path, $expectedSubject) {
    # Hash pinning needs a list to keep current; an Authenticode check is the control the
    # publisher already provides and it cannot go stale. Both status and signer identity
    # are checked: "Valid" alone would accept any certificate that chains to a trusted root.
    $sig = Get-AuthenticodeSignature -FilePath $path
    if ($sig.Status -ne 'Valid') {
        Fail "$path is not validly signed (status: $($sig.Status)); refusing to execute it"
    }
    if ($sig.SignerCertificate.Subject -notmatch $expectedSubject) {
        Fail "$path is signed by someone else: $($sig.SignerCertificate.Subject)"
    }
    Write-Host "   signature ok: $($sig.SignerCertificate.Subject)"
}

New-Item -ItemType Directory -Force -Path (Split-Path $Dir -Parent) | Out-Null

# ---------------------------------------------------------------------- 1. python
Step 'python 3.12'
$python = Join-Path $Dir '.venv\Scripts\python.exe'
if (-not (Test-Path $python)) {
    $systemPython = 'C:\Program Files\Python312\python.exe'
    if (-not (Test-Path $systemPython)) {
        # Always a fresh name inside the locked-down setup root — no reuse, no %TEMP%.
        $installer = Join-Path $SetupRoot 'python-3.12.7-amd64.exe'
        Write-Host '   downloading python (25 MB)'
        Invoke-WebRequest 'https://www.python.org/ftp/python/3.12.7/python-3.12.7-amd64.exe' -OutFile $installer -UseBasicParsing
        # Verified before execution, not after: the whole point is that this file runs
        # elevated. python.org signs its installers with the PSF certificate.
        Assert-AuthenticodeSigned $installer 'O=Python Software Foundation'
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
    $zip = Join-Path $SetupRoot 'soapbot.zip'
    Invoke-WebRequest 'https://codeload.github.com/Soa4P/soapbot/zip/refs/heads/master' -OutFile $zip -UseBasicParsing
    $digest = (Get-FileHash -Algorithm SHA256 -LiteralPath $zip).Hash.ToLower()
    # No publisher signature exists for a codeload zip, so this is the strongest check
    # available: TLS for transport, an optional operator-supplied pin, and the hash printed
    # either way so it can be compared against a release note by hand.
    if ($ExpectedSha256) {
        if ($digest -ne $ExpectedSha256.ToLower()) {
            Fail "archive hash mismatch`n      got  $digest`n      want $($ExpectedSha256.ToLower())"
        }
        Write-Host '   archive hash matches the pin'
    } else {
        Write-Host "   archive sha256: $digest"
        Write-Host '   (pass -ExpectedSha256 to make this a hard check)' -ForegroundColor DarkGray
    }
    $unpacked = Join-Path $SetupRoot 'unpacked'
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
    #
    # The task definition lives in scripts/harden-windows.ps1, not here. Two installers
    # writing the same task name with different principals is worse than two names:
    # whichever ran last would silently decide both who the bot is and whether plugins
    # can run at all. Harden also sets the ACLs — a task whose account cannot read the
    # install fails at boot with nothing in panel.log.
    $harden = Join-Path $Dir 'scripts\harden-windows.ps1'
    if (-not (Test-Path -LiteralPath $harden)) { Fail "missing $harden; the archive looks incomplete" }
    & powershell.exe -NoProfile -ExecutionPolicy Bypass -File $harden -Dir $Dir -Account $Account
    if ($LASTEXITCODE -ne 0) { Fail 'hardening failed; fix the message above and re-run' }
    Start-ScheduledTask -TaskName 'SoapbotBot'
    for ($i = 0; $i -lt 45; $i++) {
        Start-Sleep -Seconds 2
        try {
            $health = Invoke-WebRequest "http://$HostAddress`:$Port/api/health" -UseBasicParsing -TimeoutSec 3
            Write-Host ("   " + $health.Content)
            break
        } catch { }
    }
}

$tokenPath = Join-Path $Dir 'data\init_token.txt'
Write-Host ''
Write-Host '===================================================================='
Write-Host "  panel  : http://${HostAddress}:$Port"
Write-Host ''
# Not printed, for the same reason as scripts/install.ps1: a token echoed into a console
# transcript outlives the token, and this one is single-use. Say WHERE (on this server,
# not the operator's laptop) and give a command that can be pasted verbatim.
Write-Host '  FIRST LOGIN - one-time token (ON THIS SERVER, not on your own PC):' -ForegroundColor Yellow
Write-Host "    $tokenPath"
Write-Host '  Open it here, on the server:'
Write-Host "    notepad `"$tokenPath`""
Write-Host '  Already logged in? The file is deleted and a restart will NOT create'
Write-Host '  another one. Recovery: docs\deploy-quickstart.md, section "first login".'
Write-Host ''
Write-Host "  data   : $(Join-Path $Dir 'data')"
Write-Host '  restart: schtasks /End /TN SoapbotBot && schtasks /Run /TN SoapbotBot'
Write-Host '  next   : install NapCat (napcat.napneko.icu), log the bot QQ in, then'
Write-Host '           open page 07 and press "Scan this machine".'
Write-Host '===================================================================='
