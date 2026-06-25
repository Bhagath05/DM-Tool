#!/usr/bin/env bash
# Automated PostgreSQL backup (P0-1).
#
#   * pg_dump custom format (-Fc) — compressed, parallel-restorable.
#   * Timestamped file in $BACKUP_DIR.
#   * Retention: prunes dumps older than $BACKUP_RETENTION_DAYS.
#
# Local/dev: routes through the docker container (BACKUP_CONTAINER).
# Production (managed PG): set BACKUP_CONTAINER="" and provide libpq env
# (PGHOST/PGPORT/PGUSER/PGPASSWORD) so the host `pg_dump` is used directly.
#
# Cron (daily 02:30):
#   30 2 * * *  /path/to/infra/backup/backup.sh >> /var/log/aicmo-backup.log 2>&1
set -euo pipefail

DB="${PGDATABASE:-aicmo}"
USER="${PGUSER:-aicmo}"
CONTAINER="${BACKUP_CONTAINER-ai-cmo-postgres}"
BACKUP_DIR="${BACKUP_DIR:-$(cd "$(dirname "$0")" && pwd)/dumps}"
RETENTION_DAYS="${BACKUP_RETENTION_DAYS:-14}"

mkdir -p "$BACKUP_DIR"
STAMP="$(date -u +%Y%m%dT%H%M%SZ)"
OUT="$BACKUP_DIR/aicmo_${DB}_${STAMP}.dump"

echo "[backup] $(date -u +%FT%TZ) dumping db=$DB → $OUT"
if [ -n "$CONTAINER" ]; then
  docker exec "$CONTAINER" pg_dump -U "$USER" -d "$DB" -Fc > "$OUT"
else
  pg_dump -U "$USER" -d "$DB" -Fc > "$OUT"
fi

SIZE="$(wc -c < "$OUT" | tr -d ' ')"
if [ "$SIZE" -lt 1000 ]; then
  echo "[backup] ERROR: dump suspiciously small ($SIZE bytes) — aborting" >&2
  rm -f "$OUT"
  exit 1
fi
echo "[backup] OK bytes=$SIZE"

# Retention: delete dumps older than N days.
PRUNED="$(find "$BACKUP_DIR" -name "aicmo_*.dump" -type f -mtime "+${RETENTION_DAYS}" -print -delete | wc -l | tr -d ' ')"
echo "[backup] retention=${RETENTION_DAYS}d pruned=${PRUNED} kept=$(find "$BACKUP_DIR" -name 'aicmo_*.dump' | wc -l | tr -d ' ')"
echo "$OUT"
