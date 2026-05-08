#!/usr/bin/env bash
# Migrate local Docker PostgreSQL → Neon
# Usage: ./migrate_to_neon.sh "postgresql://user:pass@host/db?sslmode=require"
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

# ── 3. Wipe Neon schema clean (in case Alembic already ran there) ─────────────
echo "→ Clearing Neon schema..."
docker exec "$CONTAINER" psql "$NEON_URL" \
    -c "DROP SCHEMA public CASCADE; CREATE SCHEMA public;"

# ── 4. Restore into Neon using -f (reliable, no stdin pipe) ──────────────────
echo "→ Restoring into Neon..."
docker exec "$CONTAINER" psql "$NEON_URL" -f /tmp/backup.sql
echo "  Done."

# ── 5. Sanity check ───────────────────────────────────────────────────────────
echo ""
echo "→ Row counts on Neon:"
docker exec "$CONTAINER" psql "$NEON_URL" -c "
SELECT 'properties' AS t, COUNT(*) FROM public.properties
UNION ALL SELECT 'apartments',  COUNT(*) FROM public.apartments
UNION ALL SELECT 'tenants',     COUNT(*) FROM public.tenants
UNION ALL SELECT 'contracts',   COUNT(*) FROM public.contracts
UNION ALL SELECT 'payments',    COUNT(*) FROM public.payments;"

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
