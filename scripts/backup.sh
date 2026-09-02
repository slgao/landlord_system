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
STATUS_FILE="$BACKUP_DIR/STATUS"
LOG_FILE="$BACKUP_DIR/backup.log"
LOG_MAX_LINES=2000

mkdir -p "$BACKUP_DIR"

# ── Making a failure visible ─────────────────────────────────────────────────
# The log was never the problem: cron has always redirected into backup.log, and
# all four silently-empty dumps are in there — logged as "Backup successful",
# because the old exit-status check could not tell a failed dump from a good one.
# A log nobody reads also cannot raise an alarm, so a failure now pushes a
# desktop notification and leaves a one-line STATUS file to glance at.

notify() {
    # cron has no desktop environment; point notify-send at the live X session
    # and its D-Bus socket, or it exits silently and the alarm never appears.
    command -v notify-send >/dev/null 2>&1 || return 0
    local uid; uid=$(id -u)
    [ -S "/run/user/$uid/bus" ] || return 0
    DISPLAY="${DISPLAY:-:0}" \
    DBUS_SESSION_BUS_ADDRESS="unix:path=/run/user/$uid/bus" \
    notify-send --urgency="$1" --icon=drive-harddisk "$2" "$3" 2>/dev/null || true
}

write_status() {
    printf '%s\n' "$1" > "$STATUS_FILE"
}

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
#
# pipefail is essential here, not decoration: without it `$?` is *gzip's* status,
# and gzip exits 0 on empty input. A failed pg_dump therefore produced a valid
# 20-byte empty archive, passed the `-s` non-empty test, and was reported as a
# success — while still counting toward the retention below that deletes the good
# ones. Four such phantom backups accumulated before this was caught.
set -o pipefail

docker run --rm postgres:18 pg_dump "$DATABASE_URL" --no-owner --no-acl | gzip > "$FILE"
STATUS=$?

# An empty gzip stream is 20 bytes; a real dump of this database is tens of KB.
# The floor is a sanity check on top of the exit status, catching a dump that
# "succeeded" but produced nothing usable.
MIN_BYTES=1024
SIZE=$(stat -c %s "$FILE" 2>/dev/null || echo 0)

if [ $STATUS -eq 0 ] && [ "$SIZE" -ge "$MIN_BYTES" ]; then
    echo "$(date): Backup successful → $FILE ($SIZE bytes)"
    write_status "OK   $(date '+%Y-%m-%d %H:%M')  $FILE  ($SIZE bytes)"
else
    REASON="pg_dump exit $STATUS, $SIZE bytes (need >= $MIN_BYTES)"
    echo "$(date): Backup FAILED — $REASON" >&2
    write_status "FAIL $(date '+%Y-%m-%d %H:%M')  $REASON"
    notify critical "Landlord backup FAILED" "$REASON — see $LOG_FILE"
    rm -f "$FILE"
    exit 1
fi

# ── Retain last 30 backups ────────────────────────────────────────────────────
find "$BACKUP_DIR" -name "landlord_*.sql.gz" -mtime +30 -delete

# ── Keep the log from growing without bound ───────────────────────────────────
# It had reached 1200+ lines with no rotation configured anywhere.
if [ -f "$LOG_FILE" ] && [ "$(wc -l < "$LOG_FILE")" -gt "$LOG_MAX_LINES" ]; then
    tail -n "$LOG_MAX_LINES" "$LOG_FILE" > "$LOG_FILE.tmp" && mv "$LOG_FILE.tmp" "$LOG_FILE"
fi

echo "$(date): Done. Current backups:"
ls -lh "$BACKUP_DIR"/landlord_*.sql.gz 2>/dev/null
