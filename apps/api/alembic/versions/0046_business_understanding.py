"""Phase 3.1 — AI business-understanding fields on business_profiles.

Adds structured business context the autonomous system reasons over:
products, services, unique_selling_points (JSONB lists), pricing (text),
growth_stage (short string). Purely additive + backward compatible — existing
rows get empty lists / NULL, so no data migration and no downtime.

Revision ID: 0046_business_understanding
Revises: 0045_pg_stat_statements
Create Date: 2026-07-01
"""

from __future__ import annotations

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "0046_business_understanding"
down_revision: Union[str, None] = "0045_pg_stat_statements"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

_JSONB = postgresql.JSONB(astext_type=sa.Text())
_LIST_COLS = ("products", "services", "unique_selling_points")


def upgrade() -> None:
    for col in _LIST_COLS:
        op.add_column(
            "business_profiles",
            sa.Column(col, _JSONB, server_default="[]", nullable=False),
        )
    op.add_column("business_profiles", sa.Column("pricing", sa.Text(), nullable=True))
    op.add_column(
        "business_profiles",
        sa.Column("growth_stage", sa.String(length=32), nullable=True),
    )


def downgrade() -> None:
    op.drop_column("business_profiles", "growth_stage")
    op.drop_column("business_profiles", "pricing")
    for col in reversed(_LIST_COLS):
        op.drop_column("business_profiles", col)
