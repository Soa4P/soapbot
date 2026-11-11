#Requires -Version 5.1
<#
.SYNOPSIS
    Restrict a soapbot install directory to administrators, the OS and one service account,
    and register its scheduled task under that account instead of SYSTEM.

.DESCRIPTION
    Two problems, one script, because neither fix is safe on its own.

    1. ACLs. A directory created under a drive root inherits "Authenticated Users: Modify".
       That one ACE gives every local user — and any process running as one — write access
       to `.env` (which holds SOAPBOT_MASTER_KEY), `data\secret.key`, `data\jwt.key`,
       `data\soapbot.db` and the plugin directory. Overwriting `data\secret.key` is enough
       to make the panel decrypt values of the attacker's choosing, and a file dropped into
       `plugins\` is code execution at the next load. Check the starting point with:
           icacls C:\soapbot

    2. Identity. The task used to run as SYSTEM. `plugins/supervisor.py` refuses to start a
       plugin worker under LocalSystem, because a third-party plugin would then inherit
       SYSTEM and could rewrite the service, the panel binary or the OS itself. A SYSTEM
       install therefore runs with every plugin silently disabled. The fix is not to stop
       refusing — it is to run the bot as an account with nothing to inherit:
       `NT AUTHORITY\LocalService` by default. It is non-admin, needs no stored password,
       and still reaches the network for provider calls (it presents the machine account,
       just like SYSTEM did).

    What the resulting ACL looks like (no inherited entries at all):

        Administrators  Full        recursive
        SYSTEM          Full        recursive
        <account>       Read+Execute on the install directory
        <account>       Modify      on data\, config\, plugins\, panel.log, .env

    `config\` and `.env` are writable because the panel edits them (`api/settings.py`
    rewrites `.env`); `plugins\` because installing a plugin writes there; `data\` because
    that is the database. Everything else — the interpreter, the code, `.venv` — is
    read-only to the bot, so a compromised plugin cannot patch the program it runs inside.

    Idempotent: re-running applies the same DACL and re-registers the same task. Run it on
    an existing install to migrate it off SYSTEM; nothing is moved or deleted.

.PARAMETER Dir
    Install directory. Default C:\soapbot.

.PARAMETER Account
    Account the task runs as. Default NT AUTHORITY\LocalService. A named account needs
    -Password and the "Log on as a batch job" right (secpol.msc -> Local Policies ->
    User Rights Assignment).

.PARAMETER Password
    Password for a named -Account. Passed to the Task Scheduler and never written to disk
    by this script.

.PARAMETER TaskName
    Scheduled task name. Default SoapbotBot — both installers use this name, because two
    tasks with the same port is a mystery that only shows up as "the bot answers twice".

.PARAMETER NoTask
    Only fix the ACLs; leave the scheduled task untouched.

.EXAMPLE
    powershell -ExecutionPolicy Bypass -File scripts\harden-windows.ps1

.EXAMPLE
    powershell -ExecutionPolicy Bypass -File scripts\harden-windows.ps1 -Dir D:\soapbot -NoTask
#>
[CmdletBinding()]
param(
    [string]$Dir = 'C:\soapbot',
    [string]$Account = 'NT AUTHORITY\LocalService',
    [string]$Password = '',
    [string]$TaskName = 'SoapbotBot',
    [switch]$NoTask
)

$ErrorActionPreference = 'Stop'

function Step([string]$Text) { Write-Host "`n== $Text ==" }
function Fail([string]$Text) { Write-Host "`n[x] $Text" -ForegroundColor Red; exit 1 }

# ------------------------------------------------------------------- preconditions
$principal = New-Object Security.Principal.WindowsPrincipal([Security.Principal.WindowsIdentity]::GetCurrent())
if (-not $principal.IsInRole([Security.Principal.WindowsBuiltInRole]::Administrator)) {
    Fail 'run this in an elevated PowerShell: changing a DACL and a service principal needs administrator'
}
if (-not (Test-Path -LiteralPath $Dir)) {
    Fail "no install at $Dir; run scripts\install.ps1 first"
}

function Resolve-Sid([string]$Name) {
    # Already a SID: pass through, so callers can skip name translation entirely.
    if ($Name -match '^S-1-') { return $Name }
    try {
        return (New-Object System.Security.Principal.NTAccount($Name)).Translate(
            [System.Security.Principal.SecurityIdentifier]).Value
    } catch {
        return $null
    }
}

$serviceSid = Resolve-Sid $Account
if (-not $serviceSid) {
    Fail "cannot resolve '$Account' to a SID; create the account first, or pass it as S-1-5-..."
}
if (-not $Password -and $serviceSid -notin @('S-1-5-18', 'S-1-5-19', 'S-1-5-20')) {
    Fail "a named account needs -Password (a scheduled task cannot log a user on without one)"
}
if ($serviceSid -eq 'S-1-5-18') {
    Write-Host '    warning: SYSTEM cannot run plugins — supervisor.py refuses to start a worker as LocalSystem.' -ForegroundColor Yellow
}

# ------------------------------------------------------------------------- 1. ACLs
$FILE_ALL = '0x1F01FF'      # Full control
$READ_EXEC = '0x1200A9'     # Read + execute (no write, no delete)
$MODIFY = '0x1301BF'        # Read + write + delete, no take-ownership

