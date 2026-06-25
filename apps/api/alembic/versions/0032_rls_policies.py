"""Row-Level Security policies (DORMANT) — Phase DB-RLS

Revision ID: 0032_rls_policies
Revises: 0031_tenant_perf_idx
Create Date: 2026-06-11

Creates the RLS helper functions + tenant-isolation policies on six
tables, but does NOT enable Row Level Security on them. The policies are
therefore DORMANT — Postgres only enforces a policy once RLS is enabled
on its table (`scripts/rls_activate.py`). This migration is fully
backward compatible: zero runtime behavior change.

Tables covered: leads, campaign_plans (campaigns), generated_content,
audit_events, organizations, users.

The function/policy SQL is sourced from `aicmo.db.rls` so the migration,
the activation scripts, and the tests share ONE definition and cannot
drift.

Reversible: downgrade drops the policies + functions. Because RLS is
never enabled here, downgrade is also a no-op on enforcement.
"""

from __future__ import annotations

from typing import Sequence, Union

from alembic import op

from aicmo.db import rls


revision: str = "0032_rls_policies"
down_revision: Union[str, None] = "0031_tenant_perf_idx"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # 1. Helper functions (idempotent CREATE OR REPLACE).
    op.execute(rls.FUNCTIONS_SQL)
    # 2. Policies on each table (idempotent DROP-then-CREATE).
    #    RLS is intentionally NOT enabled — policies stay dormant.
    for table in rls.RLS_TABLES:
        op.execute(rls.create_policy_sql(table))


def downgrade() -> None:
    for table in rls.RLS_TABLES:
        op.execute(rls.drop_policy_sql(table))
    op.execute(rls.DROP_FUNCTIONS_SQL)
