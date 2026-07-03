"""Phase 6.3 — AI creative brief.

One tenant-scoped table `creative_brief` holding a GROUNDED brief (business
profile + strategy + campaign + content). Additive — no rewrite, no backfill.

Revision ID: 0059_creative_brief
Revises: 0058_content_ops
Create Date: 2026-07-03
"""

from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

from alembic import op

revision: str = "0059_creative_brief"
down_revision: str | None = "0058_content_ops"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

UUID = postgresql.UUID(as_uuid=True)
JSONB = postgresql.JSONB(astext_type=sa.Text())


def upgrade() -> None:
    op.create_table(
        "creative_brief",
        sa.Column("id", UUID, primary_key=True),
        sa.Column(
            "organization_id",
            UUID,
            sa.ForeignKey("organizations.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column(
            "brand_id",
            UUID,
            sa.ForeignKey("brands.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("user_id", sa.String(255), nullable=True),
        # Plain UUIDs — no cross-module ORM FK (creative-core boundary rule).
        sa.Column("campaign_id", UUID, nullable=True),
        sa.Column("content_id", UUID, nullable=True),
        sa.Column("strategy_id", UUID, nullable=True),
        sa.Column("title", sa.String(200), nullable=False),
        sa.Column("objective", sa.String(120), nullable=True),
        sa.Column("brief", JSONB, server_default="{}", nullable=False),
        sa.Column("grounded_in", JSONB, server_default="[]", nullable=False),
        sa.Column("confidence", sa.Integer(), server_default="0", nullable=False),
        sa.Column("reason", sa.Text(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
    )
    op.create_index("ix_creative_brief_brand_id", "creative_brief", ["brand_id"])
    op.create_index("ix_creative_brief_organization_id", "creative_brief", ["organization_id"])


def downgrade() -> None:
    op.drop_index("ix_creative_brief_organization_id", table_name="creative_brief")
    op.drop_index("ix_creative_brief_brand_id", table_name="creative_brief")
    op.drop_table("creative_brief")
