#!/usr/bin/env bash
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$ROOT_DIR"

PYTHON_BIN="${PYTHON_BIN:-python3}"
HOST="${HOST:-127.0.0.1}"
PORT="${PORT:-8000}"
FRONTEND_DIR="${GUANKAN_FRONTEND_DIR:-$ROOT_DIR/frontend/dist}"

export GUANKAN_FRONTEND_DIR="$FRONTEND_DIR"

if [ -f ".env.local" ]; then
  set -a
  # shellcheck disable=SC1091
  . ".env.local"
  set +a
fi

if [ ! -d ".venv" ]; then
  "$PYTHON_BIN" -m venv .venv
fi

# shellcheck disable=SC1091
. ".venv/bin/activate"
python -m pip install -r backend/requirements.txt

if [ ! -f "$FRONTEND_DIR/index.html" ]; then
  (cd frontend && npm install && npm run build)
fi

cd backend
exec python -m uvicorn app.main:app --host "$HOST" --port "$PORT"
