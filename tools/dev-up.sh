#!/usr/bin/env bash
# Start the app for development (Section 3). Electron starts titan-supervisor, which migrates the
# database and starts the API (M1). Backing services:
#
#   tools/dev-up.sh               docker compose up; the supervisor treats Postgres and Chroma as external
#   tools/dev-up.sh --no-compose  containers you already started (same as above, minus `docker compose up`)
#   tools/dev-up.sh --managed     no Docker: the supervisor runs portable Postgres and Chroma itself
#                                 (Redis/Memurai is always yours, on 63790 with requirepass)
set -euo pipefail
cd "$(dirname "$0")/.."

mode="${1:-compose}"
export TITAN__REDIS__PASSWORD="${TITAN__REDIS__PASSWORD:-titan-dev}"
case "$mode" in
  compose | --no-compose)
    export TITAN__POSTGRES__MODE=external TITAN__CHROMA__MODE=external
    export TITAN__POSTGRES__PASSWORD="${TITAN__POSTGRES__PASSWORD:-titan}"
    [[ "$mode" == "compose" ]] && docker compose up -d --wait
    ;;
  --managed) ;;
  *)
    echo "usage: $0 [--no-compose | --managed]" >&2
    exit 2
    ;;
esac
pnpm install --frozen-lockfile
uv sync --frozen --all-packages
exec pnpm dev
