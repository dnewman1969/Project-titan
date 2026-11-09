#!/usr/bin/env bash
# Linux/macOS developer launcher (managed Postgres if pg_ctl 16 is on PATH; else use Docker).
set -euo pipefail
cd "$(dirname "$0")"

export TITAN__REDIS__PASSWORD="${TITAN__REDIS__PASSWORD:-titan-dev}"

redis_ok() {
  (echo >/dev/tcp/127.0.0.1/63790) >/dev/null 2>&1
}

if ! redis_ok; then
  if command -v docker >/dev/null 2>&1; then
    echo "Starting Redis via Docker..."
    docker compose up -d redis --wait
  else
    echo "Redis required on 127.0.0.1:63790 (password: titan-dev). Start redis-server or Docker." >&2
    exit 1
  fi
fi

if ! command -v pg_ctl >/dev/null 2>&1 && command -v docker >/dev/null 2>&1; then
  if ! (echo >/dev/tcp/127.0.0.1/54329) >/dev/null 2>&1; then
    echo "Starting Postgres + Chroma via Docker (managed portable PG used when pg 16 is installed)..."
    docker compose up -d postgres chroma --wait
    export TITAN__POSTGRES__MODE=external
    export TITAN__CHROMA__MODE=external
    export TITAN__POSTGRES__PASSWORD="${TITAN__POSTGRES__PASSWORD:-titan}"
  fi
fi

DESKTOP_ENV=apps/desktop/.env
if [[ ! -f "$DESKTOP_ENV" && -f apps/desktop/.env.example ]]; then
  cp apps/desktop/.env.example "$DESKTOP_ENV"
fi

pnpm install --frozen-lockfile
uv sync --frozen --all-packages
pnpm codegen
exec pnpm dev
