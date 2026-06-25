"""business tables tenant columns

Revision ID: 0015_tenant_columns
Revises: 0014_rbac_foundation
Create Date: 2026-05-30

Phase 1 — second step. Adds nullable `organization_id` + `brand_id`
columns to every existing business table. Two indices per table:

  - (brand_id, created_at DESC)  → for tenant-scoped lists
  - (organization_id)            → for org-level rollups + audit

Columns are NULLABLE here. They get backfilled in 0016 and flipped to
NOT NULL in 0017. Keeping them nullable means this migration is
completely safe for existing data — no row needs touching.

Tables touched (16):
    business_profiles, trend_reports, generated_content,
    generated_ads, generated_visuals, rendered_visuals,
    campaign_plans, landing_pages, leads, bundles,
    social_connections, social_assets, audience_patterns,
    winning_patterns, campaign_experiments, learning_events
"""

from __future__ import annotations

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "0015_tenant_columns"
down_revision: Union[str, None] = "0014_rbac_foundation"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


# All 16 business tables that hold tenant-owned data.
# performance_signals and experiment_results inherit tenancy via their
# parent FK (social_assets → brand, campaign_experiments → brand), so
# they don't need direct columns. Queries traverse the join.
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
    for table in BUSINESS_TABLES:
        op.add_column(
            table,
            sa.Column(
                "organization_id",
                postgresql.UUID(as_uuid=True),
                nullable=True,
            ),
        )
        op.add_column(
            table,
            sa.Column(
                "brand_id",
                postgresql.UUID(as_uuid=True),
                nullable=True,
            ),
        )
        op.create_foreign_key(
            f"fk_{table}_organization_id",
            table,
            "organizations",
            ["organization_id"],
            ["id"],
            ondelete="CASCADE",
        )
        op.create_foreign_key(
            f"fk_{table}_brand_id",
            table,
            "brands",
            ["brand_id"],
            ["id"],
            ondelete="CASCADE",
        )
        # Hot index: list-by-brand, newest first.
        op.create_index(
            f"ix_{table}_brand_id_created_at",
            table,
            ["brand_id", sa.text("created_at DESC")],
        )
        # Cooler index: org-level rollups + audit lookups.
        op.create_index(
            f"ix_{table}_organization_id",
            table,
            ["organization_id"],
        )


def downgrade() -> None:
    for table in reversed(BUSINESS_TABLES):
        op.drop_index(f"ix_{table}_organization_id", table_name=table)
        op.drop_index(f"ix_{table}_brand_id_created_at", table_name=table)
        op.drop_constraint(
            f"fk_{table}_brand_id", table, type_="foreignkey"
        )
        op.drop_constraint(
            f"fk_{table}_organization_id", table, type_="foreignkey"
        )
        op.drop_column(table, "brand_id")
        op.drop_column(table, "organization_id")
