#!/bin/sh
set -eu

BACKUP_DIR="${BACKUP_DIR:-/backups}"
mkdir -p "${BACKUP_DIR}"

TIMESTAMP=$(date +"%Y%m%d_%H%M%S")
BACKUP_FILE="${BACKUP_DIR}/fsp_draft_${TIMESTAMP}.sql.gz"

echo "[$(date -Iseconds)] Starting PostgreSQL backup for database ${PGDATABASE}..."

pg_dump -h "${PGHOST:-db}" -U "${PGUSER:-postgres}" -d "${PGDATABASE:-fsp_draft}" --clean --if-exists | gzip > "${BACKUP_FILE}"

echo "[$(date -Iseconds)] Backup completed successfully: ${BACKUP_FILE} ($(du -h "${BACKUP_FILE}" | cut -f1))"

# Retention: delete backups older than 7 days
echo "[$(date -Iseconds)] Pruning backups older than 7 days..."
find "${BACKUP_DIR}" -type f -name "fsp_draft_*.sql.gz" -mtime +7 -delete

echo "[$(date -Iseconds)] Backup job finished."