function Set-Dacl {
    <#
        Replace the DACL instead of adding to it. Adding leaves whatever the previous
        policy wrote behind, and "Authenticated Users" from the drive root is exactly the
        entry this script exists to remove. SDDL rather than FileSystemAccessRule because
        it is one deterministic string: OICI for directories so new files inherit, and no
        owner entry, so ownership (and therefore administrative recovery) is untouched.
    #>
    param([string]$Path, [string]$Rights)

    if (-not (Test-Path -LiteralPath $Path)) { return $false }
    $isDir = (Get-Item -LiteralPath $Path -Force).PSIsContainer
    $inherit = if ($isDir) { 'OICI' } else { '' }
    $sddl = 'D:PAI' +
        "(A;$inherit;$FILE_ALL;;;S-1-5-32-544)" +
        "(A;$inherit;$FILE_ALL;;;S-1-5-18)" +
        "(A;$inherit;$Rights;;;$serviceSid)"

    $acl = Get-Acl -LiteralPath $Path
    $acl.SetSecurityDescriptorSddlForm($sddl, [System.Security.AccessControl.AccessControlSections]::Access)
    Set-Acl -LiteralPath $Path -AclObject $acl
    return $true
}

Step "restricting $Dir"

# The root is read-only for the bot. Children inherit that, and the four writable places
# below override it with their own DACL — a child's explicit DACL wins over the inherited
# one, which is why this order works without recursing over thousands of .venv files.
Set-Dacl $Dir $READ_EXEC | Out-Null

foreach ($sub in @('data', 'config', 'plugins')) {
    $path = Join-Path $Dir $sub
    if (Set-Dacl $path $MODIFY) { Write-Host "    $sub : readable and writable" }
}

# panel.log is created by the redirect in the task action; a read-only root would make
# `cmd /c ... >> panel.log` fail before Python ever starts, and the task would look like
# it ran with no output anywhere.
$logPath = Join-Path $Dir 'panel.log'
if (-not (Test-Path -LiteralPath $logPath)) { New-Item -ItemType File -Path $logPath -Force | Out-Null }
Set-Dacl $logPath $MODIFY | Out-Null

# .env exists in both shapes: install.ps1 puts it under data\, deploy\windows-bootstrap.ps1
# beside the code. Both are rewritten by the settings API, so both need to stay writable —
# the point is that only this account can, not that it becomes read-only.
foreach ($envPath in @((Join-Path $Dir '.env'), (Join-Path $Dir 'data\.env'))) {
    if (Set-Dacl $envPath $MODIFY) { Write-Host "    $(Split-Path $envPath -Leaf) : readable and writable" }
}

# The two keys are the highest-value files here: secret.key decrypts every provider key
# and plugin secret, jwt.key mints panel sessions. They keep a Modify grant because the
# bot rotates them, but they are now visible to three principals instead of every user.
foreach ($keyName in @('secret.key', 'jwt.key')) {
    $keyPath = Join-Path $Dir "data\$keyName"
    if (Set-Dacl $keyPath $MODIFY) { Write-Host "    data\$keyName : restricted to administrators and $Account" }
}

# ---------------------------------------------------------------- 2. task principal
if (-not $NoTask) {
    Step "registering $TaskName as $Account"

    $python = Join-Path $Dir '.venv\Scripts\python.exe'
    if (-not (Test-Path -LiteralPath $python)) {
        Fail "no virtualenv at $python; run scripts\install.ps1 first (or pass -NoTask)"
    }

    # Same action, trigger and settings as both installers, kept in one place so an
    # upgrade cannot end up with two tasks racing for the port.
    $action = New-ScheduledTaskAction -Execute 'cmd.exe' `
        -Argument "/c cd /d `"$Dir`" && `"$python`" -m soapbot.cli start >> `"$logPath`" 2>&1"
    $trigger = New-ScheduledTaskTrigger -AtStartup
    $settings = New-ScheduledTaskSettingsSet -AllowStartIfOnBatteries -DontStopIfGoingOnBatteries `
        -ExecutionTimeLimit ([TimeSpan]::Zero) -RestartCount 3 -RestartInterval (New-TimeSpan -Minutes 1)

    if ($Password) {
        # Batch logon is not implied by a password; if this throws, the message below is the
        # one thing an operator can act on without guessing.
        try {
            Register-ScheduledTask -TaskName $TaskName -Action $action -Trigger $trigger `
                -Settings $settings -User $Account -Password $Password -RunLevel Limited -Force | Out-Null
        } catch {
            Fail ("could not register the task for $Account. Grant it 'Log on as a batch job' " +
                "(secpol.msc -> Local Policies -> User Rights Assignment) and re-run. $($_.Exception.Message)")
        }
    } else {
        # ServiceAccount needs no stored password, and LocalService owns no files, no
        # profile and no privileges a plugin could inherit.
        $taskPrincipal = New-ScheduledTaskPrincipal -UserId $serviceSid -LogonType ServiceAccount -RunLevel Limited
        Register-ScheduledTask -TaskName $TaskName -Action $action -Trigger $trigger `
            -Principal $taskPrincipal -Settings $settings -Force | Out-Null
    }
    Write-Host '    registered'
}

# ------------------------------------------------------------------------ 3. report
Step 'effective permissions'
foreach ($path in @($Dir, (Join-Path $Dir 'data'), (Join-Path $Dir 'config'), (Join-Path $Dir 'plugins'))) {
    if (-not (Test-Path -LiteralPath $path)) { continue }
    Write-Host "`n  $path"
    $acl = Get-Acl -LiteralPath $path
    Write-Host ("    inherited : {0}" -f (-not $acl.AreAccessRulesProtected))
    foreach ($rule in @($acl.Access)) {
        Write-Host ("    {0,-45} {1}" -f $rule.IdentityReference.Value, $rule.FileSystemRights)
    }
}

Write-Host ''
Write-Host 'Verify there is no Authenticated Users entry left:' -ForegroundColor Yellow
Write-Host "    icacls `"$Dir`""
Write-Host 'Restart the bot to apply the new identity:'
Write-Host "    schtasks /End /TN $TaskName ; schtasks /Run /TN $TaskName"
