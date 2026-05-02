#Requires -Version 5.1
<#
.SYNOPSIS
  将本地「未进 Git」的前端/后端环境与用户数据，经 SSH 拷贝到云服务器（与 git push 互补）。

.DESCRIPTION
  会尝试上传（存在才传）：
  - frontend/.env
  - backend/.env
  - frontend/data/ 目录

  使用前：将 scripts/sync.env.example 复制为 scripts/sync.env 并填写主机、用户、远端项目根路径。
  本机需已配置 SSH 免密登录到 ZHIMEDIA_SYNC_USER@ZHIMEDIA_SYNC_HOST。
#>

$ErrorActionPreference = "Stop"
$ScriptDir = Split-Path -Parent $MyInvocation.MyCommand.Path
$RepoRoot = Resolve-Path (Join-Path $ScriptDir "..")
$SyncEnvPath = Join-Path $ScriptDir "sync.env"

if (-not (Test-Path $SyncEnvPath)) {
  Write-Host "缺少 $SyncEnvPath" -ForegroundColor Red
  Write-Host "请复制:  scripts/sync.env.example -> scripts/sync.env  并填写 SSH 与远端路径。" -ForegroundColor Yellow
  exit 1
}

foreach ($raw in Get-Content $SyncEnvPath) {
  $line = $raw.Trim()
  if ($line -match '^\s*#' -or $line -eq "") { continue }
  if ($line -match '^([A-Za-z0-9_]+)\s*=\s*(.*)$') {
    Set-Item -Path "Env:$($matches[1])" -Value $matches[2].Trim()
  }
}

$hostName = $Env:ZHIMEDIA_SYNC_HOST
$user = $Env:ZHIMEDIA_SYNC_USER
$remoteRoot = $Env:ZHIMEDIA_SYNC_REMOTE_ROOT

if (-not $hostName -or -not $user -or -not $remoteRoot) {
  Write-Host "sync.env 中需设置 ZHIMEDIA_SYNC_HOST、ZHIMEDIA_SYNC_USER、ZHIMEDIA_SYNC_REMOTE_ROOT" -ForegroundColor Red
  exit 1
}

$target = "${user}@${hostName}:${remoteRoot}"
Write-Host "远端根目录: $target" -ForegroundColor Cyan

function Invoke-ScpUpload {
  param([string]$LocalPath, [string]$RemotePath)
  if (-not (Test-Path $LocalPath)) {
    Write-Host "跳过（本地不存在）: $LocalPath" -ForegroundColor DarkGray
    return
  }
  Write-Host "上传: $LocalPath -> $RemotePath" -ForegroundColor Green
  & scp @($LocalPath, $RemotePath)
  if ($LASTEXITCODE -ne 0) { throw "scp 失败: $LocalPath" }
}

$feEnv = Join-Path $RepoRoot "frontend\.env"
$beEnv = Join-Path $RepoRoot "backend\.env"
$dataDir = Join-Path $RepoRoot "frontend\data"

Invoke-ScpUpload -LocalPath $feEnv -RemotePath "${target}/frontend/.env"

if (Test-Path $beEnv) {
  Invoke-ScpUpload -LocalPath $beEnv -RemotePath "${target}/backend/.env"
}

if (Test-Path $dataDir) {
  Write-Host "上传目录: $dataDir -> ${target}/frontend/" -ForegroundColor Green
  & scp -r $dataDir "${target}/frontend/"
  if ($LASTEXITCODE -ne 0) { throw "scp -r frontend/data 失败" }
}

Write-Host ""
Write-Host "上传完成。请在服务器上使环境变量生效，例如：" -ForegroundColor Yellow
Write-Host "  ssh ${user}@${hostName}" -ForegroundColor White
Write-Host "  pm2 restart zhimedia-frontend --update-env" -ForegroundColor White
Write-Host "  pm2 restart zhimedia-backend --update-env" -ForegroundColor White
Write-Host "  pm2 save" -ForegroundColor White
