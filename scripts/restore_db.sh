#!/usr/bin/env bash
# Restore databases from dump files produced by scripts/dump_db.sh.
# Run this on the target machine AFTER ./setup.sh has completed.
#
# Usage:  ./scripts/restore_db.sh
# Reads:  backups/landlord_dev.sql  (required)
#         backups/landlord_demo.sql (optional)
set -euo pipefail

CONTAINER="landlord-pg"
BACKUP_DIR="backups"

cd "$(dirname "$0")/.."

# ── Load credentials ──────────────────────────────────────────────────────────
if [ ! -f ".env" ]; then
    echo "ERROR: .env not found. Run ./setup.sh first."
    exit 1
fi
# shellcheck disable=SC2046
export $(grep -v '^\s*#' .env | grep -v '^\s*$' | xargs)

DB_USER="${POSTGRES_USER:-landlord}"
DB_NAME="${POSTGRES_DB:-landlord_dev}"

# ── Pre-flight checks ─────────────────────────────────────────────────────────
if ! docker info &>/dev/null; then
    echo "ERROR: Docker is not running."
    exit 1
fi

if ! docker ps --format '{{.Names}}' | grep -q "^${CONTAINER}$"; then
    echo "ERROR: Container '$CONTAINER' is not running. Run ./setup.sh first."
    exit 1
fi

DEV_DUMP="$BACKUP_DIR/landlord_dev.sql"
if [ ! -f "$DEV_DUMP" ]; then
    echo "ERROR: $DEV_DUMP not found."
    echo "       Run ./scripts/dump_db.sh on the source machine and copy the files to $BACKUP_DIR/."
    exit 1
fi

# ── Wait for Postgres to be ready ────────────────────────────────────────────
echo ""
echo "=== Restoring databases ==="
echo ""
echo "Waiting for PostgreSQL to be ready..."
until docker exec "$CONTAINER" pg_isready -U "$DB_USER" -q 2>/dev/null; do
    sleep 1
done
echo "  ✓ PostgreSQL is ready"

# ── Restore main database ─────────────────────────────────────────────────────
echo "  Restoring $DB_NAME from $DEV_DUMP..."
docker exec -i "$CONTAINER" psql -U "$DB_USER" -d "$DB_NAME" -q < "$DEV_DUMP"
echo "  ✓ $DB_NAME restored"

# ── Restore demo database (optional) ─────────────────────────────────────────
DEMO_DUMP="$BACKUP_DIR/landlord_demo.sql"
if [ -f "$DEMO_DUMP" ]; then
    echo "  Restoring landlord_demo from $DEMO_DUMP..."
    # Create the database if it doesn't exist yet
    docker exec "$CONTAINER" psql -U "$DB_USER" -tc \
        "SELECT 1 FROM pg_database WHERE datname = 'landlord_demo'" \
        | grep -q 1 \
        || docker exec "$CONTAINER" createdb -U "$DB_USER" landlord_demo
    docker exec -i "$CONTAINER" psql -U "$DB_USER" -d landlord_demo -q < "$DEMO_DUMP"
    echo "  ✓ landlord_demo restored"
fi

echo ""
echo "Restore complete. Start the app with:"
echo ""
echo "  source venv/bin/activate"
echo "  honcho start"
echo ""
