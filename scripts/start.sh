#!/usr/bin/env bash
set -euo pipefail
cd "$(dirname "$0")/.."

command -v uv >/dev/null 2>&1 || { echo "未找到 uv，请先安装 uv。" >&2; exit 1; }
command -v npm >/dev/null 2>&1 || { echo "未找到 npm，请先安装 Node.js 22+。" >&2; exit 1; }
if [ ! -d ".venv" ]; then
  uv venv .venv
  uv pip install --python .venv/bin/python -r backend/requirements.txt
fi
if [ ! -d "frontend/node_modules" ]; then
  npm --prefix frontend ci
fi

exec .venv/bin/python scripts/dev.py
