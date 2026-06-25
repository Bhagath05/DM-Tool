#!/usr/bin/env bash
# Container start-up for the FastAPI service.
#
# Render Free has no Pre-Deploy hook and no Shell access, so database
# migrations have to run *here* — at container start, before uvicorn binds the
# port. Sequence:
#   1. uv run alembic upgrade head   (create/seed schema; idempotent)
#   2. uv run uvicorn aicmo.main:app (serve)
#
# If migrations fail, we print a clear error and exit non-zero so Render marks
# the deploy as failed instead of serving a half-migrated app.

set -uo pipefail

# Run from this script's directory (apps/api) so alembic.ini and the uv project
# are found regardless of the configured working directory.
cd "$(dirname "$0")"

echo "[start] Applying database migrations: uv run alembic upgrade head"
if ! uv run alembic upgrade head; then
  echo "[start] FATAL: database migrations failed — refusing to start the API server." >&2
  exit 1
fi

echo "[start] Migrations complete. Starting API server on port ${PORT:-8000}."
exec uv run uvicorn aicmo.main:app --host 0.0.0.0 --port "${PORT:-8000}"
