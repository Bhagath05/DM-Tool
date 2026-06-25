"""tenant columns NOT NULL

Revision ID: 0017_tenant_not_null
Revises: 0016_backfill_orgs_brands
Create Date: 2026-05-30

Final step of the multi-tenancy rollout. Now that 0016 has backfilled
every existing business row with (organization_id, brand_id), we can
safely enforce NOT NULL on both columns across all 16 tables.

After this migration, the SQLAlchemy event listener (added in S1.4)
+ service-layer guards mean it is impossible to insert a business row
without tenant scope.

Downgrade re-allows NULL so 0016 can be safely rolled back.
"""

from __future__ import annotations

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "0017_tenant_not_null"
down_revision: Union[str, None] = "0016_backfill_orgs_brands"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


BUSINESS_TABLES: list[str] = [
    "business_profiles",
    "trend_reports",
    "generated_content",
    "generated_ads",
    "generated_visuals",
    "rendered_visuals",
    "campaign_plans",
    "landing_pages",
    "leads",
    "bundles",
    "social_connections",
    "social_assets",
    "audience_patterns",
    "winning_patterns",
    "campaign_experiments",
    "learning_events",
]


def upgrade() -> None:
    # Safety: re-check there are no NULL rows before forcing the constraint.
    # If 0016 backfill was skipped or partial, this raises with a clear
    # message instead of a confusing alembic crash.
    bind = op.get_bind()
    for table in BUSINESS_TABLES:
        null_count = bind.execute(
            sa.text(
                f"SELECT count(*) FROM {table} "
                "WHERE organization_id IS NULL OR brand_id IS NULL"
            )
        ).scalar()
        if null_count:
            raise RuntimeError(
                f"Cannot enforce NOT NULL on {table}: "
                f"{null_count} row(s) still missing tenant scope. "
                "Run migration 0016 first."
            )

    for table in BUSINESS_TABLES:
        op.alter_column(
            table,
            "organization_id",
            existing_type=postgresql.UUID(as_uuid=True),
            nullable=False,
        )
        op.alter_column(
            table,
            "brand_id",
            existing_type=postgresql.UUID(as_uuid=True),
            nullable=False,
        )


def downgrade() -> None:
    for table in reversed(BUSINESS_TABLES):
        op.alter_column(
            table,
            "brand_id",
            existing_type=postgresql.UUID(as_uuid=True),
            nullable=True,
        )
        op.alter_column(
            table,
            "organization_id",
            existing_type=postgresql.UUID(as_uuid=True),
            nullable=True,
        )
