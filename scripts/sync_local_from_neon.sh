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
DUMP_FILE="/tmp/neon_sync.sql"

# ── Read credentials from .env ────────────────────────────────────────────────
if [ ! -f "$ENV_FILE" ]; then
    echo "ERROR: .env not found at $ENV_FILE" >&2
    exit 1
fi
# shellcheck disable=SC2046
export $(grep -v '^\s*#' "$ENV_FILE" | grep -v '^\s*$' | xargs)

NEON_URL=$(grep -E '^DATABASE_URL=' "$ENV_FILE" | tail -1 | cut -d= -f2-)

LOCAL_USER="${POSTGRES_USER:-landlord}"
LOCAL_PASS="${POSTGRES_PASSWORD:-changeme}"
LOCAL_DB="${POSTGRES_DB:-landlord_dev}"
LOCAL_PORT="${POSTGRES_PORT:-5432}"
LOCAL_URL="postgresql://${LOCAL_USER}:${LOCAL_PASS}@localhost:${LOCAL_PORT}/${LOCAL_DB}"

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

# ── 1. Dump from Neon using postgres:18 (matches Neon's server version) ───────
# Neon runs a newer PostgreSQL major version than the local Docker server, so
# pg_dump emits session GUCs the local server may not recognise (e.g.
# transaction_timeout, added in PG17). These are harmless top-of-file SETs, but
# an older local server errors on them; strip them so the restore stays clean.
echo "→ Dumping from Neon..."
docker run --rm postgres:18 pg_dump "$NEON_URL" --no-owner --no-acl \
    | grep -vE '^SET (transaction_timeout)\b' > "$DUMP_FILE"
echo "  Done."

# ── 2. Wipe local schema and restore ─────────────────────────────────────────
echo "→ Wiping local schema..."
docker exec landlord-pg psql "$LOCAL_URL" \
    -c "DROP SCHEMA public CASCADE; CREATE SCHEMA public;"

echo "→ Copying dump into container..."
docker cp "$DUMP_FILE" landlord-pg:/tmp/neon_sync.sql

echo "→ Restoring into local Docker..."
docker exec landlord-pg psql "$LOCAL_URL" -f /tmp/neon_sync.sql
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

docker exec landlord-pg rm -f /tmp/neon_sync.sql
rm -f "$DUMP_FILE"

echo ""
echo "=== Sync complete ==="
echo ""
