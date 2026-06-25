"""bundles table

Revision ID: 0009_bundles
Revises: 0008_business_profile_v2
Create Date: 2026-05-23

Phase 3.1 — Campaign Bundle Engine. One table, additive. Stores a thin
linking record between coordinated assets — the actual content lives in
generated_content / generated_ads / generated_visuals / campaign_plans,
referenced by UUID inside the `pieces` JSONB column.
"""
from __future__ import annotations

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "0009_bundles"
down_revision: Union[str, None] = "0008_business_profile_v2"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "bundles",
        sa.Column("id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("user_id", sa.String(length=255), nullable=False),
        sa.Column(
            "business_profile_id", postgresql.UUID(as_uuid=True), nullable=False
        ),
        sa.Column(
            "landing_page_id", postgresql.UUID(as_uuid=True), nullable=True
        ),
        sa.Column("theme", sa.String(length=255), nullable=False),
        sa.Column("objective", sa.String(length=32), nullable=False),
        sa.Column(
            "duration_days", sa.Integer(), nullable=False, server_default="14"
        ),
        sa.Column(
            "pieces",
            postgresql.JSONB(astext_type=sa.Text()),
            nullable=False,
            server_default=sa.text("'[]'::jsonb"),
        ),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.ForeignKeyConstraint(
            ["business_profile_id"], ["business_profiles.id"], ondelete="CASCADE"
        ),
        sa.ForeignKeyConstraint(
            ["landing_page_id"], ["landing_pages.id"], ondelete="SET NULL"
        ),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_bundles_user_id", "bundles", ["user_id"])
    op.create_index(
        "ix_bundles_business_profile_id", "bundles", ["business_profile_id"]
    )
    op.create_index(
        "ix_bundles_landing_page_id", "bundles", ["landing_page_id"]
    )


def downgrade() -> None:
    op.drop_index("ix_bundles_landing_page_id", table_name="bundles")
    op.drop_index("ix_bundles_business_profile_id", table_name="bundles")
    op.drop_index("ix_bundles_user_id", table_name="bundles")
    op.drop_table("bundles")
