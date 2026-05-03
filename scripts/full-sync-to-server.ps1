#Requires -Version 5.1
<#
.SYNOPSIS
  Upload frontend/.env, backend/.env, frontend/data to remote via SSH.
  Default: copy to remote user's home then sudo install into /var/www/... (avoids Permission denied on ubuntu).
  Set ZHIMEDIA_SYNC_DIRECT=1 in sync.env if you already chown the project tree to your SSH user.
#>

$ErrorActionPreference = "Stop"
$ScriptDir = Split-Path -Parent $MyInvocation.MyCommand.Path
$RepoRoot = Resolve-Path (Join-Path $ScriptDir "..")
$SyncEnvPath = Join-Path $ScriptDir "sync.env"

if (-not (Test-Path $SyncEnvPath)) {
  Write-Host "Missing: $SyncEnvPath" -ForegroundColor Red
  Write-Host "Copy scripts/sync.env.example to scripts/sync.env and set HOST, USER, REMOTE_ROOT." -ForegroundColor Yellow
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
  if ($key.Length -gt 0) {
    Set-Item -Path ('Env:' + $key) -Value $val
  }
}

$hostName = $Env:ZHIMEDIA_SYNC_HOST
$user = $Env:ZHIMEDIA_SYNC_USER
$remoteRoot = $Env:ZHIMEDIA_SYNC_REMOTE_ROOT
$direct = ($Env:ZHIMEDIA_SYNC_DIRECT -eq '1')

if (-not $hostName -or -not $user -or -not $remoteRoot) {
  Write-Host "sync.env must set ZHIMEDIA_SYNC_HOST, ZHIMEDIA_SYNC_USER, ZHIMEDIA_SYNC_REMOTE_ROOT (ASCII lines)." -ForegroundColor Red
  exit 1
}

$sshTarget = $user + '@' + $hostName
$target = $sshTarget + ':' + $remoteRoot
$staging = 'zhimedia-staging'

Write-Host ('Remote root: ' + $remoteRoot + '  (ssh ' + $sshTarget + ')') -ForegroundColor Cyan
if ($direct) {
  Write-Host 'Mode: ZHIMEDIA_SYNC_DIRECT=1 (scp straight into REMOTE_ROOT; you need write permission there).' -ForegroundColor DarkYellow
} else {
  Write-Host 'Mode: staging in ~/' + $staging + ' then sudo install (you may be prompted for sudo password once or twice).' -ForegroundColor DarkYellow
}

function Invoke-ScpUpload {
  param([string]$LocalPath, [string]$RemotePath)
  if (-not (Test-Path $LocalPath)) {
    Write-Host "Skip (missing local): $LocalPath" -ForegroundColor DarkGray
    return
  }
  Write-Host "Upload: $LocalPath -> $RemotePath" -ForegroundColor Green
  & scp @($LocalPath, $RemotePath)
  if ($LASTEXITCODE -ne 0) { throw "scp failed: $LocalPath" }
}

function Invoke-Ssh {
  param([string]$RemoteCommand)
  Write-Host ('ssh run: ' + $RemoteCommand) -ForegroundColor DarkGray
  & ssh $sshTarget $RemoteCommand
  if ($LASTEXITCODE -ne 0) { throw "ssh failed: $RemoteCommand" }
}

$feEnv = Join-Path $RepoRoot "frontend\.env"
$beEnv = Join-Path $RepoRoot "backend\.env"
$dataDir = Join-Path $RepoRoot "frontend\data"

if ($direct) {
  Invoke-ScpUpload -LocalPath $feEnv -RemotePath ($target + '/frontend/.env')
  if (Test-Path $beEnv) {
    Invoke-ScpUpload -LocalPath $beEnv -RemotePath ($target + '/backend/.env')
  }
  if (Test-Path $dataDir) {
    Write-Host ('Upload dir: ' + $dataDir + ' -> ' + $target + '/frontend/') -ForegroundColor Green
    & scp -r $dataDir ($target + '/frontend/')
    if ($LASTEXITCODE -ne 0) { throw "scp -r frontend/data failed" }
  }
} else {
  Invoke-Ssh -RemoteCommand ('mkdir -p ~/' + $staging)

  if (Test-Path $feEnv) {
    Invoke-ScpUpload -LocalPath $feEnv -RemotePath ($sshTarget + ':~/' + $staging + '/frontend.env')
    Invoke-Ssh -RemoteCommand ('sudo install -m 0644 -T ~/' + $staging + '/frontend.env ''' + $remoteRoot + '/frontend/.env''')
  } else {
    Write-Host "Skip (missing local): $feEnv" -ForegroundColor DarkGray
  }

  if (Test-Path $beEnv) {
    Invoke-ScpUpload -LocalPath $beEnv -RemotePath ($sshTarget + ':~/' + $staging + '/backend.env')
    Invoke-Ssh -RemoteCommand ('sudo install -m 0644 -T ~/' + $staging + '/backend.env ''' + $remoteRoot + '/backend/.env''')
  }

  if (Test-Path $dataDir) {
    Write-Host ('Upload dir: ' + $dataDir + ' -> ~/' + $staging + '/data then sudo merge') -ForegroundColor Green
    & scp -r $dataDir ($sshTarget + ':~/' + $staging + '/')
    if ($LASTEXITCODE -ne 0) { throw "scp -r frontend/data failed" }
    Invoke-Ssh -RemoteCommand ('sudo rm -rf ''' + $remoteRoot + '/frontend/data'' && sudo cp -a ~/' + $staging + '/data ''' + $remoteRoot + '/frontend/data'' && sudo chown -R ' + $user + ':' + $user + ' ''' + $remoteRoot + '/frontend/data''')
  }
}

Write-Host ""
Write-Host "Done. On server reload env for PM2, e.g.:" -ForegroundColor Yellow
Write-Host ([string]::Format('  ssh {0}@{1}', $user, $hostName)) -ForegroundColor White
Write-Host '  pm2 restart zhimedia-frontend --update-env' -ForegroundColor White
Write-Host '  pm2 restart zhimedia-backend --update-env' -ForegroundColor White
Write-Host '  pm2 save' -ForegroundColor White
