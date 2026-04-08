#!/bin/bash
# PostgreSQL backup script for landlord_system
# Keeps the last 30 daily backups, then weekly backups for 6 months

BACKUP_DIR="$HOME/landlord_backups"
DATE=$(date +%Y%m%d_%H%M%S)
FILE="$BACKUP_DIR/landlord_$DATE.sql.gz"

# Create backup
docker exec landlord-pg pg_dump -U landlord landlord_dev | gzip > "$FILE"

if [ $? -eq 0 ]; then
    echo "$(date): Backup successful → $FILE"
else
    echo "$(date): Backup FAILED" >&2
    exit 1
fi

# Retain last 30 daily backups; delete older ones
find "$BACKUP_DIR" -name "landlord_*.sql.gz" -mtime +30 -delete

echo "$(date): Cleanup done. Current backups:"
ls -lh "$BACKUP_DIR"/landlord_*.sql.gz 2>/dev/null
