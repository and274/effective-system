#!/usr/bin/env bash
# PM2 入口：强制 UTF-8，避免日志/WSGI 在中文路径下触发 ascii 编码错误
set -euo pipefail
cd "$(dirname "$0")"
export PYTHONUTF8=1
export PYTHONIOENCODING=utf-8
export LANG="${LANG:-C.UTF-8}"
export LC_ALL="${LC_ALL:-C.UTF-8}"
exec ./venv/bin/gunicorn -k gevent -w 2 -b 127.0.0.1:5000 app:app
