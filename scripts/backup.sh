#!/bin/bash
# Backup landlord_system database to a local compressed file.
# Reads DATABASE_URL from .env — works for both Neon (cloud) and local Docker.
# Scheduled: daily at 22:00 Europe/Berlin (see README for cron setup).
# Keeps the last 30 daily backups.

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_DIR="$(dirname "$SCRIPT_DIR")"
ENV_FILE="$PROJECT_DIR/.env"

BACKUP_DIR="$HOME/landlord_backups"
DATE=$(date +%Y%m%d_%H%M%S)
FILE="$BACKUP_DIR/landlord_$DATE.sql.gz"

mkdir -p "$BACKUP_DIR"

# ── Read DATABASE_URL from .env ───────────────────────────────────────────────
if [ ! -f "$ENV_FILE" ]; then
    echo "$(date): ERROR — .env not found at $ENV_FILE" >&2
    exit 1
fi
DATABASE_URL=$(grep -E '^DATABASE_URL=' "$ENV_FILE" | tail -1 | cut -d= -f2-)

if [ -z "$DATABASE_URL" ]; then
    echo "$(date): ERROR — DATABASE_URL not set in .env" >&2
    exit 1
fi

# ── Dump using a postgres:18 container (matches Neon's server version) ────────
# docker run --rm pulls the image once then reuses it; no persistent container needed.
docker run --rm postgres:18 pg_dump "$DATABASE_URL" --no-owner --no-acl | gzip > "$FILE"

if [ $? -eq 0 ] && [ -s "$FILE" ]; then
    echo "$(date): Backup successful → $FILE"
else
    echo "$(date): Backup FAILED" >&2
    rm -f "$FILE"
    exit 1
fi

# ── Retain last 30 backups ────────────────────────────────────────────────────
find "$BACKUP_DIR" -name "landlord_*.sql.gz" -mtime +30 -delete

echo "$(date): Done. Current backups:"
ls -lh "$BACKUP_DIR"/landlord_*.sql.gz 2>/dev/null
