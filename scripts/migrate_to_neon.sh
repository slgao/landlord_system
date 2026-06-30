#!/usr/bin/env bash
# Migrate local Docker PostgreSQL → Neon
# Usage: ./migrate_to_neon.sh "postgresql://user:pass@host/db?sslmode=require"
#
# The destructive work (DROP SCHEMA + restore) is run against Neon's DIRECT
# (non-pooler) endpoint. Running a restore through the pooler leaves the pooled
# server connections with the dump's session `search_path = ''`, which then
# makes the app's unqualified queries fail with "relation does not exist".
# Using the direct endpoint keeps the pooler clean.
set -euo pipefail

NEON_URL="${1:-}"
if [ -z "$NEON_URL" ]; then
    echo "Usage: ./migrate_to_neon.sh \"postgresql://...\""
    exit 1
fi

CONTAINER="landlord-pg"
DB_USER="landlord"
DB_NAME="landlord_dev"
DB_PASS="secret"
BACKUP="local_backup.sql"

# Direct (non-pooler) endpoint for schema-altering work; no-op if already direct.
DIRECT_URL="${NEON_URL/-pooler/}"
# Target database name (used to reassert the default search_path).
NEON_DB=$(printf '%s' "$NEON_URL" | sed -E 's#.*://[^/]+/([^/?]+).*#\1#')

cleanup() {
    rm -f "$BACKUP"
    docker exec "$CONTAINER" rm -f /tmp/backup.sql 2>/dev/null || true
}
trap cleanup EXIT

echo ""
echo "=== Neon Migration ==="
echo ""

# ── 1. Dump from local Docker container ──────────────────────────────────────
echo "→ Dumping local database..."
docker exec -e PGPASSWORD="$DB_PASS" "$CONTAINER" \
    pg_dump -U "$DB_USER" "$DB_NAME" --no-owner --no-acl \
    > "$BACKUP"
echo "  Saved to $BACKUP ($(wc -l < "$BACKUP") lines)"

# ── 2. Copy backup into container (avoids stdin redirect issues) ──────────────
echo "→ Copying backup into container..."
docker cp "$BACKUP" "$CONTAINER":/tmp/backup.sql

# ── 3. Wipe Neon schema clean (direct endpoint) ──────────────────────────────
echo "→ Clearing Neon schema (direct endpoint)..."
docker exec "$CONTAINER" psql "$DIRECT_URL" \
    -c "DROP SCHEMA public CASCADE; CREATE SCHEMA public;"

# ── 4. Restore into Neon (direct endpoint, -f for reliability) ───────────────
echo "→ Restoring into Neon (direct endpoint)..."
docker exec "$CONTAINER" psql "$DIRECT_URL" -f /tmp/backup.sql
echo "  Done."

# ── 5. Reassert the default search_path (belt-and-suspenders) ────────────────
echo "→ Restoring default search_path..."
docker exec "$CONTAINER" psql "$DIRECT_URL" \
    -c "ALTER DATABASE \"$NEON_DB\" SET search_path TO \"\$user\", public;"

# ── 6. Sanity check via the app's actual (pooler) URL ────────────────────────
echo ""
echo "→ Row counts on Neon (via the app endpoint, unqualified):"
docker exec "$CONTAINER" psql "$NEON_URL" -c "
SELECT 'properties' AS t, COUNT(*) FROM properties
UNION ALL SELECT 'apartments',  COUNT(*) FROM apartments
UNION ALL SELECT 'tenants',     COUNT(*) FROM tenants
UNION ALL SELECT 'contracts',   COUNT(*) FROM contracts
UNION ALL SELECT 'payments',    COUNT(*) FROM payments;"

echo ""
echo "=== Migration complete ==="
echo ""
echo "Next: update DATABASE_URL in .env to your Neon connection string."
echo ""
echo "  # LOCAL (fallback)"
echo "  # DATABASE_URL=postgresql://landlord:secret@localhost:5432/landlord_dev"
echo ""
echo "  # NEON (active)"
echo "  DATABASE_URL=$NEON_URL"
echo ""
