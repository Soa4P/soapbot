param(
  [string]$HooksPath = '.githooks'
)

$ErrorActionPreference = 'Stop'
$root = Resolve-Path (Join-Path $PSScriptRoot '..')
$target = Join-Path $root $HooksPath
New-Item -ItemType Directory -Force $target | Out-Null
git -C $root config core.hooksPath $HooksPath
Copy-Item (Join-Path $PSScriptRoot 'pre-push') (Join-Path $target 'pre-push') -Force
Write-Host "Installed pre-push secret gate at $target"
