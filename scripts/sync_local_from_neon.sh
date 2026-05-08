#!/bin/bash
# Pull latest Neon data into the local Docker PostgreSQL.
# Run this on any machine to make its local Docker mirror Neon exactly.
#
# Usage: ./scripts/sync_local_from_neon.sh
#
# Prerequisites: landlord-pg Docker container must be running.

set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_DIR="$(dirname "$SCRIPT_DIR")"
ENV_FILE="$PROJECT_DIR/.env"

CONTAINER="landlord-pg"
LOCAL_URL="postgresql://landlord:secret@localhost:5432/landlord_dev"
DUMP_FILE="/tmp/neon_sync.sql"

# ── Read Neon DATABASE_URL from .env ──────────────────────────────────────────
if [ ! -f "$ENV_FILE" ]; then
    echo "ERROR: .env not found at $ENV_FILE" >&2
    exit 1
fi
NEON_URL=$(grep -E '^DATABASE_URL=' "$ENV_FILE" | tail -1 | cut -d= -f2-)

if [ -z "$NEON_URL" ]; then
    echo "ERROR: DATABASE_URL not set in .env" >&2
    exit 1
fi

if [[ "$NEON_URL" == *localhost* ]]; then
    echo "ERROR: DATABASE_URL points to localhost — switch .env to Neon first." >&2
    exit 1
fi

# ── Check container is running ────────────────────────────────────────────────
if ! docker ps --filter "name=^${CONTAINER}$" --filter "status=running" --format "{{.Names}}" | grep -q "$CONTAINER"; then
    echo "ERROR: Container '$CONTAINER' is not running. Start it first:" >&2
    echo "  docker start $CONTAINER" >&2
    exit 1
fi

echo ""
echo "=== Sync local Docker ← Neon ==="
echo ""

# ── 1. Dump from Neon ─────────────────────────────────────────────────────────
echo "→ Dumping from Neon..."
docker exec landlord-pg pg_dump "$NEON_URL" --no-owner --no-acl -f "$DUMP_FILE"
echo "  Done."

# ── 2. Wipe local schema and restore ─────────────────────────────────────────
echo "→ Wiping local schema..."
docker exec landlord-pg psql "$LOCAL_URL" \
    -c "DROP SCHEMA public CASCADE; CREATE SCHEMA public;"

echo "→ Restoring into local Docker..."
docker exec landlord-pg psql "$LOCAL_URL" -f "$DUMP_FILE"
echo "  Done."

# ── 3. Sanity check ───────────────────────────────────────────────────────────
echo ""
echo "→ Row counts (local Docker now mirrors Neon):"
docker exec landlord-pg psql "$LOCAL_URL" -c "
SELECT 'properties' AS t, COUNT(*) FROM public.properties
UNION ALL SELECT 'apartments',  COUNT(*) FROM public.apartments
UNION ALL SELECT 'tenants',     COUNT(*) FROM public.tenants
UNION ALL SELECT 'contracts',   COUNT(*) FROM public.contracts
UNION ALL SELECT 'payments',    COUNT(*) FROM public.payments;"

docker exec landlord-pg rm -f "$DUMP_FILE"

echo ""
echo "=== Sync complete ==="
echo ""
