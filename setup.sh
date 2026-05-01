#!/usr/bin/env bash
# First-time setup for Hausverwaltung.
#
# Usage:
#   cp .env.example .env      # set your password in .env first
#   ./setup.sh
set -euo pipefail

CONTAINER="landlord-pg"

echo ""
echo "=== Hausverwaltung Setup ==="
echo ""

# ── 0. Read credentials from .env ────────────────────────────────────────────
if [ ! -f ".env" ]; then
    if [ -f ".env.example" ]; then
        cp .env.example .env
        echo "Created .env from .env.example."
        echo "  → Edit POSTGRES_PASSWORD in .env, then re-run ./setup.sh"
        exit 0
    else
        echo "ERROR: .env not found. Create it from .env.example first."
        exit 1
    fi
fi

# Load .env (ignore comments and blank lines)
# shellcheck disable=SC2046
export $(grep -v '^\s*#' .env | grep -v '^\s*$' | xargs)

DB_USER="${POSTGRES_USER:-landlord}"
DB_PASS="${POSTGRES_PASSWORD:-changeme}"
DB_NAME="${POSTGRES_DB:-landlord_dev}"
DB_PORT="${POSTGRES_PORT:-5432}"
DATABASE_URL="postgresql://${DB_USER}:${DB_PASS}@localhost:${DB_PORT}/${DB_NAME}"

if [ "$DB_PASS" = "changeme" ]; then
    echo "WARNING: POSTGRES_PASSWORD is still 'changeme'. Consider setting a real password in .env."
    echo ""
fi

# ── 1. Virtual environment ────────────────────────────────────────────────────
if [ ! -d "venv" ]; then
    echo "Creating virtual environment..."
    python3 -m venv venv
fi
# shellcheck disable=SC1091
source venv/bin/activate
echo "Installing dependencies..."
pip install -q -r requirements.txt

# ── 2. PostgreSQL via Docker ──────────────────────────────────────────────────
if ! docker info &>/dev/null; then
    echo ""
    echo "ERROR: Docker is not running."
    if [[ "$(uname)" == "Darwin" || "$(uname)" == "MINGW"* ]]; then
        echo "  → Start Docker Desktop and re-run this script."
    else
        echo "  → Run: sudo systemctl start docker"
        echo "  → Then re-run this script."
    fi
    exit 1
fi

if docker ps -a --format '{{.Names}}' | grep -q "^${CONTAINER}$"; then
    echo "Starting existing database container..."
    docker start "$CONTAINER" &>/dev/null || true
else
    echo "Creating database container..."
    docker run -d \
        --name "$CONTAINER" \
        -e POSTGRES_USER="$DB_USER" \
        -e POSTGRES_PASSWORD="$DB_PASS" \
        -e POSTGRES_DB="$DB_NAME" \
        -p "127.0.0.1:${DB_PORT}:5432" \
        --restart unless-stopped \
        postgres:16 &>/dev/null
    echo "Waiting for PostgreSQL to be ready..."
    sleep 4
fi

# ── 3. Write DATABASE_URL to .env if not already present ─────────────────────
if ! grep -q "^DATABASE_URL=" .env 2>/dev/null; then
    echo "DATABASE_URL=${DATABASE_URL}" >> .env
    echo "Added DATABASE_URL to .env"
fi

# ── 4. Initialise schema ──────────────────────────────────────────────────────
echo "Initialising database schema..."
python3 -c "from db import init_db; init_db()"

# ── 5. Done ───────────────────────────────────────────────────────────────────
echo ""
echo "Setup complete. Start the app with:"
echo ""
echo "  source venv/bin/activate"
echo "  honcho start"
echo ""
echo "  Streamlit → http://localhost:8501"
echo "  FastAPI   → http://localhost:8000"
echo ""
