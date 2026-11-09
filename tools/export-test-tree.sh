#!/usr/bin/env bash
# Create a source tarball you can copy to another machine for local testing.
set -euo pipefail
ROOT="$(cd "$(dirname "$0")/.." && pwd)"
OUT_DIR="${1:-$HOME/titan-test-export}"
STAMP="$(date -u +%Y%m%d-%H%M%S)"
ARCHIVE="$OUT_DIR/project-titan-$STAMP.tar.gz"
mkdir -p "$OUT_DIR"
cd "$ROOT"
tar czf "$ARCHIVE" \
  --exclude='.git' \
  --exclude='node_modules' \
  --exclude='.venv' \
  --exclude='apps/desktop/out' \
  --exclude='apps/desktop/dist' \
  --exclude='**/__pycache__' \
  --exclude='.pnpm-store' \
  --exclude='third_party/cache' \
  .
echo "Wrote $ARCHIVE"
echo "On the test machine: tar xzf $(basename "$ARCHIVE") && cd Project-titan && see docs/local-test-package.md"
