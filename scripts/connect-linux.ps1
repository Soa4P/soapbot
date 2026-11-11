#Requires -Version 5.1
<#
.SYNOPSIS
    Connect to a Linux server with the Windows built-in OpenSSH client.

.EXAMPLE
    .\connect-linux.ps1 -HostName 203.0.113.10 -User ubuntu -KeyPath "$env:USERPROFILE\.ssh\id_ed25519"

.EXAMPLE
    .\connect-linux.ps1 -HostName 203.0.113.10 -User ubuntu -KeyPath .\server.key -Tunnel

.DESCRIPTION
    Default mode opens an interactive SSH terminal. -Tunnel keeps the panel bound to
    Linux loopback and opens it locally at http://127.0.0.1:<LocalPort>.
    This script never enables RDP or opens a public application port.

    Every value is validated before it reaches ssh. The arguments are already passed as
    an array — no string is ever assembled into a command line — but ssh reads a leading
    '-' as an option, so a hostname of "-oProxyCommand=..." would execute a local
    program before any connection exists. Validation, not quoting, is what stops that.
#>
[CmdletBinding()]
param(
    [Parameter(Mandatory = $true)]
    [Alias('Host')]
    [string]$HostName,
    [string]$User = 'ubuntu',
    [int]$Port = 22,
    [string]$KeyPath = '',
    [switch]$Tunnel,
    [int]$LocalPort = 6185,
    [int]$RemotePort = 6185
)

$ErrorActionPreference = 'Stop'

function Assert-Port([int]$Value, [string]$Name) {
    if ($Value -lt 1 -or $Value -gt 65535) {
        throw "$Name must be between 1 and 65535 (got $Value)."
    }
}

Assert-Port $Port 'Port'
Assert-Port $LocalPort 'LocalPort'
Assert-Port $RemotePort 'RemotePort'

# Hostname, IPv4, or bracketed/bare IPv6. Deliberately narrow: this value ends up as an
# ssh argument, and the alternative to a whitelist is excusing every character ssh might
# interpret.
if ($HostName -notmatch '^[A-Za-z0-9]([A-Za-z0-9._-]*[A-Za-z0-9])?$' -and
    $HostName -notmatch '^\[?[0-9A-Fa-f:.]+\]?$') {
    throw "HostName '$HostName' is not a hostname or IP address."
}
if ($User -notmatch '^[a-z_][a-z0-9._-]{0,31}$') {
    throw "User '$User' is not a valid Linux account name."
}

$ssh = Get-Command ssh.exe -ErrorAction SilentlyContinue
if (-not $ssh) {
    throw 'ssh.exe was not found. Install Windows OpenSSH Client and try again.'
}

$target = "$User@$HostName"
$common = @(
    '-p', $Port.ToString(),
    '-o', 'BatchMode=no',
    '-o', 'ConnectTimeout=10',
    # Pin the host key on first contact and verify it afterwards. Without this, ssh asks
    # once and then accepts whatever answers — which is exactly what a first-connection
    # man-in-the-middle needs. accept-new refuses a *changed* key.
    '-o', 'StrictHostKeyChecking=accept-new'
)
if ($KeyPath) {
    $resolved = Resolve-Path -LiteralPath $KeyPath -ErrorAction Stop
    $common += @('-i', $resolved.Path)
}

if ($Tunnel) {
    Write-Host ("SSH tunnel: http://127.0.0.1:{0} -> {1}:127.0.0.1:{2}" -f $LocalPort, $target, $RemotePort)
    Write-Host 'Keep this window open. Closing it disconnects the tunnel.'
    $forward = "{0}:127.0.0.1:{1}" -f $LocalPort, $RemotePort
    # ExitOnForwardFailure: a tunnel that failed to bind used to leave ssh running and
    # the browser pointing at whatever else held the port.
    & $ssh.Source @common '-o', 'ExitOnForwardFailure=yes' '-o', 'ServerAliveInterval=30' '-N' '-L' $forward $target
    exit $LASTEXITCODE
}

Write-Host ("Connecting to {0}. Type exit to leave the Linux shell." -f $target)
& $ssh.Source @common '-o', 'ServerAliveInterval=30' $target
exit $LASTEXITCODE
