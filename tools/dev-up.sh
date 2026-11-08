#!/usr/bin/env bash
# Start backing services and the app for development (Section 3).
# Until the supervisor exists (M1), Postgres, Redis and Chroma come from docker-compose.yml (ADR 0020)
# and `pnpm dev` launches the API with a fresh launch token.
#
#   tools/dev-up.sh                 start containers, migrate, run the app
#   tools/dev-up.sh --no-services   use services you started yourself on the same ports
set -euo pipefail
cd "$(dirname "$0")/.."

export TITAN__POSTGRES__PASSWORD="${TITAN__POSTGRES__PASSWORD:-titan}"

if [[ "${1:-}" != "--no-services" ]]; then
  docker compose up -d --wait
fi
pnpm install --frozen-lockfile
uv sync --frozen --all-packages
uv run titan-db upgrade
exec pnpm dev
