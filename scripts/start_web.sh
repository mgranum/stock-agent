#!/bin/sh
set -eu

PROJECT_DIR=$(CDPATH= cd -- "$(dirname -- "$0")/.." && pwd)
APP_ENV=${STOCK_AGENT_ENV:-prod}

case "$APP_ENV" in
    test|prod) ;;
    *)
        echo "Ugyldig STOCK_AGENT_ENV: $APP_ENV (bruk test eller prod)." >&2
        exit 2
        ;;
esac

cd "$PROJECT_DIR/frontend"
npm run build

cd "$PROJECT_DIR"
export STOCK_AGENT_ENV="$APP_ENV"
export UV_CACHE_DIR=${UV_CACHE_DIR:-/private/tmp/stock-agent-uv-cache}

if [ "$APP_ENV" = "prod" ]; then
    export STOCK_AGENT_ENABLE_PROD_WRITES=1
else
    unset STOCK_AGENT_ENABLE_PROD_WRITES
fi

echo "Starter Stock Agent i ${APP_ENV}-miljø på http://127.0.0.1:8000"
exec uv run uvicorn src.api.app:app --host 127.0.0.1 --port 8000
