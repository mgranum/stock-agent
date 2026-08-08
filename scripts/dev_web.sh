#!/bin/sh
set -eu

PROJECT_DIR=$(CDPATH= cd -- "$(dirname -- "$0")/.." && pwd)
API_PID=""
WEB_PID=""

cleanup() {
    if [ -n "$WEB_PID" ]; then kill "$WEB_PID" 2>/dev/null || true; fi
    if [ -n "$API_PID" ]; then kill "$API_PID" 2>/dev/null || true; fi
}
trap cleanup EXIT INT TERM

cd "$PROJECT_DIR"
STOCK_AGENT_ENV=${STOCK_AGENT_ENV:-test} \
UV_CACHE_DIR=${UV_CACHE_DIR:-/private/tmp/stock-agent-uv-cache} \
uv run uvicorn src.api.app:app --reload --host 127.0.0.1 --port 8000 &
API_PID=$!

cd "$PROJECT_DIR/frontend"
npm run dev -- --host 127.0.0.1 &
WEB_PID=$!

wait "$API_PID" "$WEB_PID"
