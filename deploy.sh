#!/usr/bin/env bash
# Server: place at /var/www/zhimedia-sandbox/deploy.sh (or symlink).
# Requires: git, node/npm, python3 venv, pm2; first run creates PM2 apps.
set -e

ROOT="/var/www/zhimedia-sandbox"
cd "$ROOT"
# deploy-remote.ps1 already ran git pull; skip second hit to flaky GitHub from same deploy.
if [[ "${SKIP_GIT_PULL:-}" != "1" ]]; then
  for _try in 1 2 3; do
    git pull origin main && break
    [[ $_try -eq 3 ]] && exit 1
    sleep 5
  done
fi

cd "$ROOT/frontend"
npm install --production
if pm2 describe zhimedia-frontend >/dev/null 2>&1; then
  pm2 restart zhimedia-frontend --update-env
else
  PORT="${PORT:-3000}" pm2 start server.js --name zhimedia-frontend
fi

cd "$ROOT/backend"
if [[ ! -d venv ]]; then
  python3 -m venv venv
fi
# shellcheck disable=SC1091
source venv/bin/activate
pip install -r requirements.txt
GUNICORN="$ROOT/backend/venv/bin/gunicorn"
if pm2 describe zhimedia-backend >/dev/null 2>&1; then
  pm2 restart zhimedia-backend --update-env
else
  pm2 start "$GUNICORN" --name zhimedia-backend --cwd "$ROOT/backend" --interpreter none -- \
    -k gevent -w 2 -b 127.0.0.1:5000 app:app
fi

pm2 list
