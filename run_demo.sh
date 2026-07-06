#!/usr/bin/env bash
# Launch the app in demo mode.
#
# Usage:
#   ./run_demo.sh           # seed if empty, then start
#   ./run_demo.sh --reset   # wipe demo DB, re-seed, then start
#
# Setup (first time only):
#   cp .env.demo.example .env.demo   # then fill in DATABASE_URL

set -euo pipefail

DEMO_ENV=".env.demo"
SEED_ARGS=""

for arg in "$@"; do
    case $arg in
        --reset) SEED_ARGS="--reset" ;;
        *) echo "Unknown argument: $arg"; exit 1 ;;
    esac
done

# ── Preflight checks ──────────────────────────────────────────────────────────

if [ ! -f "$DEMO_ENV" ]; then
    echo "ERROR: $DEMO_ENV not found."
    echo ""
    echo "  cp .env.demo.example .env.demo"
    echo "  # Fill in DATABASE_URL, then re-run this script."
    exit 1
fi

# Make sure DATABASE_URL is actually set in the file
if ! grep -qE "^DATABASE_URL=.+" "$DEMO_ENV"; then
    echo "ERROR: DATABASE_URL is empty in $DEMO_ENV."
    echo "  Fill in DATABASE_URL=postgresql://... and re-run."
    exit 1
fi

# Pick up python / honcho from venv if present (use absolute paths so they
# stay valid after we cd into backend/).
ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
if [ -f "$ROOT/venv/bin/python" ]; then
    PYTHON="$ROOT/venv/bin/python"
    HONCHO="$ROOT/venv/bin/honcho"
else
    PYTHON="${PYTHON:-python3}"
    HONCHO="${HONCHO:-honcho}"
fi

# ── Export demo DATABASE_URL (overrides any production URL in the shell) ──────

# shellcheck disable=SC1090
set -a
source "$DEMO_ENV"
set +a

echo "Demo DB: $DATABASE_URL"
echo ""

# Seed from backend/ so imports and relative pdf/ paths resolve correctly.
# shellcheck disable=SC2086
( cd "$ROOT/backend" && "$PYTHON" seed_demo.py $SEED_ARGS )

echo ""

# ── Launch ────────────────────────────────────────────────────────────────────

echo "Starting demo app (API + frontend) — press Ctrl+C to stop."
echo ""
echo "  Frontend  → http://localhost:3000"
echo "  FastAPI   → http://localhost:8000"
echo ""
# honcho reads the Procfile (api + frontend). Pass the demo env explicitly so it
# wins over any .env in the project root.
cd "$ROOT"
"$HONCHO" -e "$DEMO_ENV" start
