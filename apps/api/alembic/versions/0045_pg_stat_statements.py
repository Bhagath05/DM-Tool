"""P1 hardening — enable pg_stat_statements for slow-query observability.

Creates the extension (no-op if already present). REQUIRES the library to be
preloaded via `shared_preload_libraries=pg_stat_statements` in the server
config + a restart — see infra/docker-compose.yml (the `command:` override)
and the prod runbook. The extension exposes `pg_stat_statements`, which the
monitor cron reads to detect slow queries.

Revision ID: 0045_pg_stat_statements
Revises: 0044_fk_indexes
Create Date: 2026-06-24
"""

from __future__ import annotations

from typing import Sequence, Union

from alembic import op

revision: str = "0045_pg_stat_statements"
down_revision: Union[str, None] = "0044_fk_indexes"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.execute("CREATE EXTENSION IF NOT EXISTS pg_stat_statements")


def downgrade() -> None:
    op.execute("DROP EXTENSION IF EXISTS pg_stat_statements")
