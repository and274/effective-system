#Requires -Version 5.1
<#
.SYNOPSIS
  One-shot deploy from your PC: SSH to server, fix repo ownership if needed, git pull, deploy.sh.
  You do not need to manually log into the server and type commands (SSH still runs on the server for you).

.PARAMETER Push
  Run `git push origin main` from this repo before remote pull (commit first if you have changes).

.PARAMETER SkipChown
  Skip `sudo chown -R user:user REMOTE_ROOT` (use after permissions are already correct).

.EXAMPLE
  .\scripts\deploy-remote.ps1
  .\scripts\deploy-remote.ps1 -Push
#>

param(
  [switch]$Push,
  [switch]$SkipChown
)

$ErrorActionPreference = "Stop"
$ScriptDir = Split-Path -Parent $MyInvocation.MyCommand.Path
$RepoRoot = Resolve-Path (Join-Path $ScriptDir "..")
$SyncEnvPath = Join-Path $ScriptDir "sync.env"

if (-not (Test-Path $SyncEnvPath)) {
  Write-Host "Missing: $SyncEnvPath" -ForegroundColor Red
  Write-Host "Copy scripts/sync.env.example to scripts/sync.env" -ForegroundColor Yellow
  exit 1
}

foreach ($raw in Get-Content -LiteralPath $SyncEnvPath -Encoding UTF8) {
  $line = $raw.Trim()
  if ($line.Length -eq 0) { continue }
  if ($line.StartsWith('#')) { continue }
  $eq = $line.IndexOf('=')
  if ($eq -lt 1) { continue }
  $key = $line.Substring(0, $eq).Trim()
  $val = $line.Substring($eq + 1).Trim()
  if ($key.Length -gt 0) { Set-Item -Path ('Env:' + $key) -Value $val }
}

$hostName = $Env:ZHIMEDIA_SYNC_HOST
$user = $Env:ZHIMEDIA_SYNC_USER
$remoteRoot = $Env:ZHIMEDIA_SYNC_REMOTE_ROOT

if (-not $hostName -or -not $user -or -not $remoteRoot) {
  Write-Host "sync.env must set ZHIMEDIA_SYNC_HOST, ZHIMEDIA_SYNC_USER, ZHIMEDIA_SYNC_REMOTE_ROOT." -ForegroundColor Red
  exit 1
}

$sshTarget = "${user}@${hostName}"

if ($Push) {
  Write-Host "Local: git push origin main ..." -ForegroundColor Cyan
  Set-Location $RepoRoot
  & git push origin main
  if ($LASTEXITCODE -ne 0) { throw "git push failed" }
}

$chownPart = ""
if (-not $SkipChown) {
  $chownPart = "sudo chown -R ${user}:${user} '${remoteRoot}' && "
}

# Multiple git pull attempts (server→GitHub TLS often flakes with GnuTLS -110).
$remoteBash = "${chownPart}cd '${remoteRoot}' && pull_ok=0 && for _try in 1 2 3 4 5 6; do git pull origin main && pull_ok=1 && break; sleep 18; done && test `$pull_ok -eq 1 && SKIP_GIT_PULL=1 bash deploy.sh"

Write-Host "Remote: $sshTarget" -ForegroundColor Cyan
Write-Host $remoteBash -ForegroundColor DarkGray

# Keepalives: long git pull / npm / pip can look "idle" and firewalls/sshd may drop the session (exit 255, "Connection closed").
$sshOpts = @(
  "-o", "ServerAliveInterval=20",
  "-o", "ServerAliveCountMax=120",
  "-o", "TCPKeepAlive=yes",
  "-o", "ConnectTimeout=30"
)
& ssh @sshOpts $sshTarget $remoteBash
if ($LASTEXITCODE -ne 0) {
  Write-Host ""
  Write-Host "If git said 'local changes would be overwritten' (often deploy.sh edited on server), SSH in and run:" -ForegroundColor Yellow
  Write-Host "  cd '${remoteRoot}' && git restore deploy.sh && git pull origin main && SKIP_GIT_PULL=1 bash deploy.sh" -ForegroundColor White
  Write-Host "If you saw 'Connection closed by ... port 22': retry later; or SSH in and run the same line without git restore if tree is clean." -ForegroundColor Yellow
  Write-Host "If git pull shows GnuTLS recv error (-110): retry deploy-remote later, or on server once run: git config --global http.version HTTP/1.1" -ForegroundColor Yellow
  throw "remote deploy failed (ssh exit $LASTEXITCODE)"
}

Write-Host "Done." -ForegroundColor Green
