#!/usr/bin/env bash
# Restore a PostgreSQL dump produced by backup.sh (P0-1).
#
#   restore.sh <dump-file> [target-db]
#
# Recreates <target-db> (default: $PGDATABASE) from the custom-format dump.
# DESTRUCTIVE: drops and recreates the target database. Refuses to target the
# live db unless RESTORE_ALLOW_PROD=1 is set (guards against fat-fingering a
# restore over production).
set -euo pipefail

DUMP="${1:?usage: restore.sh <dump-file> [target-db]}"
DB="${PGDATABASE:-aicmo}"
USER="${PGUSER:-aicmo}"
CONTAINER="${BACKUP_CONTAINER-ai-cmo-postgres}"
TARGET="${2:-$DB}"

if [ ! -f "$DUMP" ]; then
  echo "[restore] ERROR: dump not found: $DUMP" >&2
  exit 1
fi
if [ "$TARGET" = "$DB" ] && [ "${RESTORE_ALLOW_PROD:-0}" != "1" ]; then
  echo "[restore] REFUSING to restore over the primary db '$DB'." >&2
  echo "          Pass a scratch target, or set RESTORE_ALLOW_PROD=1 to override." >&2
  exit 2
fi

if [ -n "$CONTAINER" ]; then
  PSQL=(docker exec -i "$CONTAINER" psql -U "$USER" -d postgres -v ON_ERROR_STOP=1)
  RESTORE=(docker exec -i "$CONTAINER" pg_restore -U "$USER" -d "$TARGET" --no-owner)
else
  PSQL=(psql -U "$USER" -d postgres -v ON_ERROR_STOP=1)
  RESTORE=(pg_restore -U "$USER" -d "$TARGET" --no-owner)
fi

echo "[restore] (re)creating db=$TARGET"
"${PSQL[@]}" -c "DROP DATABASE IF EXISTS \"$TARGET\";"
"${PSQL[@]}" -c "CREATE DATABASE \"$TARGET\";"

echo "[restore] restoring $DUMP → $TARGET"
"${RESTORE[@]}" < "$DUMP"
echo "[restore] OK db=$TARGET"
