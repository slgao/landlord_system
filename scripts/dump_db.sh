#!/usr/bin/env bash
# Export databases from the running Docker container.
# Run this on the source machine before migrating to a new host.
#
# Usage:  ./scripts/dump_db.sh
# Output: backups/landlord_dev.sql  (and backups/landlord_demo.sql if it exists)
set -euo pipefail

CONTAINER="landlord-pg"
BACKUP_DIR="backups"

cd "$(dirname "$0")/.."

if [ ! -f ".env" ]; then
    echo "ERROR: .env not found. Run ./setup.sh first."
    exit 1
fi
# shellcheck disable=SC2046
export $(grep -v '^\s*#' .env | grep -v '^\s*$' | xargs)

DB_USER="${POSTGRES_USER:-landlord}"
DB_NAME="${POSTGRES_DB:-landlord_dev}"

if ! docker info &>/dev/null; then
    echo "ERROR: Docker is not running."
    exit 1
fi

if ! docker ps --format '{{.Names}}' | grep -q "^${CONTAINER}$"; then
    echo "ERROR: Container '$CONTAINER' is not running. Start it with ./setup.sh first."
    exit 1
fi

mkdir -p "$BACKUP_DIR"

echo ""
echo "=== Exporting databases to $BACKUP_DIR/ ==="
echo ""

echo "  Dumping $DB_NAME..."
docker exec "$CONTAINER" pg_dump \
    -U "$DB_USER" --clean --if-exists --no-owner --no-privileges \
    "$DB_NAME" > "$BACKUP_DIR/landlord_dev.sql"
echo "  ✓ $BACKUP_DIR/landlord_dev.sql"

if docker exec "$CONTAINER" psql -U "$DB_USER" -lqt 2>/dev/null \
        | cut -d'|' -f1 | grep -qw landlord_demo; then
    echo "  Dumping landlord_demo..."
    docker exec "$CONTAINER" pg_dump \
        -U "$DB_USER" --clean --if-exists --no-owner --no-privileges \
        landlord_demo > "$BACKUP_DIR/landlord_demo.sql"
    echo "  ✓ $BACKUP_DIR/landlord_demo.sql"
fi

echo ""
echo "Transfer the dump files to your target machine, then run ./scripts/restore_db.sh there."
echo ""
echo "  scp backups/*.sql <user>@<ubuntu-ip>:~/landlord_system/backups/"
echo ""
