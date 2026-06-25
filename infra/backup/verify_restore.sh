#!/usr/bin/env bash
# Restore-verification test (P0-1): proves a backup is actually restorable.
#
#   1. take a fresh backup of the live db,
#   2. restore it into a throwaway scratch db,
#   3. compare table count + key row counts between source and restore,
#   4. drop the scratch db.
#
# Exit 0 = backup is restorable and consistent; non-zero = FAILED.
# Safe to run on a schedule (e.g. after each nightly backup) as a smoke test.
set -euo pipefail

DB="${PGDATABASE:-aicmo}"
USER="${PGUSER:-aicmo}"
CONTAINER="${BACKUP_CONTAINER-ai-cmo-postgres}"
HERE="$(cd "$(dirname "$0")" && pwd)"
SCRATCH="aicmo_verify_$$"

if [ -n "$CONTAINER" ]; then
  q() { docker exec "$CONTAINER" psql -U "$USER" -d "$1" -t -A -c "$2"; }
else
  q() { PGDATABASE="$1" psql -U "$USER" -t -A -c "$2"; }
fi

echo "[verify] 1/4 backup"
DUMP="$("$HERE/backup.sh" | tail -1)"
echo "[verify]   dump=$DUMP"

echo "[verify] 2/4 restore → $SCRATCH"
"$HERE/restore.sh" "$DUMP" "$SCRATCH" >/dev/null

echo "[verify] 3/4 compare"
SRC_TABLES="$(q "$DB" "select count(*) from information_schema.tables where table_schema='public' and table_type='BASE TABLE';")"
DST_TABLES="$(q "$SCRATCH" "select count(*) from information_schema.tables where table_schema='public' and table_type='BASE TABLE';")"
SRC_ORGS="$(q "$DB" "select count(*) from organizations;")"
DST_ORGS="$(q "$SCRATCH" "select count(*) from organizations;")"
SRC_VER="$(q "$DB" "select version_num from alembic_version;")"
DST_VER="$(q "$SCRATCH" "select version_num from alembic_version;")"

echo "[verify]   tables: src=$SRC_TABLES dst=$DST_TABLES | orgs: src=$SRC_ORGS dst=$DST_ORGS | migration: src=$SRC_VER dst=$DST_VER"

echo "[verify] 4/4 cleanup ($SCRATCH)"
if [ -n "$CONTAINER" ]; then
  docker exec "$CONTAINER" psql -U "$USER" -d postgres -c "DROP DATABASE IF EXISTS \"$SCRATCH\";" >/dev/null
else
  psql -U "$USER" -d postgres -c "DROP DATABASE IF EXISTS \"$SCRATCH\";" >/dev/null
fi

if [ "$SRC_TABLES" = "$DST_TABLES" ] && [ "$SRC_ORGS" = "$DST_ORGS" ] && [ "$SRC_VER" = "$DST_VER" ]; then
  echo "[verify] PASS — backup is restorable and consistent."
  exit 0
fi
echo "[verify] FAIL — restored db does not match source." >&2
exit 1
