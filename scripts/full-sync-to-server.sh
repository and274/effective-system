#!/usr/bin/env bash
# 与 full-sync-to-server.ps1 相同：上传 .env 与 frontend/data（需本机 SSH 免密）
set -euo pipefail
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
REPO_ROOT="$(cd "$SCRIPT_DIR/.." && pwd)"
SYNC_ENV="$SCRIPT_DIR/sync.env"

if [[ ! -f "$SYNC_ENV" ]]; then
  echo "缺少 $SYNC_ENV — 请复制 sync.env.example 为 sync.env 并填写。" >&2
  exit 1
fi

set -a
# shellcheck disable=SC1090
source "$SYNC_ENV"
set +a

: "${ZHIMEDIA_SYNC_HOST:?}"
: "${ZHIMEDIA_SYNC_USER:?}"
: "${ZHIMEDIA_SYNC_REMOTE_ROOT:?}"

TARGET="${ZHIMEDIA_SYNC_USER}@${ZHIMEDIA_SYNC_HOST}:${ZHIMEDIA_SYNC_REMOTE_ROOT}"
echo "远端根目录: $TARGET"

upload_file() {
  local src="$1" dest="$2"
  if [[ ! -e "$src" ]]; then
    echo "跳过（本地不存在）: $src"
    return 0
  fi
  echo "上传: $src -> $dest"
  scp "$src" "$dest"
}

upload_file "$REPO_ROOT/frontend/.env" "${TARGET}/frontend/.env"

if [[ -f "$REPO_ROOT/backend/.env" ]]; then
  upload_file "$REPO_ROOT/backend/.env" "${TARGET}/backend/.env"
fi

if [[ -d "$REPO_ROOT/frontend/data" ]]; then
  echo "上传目录: $REPO_ROOT/frontend/data -> ${TARGET}/frontend/"
  scp -r "$REPO_ROOT/frontend/data" "${TARGET}/frontend/"
fi

echo ""
echo "上传完成。请在服务器执行 pm2 restart … --update-env 与 pm2 save。"
