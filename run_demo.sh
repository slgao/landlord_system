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

# Pick up python / streamlit from venv if present
if [ -f "venv/bin/python" ]; then
    PYTHON="venv/bin/python"
    STREAMLIT="venv/bin/streamlit"
else
    PYTHON="${PYTHON:-python3}"
    STREAMLIT="${STREAMLIT:-streamlit}"
fi

# ── Export demo DATABASE_URL (overrides any production URL in the shell) ──────

# shellcheck disable=SC1090
set -a
source "$DEMO_ENV"
set +a

echo "Demo DB: $DATABASE_URL"
echo ""

# ── Seed (skipped automatically if DB already has data) ───────────────────────

# shellcheck disable=SC2086
"$PYTHON" seed_demo.py $SEED_ARGS

echo ""

# ── Launch ────────────────────────────────────────────────────────────────────

echo "Starting demo app — press Ctrl+C to stop."
echo ""
"$STREAMLIT" run app.py
