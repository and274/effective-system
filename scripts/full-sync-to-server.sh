#!/usr/bin/env bash
# Same as full-sync-to-server.ps1: upload .env and frontend/data.
# Default: stage in ~/zhimedia-staging then sudo install (ubuntu-friendly).
# ZHIMEDIA_SYNC_DIRECT=1 -> scp straight into REMOTE_ROOT (needs write permission).
set -euo pipefail
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
REPO_ROOT="$(cd "$SCRIPT_DIR/.." && pwd)"
SYNC_ENV="$SCRIPT_DIR/sync.env"
STAGING="zhimedia-staging"

if [[ ! -f "$SYNC_ENV" ]]; then
  echo "Missing $SYNC_ENV — copy sync.env.example to sync.env" >&2
  exit 1
fi

set -a
# shellcheck disable=SC1090
source "$SYNC_ENV"
set +a

: "${ZHIMEDIA_SYNC_HOST:?}"
: "${ZHIMEDIA_SYNC_USER:?}"
: "${ZHIMEDIA_SYNC_REMOTE_ROOT:?}"

SSH_TARGET="${ZHIMEDIA_SYNC_USER}@${ZHIMEDIA_SYNC_HOST}"
TARGET="${SSH_TARGET}:${ZHIMEDIA_SYNC_REMOTE_ROOT}"

echo "Remote: ${ZHIMEDIA_SYNC_REMOTE_ROOT} (ssh ${SSH_TARGET})"

run_ssh() {
  echo "+ ssh $SSH_TARGET $*"
  ssh "$SSH_TARGET" "$@"
}

if [[ "${ZHIMEDIA_SYNC_DIRECT:-}" == "1" ]]; then
  echo "Mode: DIRECT scp"
  [[ -f "$REPO_ROOT/frontend/.env" ]] && scp "$REPO_ROOT/frontend/.env" "${TARGET}/frontend/.env"
  [[ -f "$REPO_ROOT/backend/.env" ]] && scp "$REPO_ROOT/backend/.env" "${TARGET}/backend/.env"
  if [[ -d "$REPO_ROOT/frontend/data" ]]; then
    scp -r "$REPO_ROOT/frontend/data" "${TARGET}/frontend/"
  fi
else
  echo "Mode: staging + sudo"
  run_ssh "mkdir -p ~/${STAGING}"
  if [[ -f "$REPO_ROOT/frontend/.env" ]]; then
    scp "$REPO_ROOT/frontend/.env" "${SSH_TARGET}:~/${STAGING}/frontend.env"
    run_ssh "sudo install -m 0644 -T ~/${STAGING}/frontend.env '${ZHIMEDIA_SYNC_REMOTE_ROOT}/frontend/.env'"
  fi
  if [[ -f "$REPO_ROOT/backend/.env" ]]; then
    scp "$REPO_ROOT/backend/.env" "${SSH_TARGET}:~/${STAGING}/backend.env"
    run_ssh "sudo install -m 0644 -T ~/${STAGING}/backend.env '${ZHIMEDIA_SYNC_REMOTE_ROOT}/backend/.env'"
  fi
  if [[ -d "$REPO_ROOT/frontend/data" ]]; then
    scp -r "$REPO_ROOT/frontend/data" "${SSH_TARGET}:~/${STAGING}/"
    run_ssh "sudo rm -rf '${ZHIMEDIA_SYNC_REMOTE_ROOT}/frontend/data' && sudo cp -a ~/${STAGING}/data '${ZHIMEDIA_SYNC_REMOTE_ROOT}/frontend/data' && sudo chown -R ${ZHIMEDIA_SYNC_USER}:${ZHIMEDIA_SYNC_USER} '${ZHIMEDIA_SYNC_REMOTE_ROOT}/frontend/data'"
  fi
fi

echo ""
echo "Done. On server: pm2 restart … --update-env && pm2 save"
