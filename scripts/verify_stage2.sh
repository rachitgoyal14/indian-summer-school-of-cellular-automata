#!/usr/bin/env bash
# verify_stage2.sh — bring up backend + frontend dev server, run the
# Playwright browser verification, then tear everything down.
#
# Produces screenshot evidence in docs/evidence/stage2/ and prints a JSON
# summary of the automated frontend checks.
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
VENV="$ROOT/.venv/bin/activate"

cleanup() {
  [[ -n "${BACK_PID:-}" ]] && kill "$BACK_PID" 2>/dev/null || true
  [[ -n "${FRONT_PID:-}" ]] && kill "$FRONT_PID" 2>/dev/null || true
}
trap cleanup EXIT

# shellcheck disable=SC1090
source "$VENV"

echo "[verify] starting backend..."
( cd "$ROOT/backend" && CA_PORT=8000 python scripts/run_server.py ) \
  > /tmp/ca_verify_backend.log 2>&1 &
BACK_PID=$!

echo "[verify] starting frontend dev server..."
( cd "$ROOT/frontend" && npm run dev -- --port 5173 ) \
  > /tmp/ca_verify_frontend.log 2>&1 &
FRONT_PID=$!

# wait for both to be ready
for _ in $(seq 1 40); do
  curl -sf http://127.0.0.1:8000/health >/dev/null 2>&1 && break || sleep 0.5
done
for _ in $(seq 1 40); do
  curl -sf http://127.0.0.1:5173/ >/dev/null 2>&1 && break || sleep 0.5
done

echo "[verify] running Playwright checks..."
( cd "$ROOT/frontend" && node scripts/verify_stage2.mjs "http://127.0.0.1:5173/" )
