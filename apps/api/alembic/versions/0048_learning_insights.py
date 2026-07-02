"""Phase 3.6 — learning_insights table (cross-domain Learning Engine).

One row per durable, evidence-backed lesson the Learning Engine distils from a
brand's real history. Purely additive (a new table) — no impact on existing
tables or data. Distinct from learning_events (creative-dimension findings that
feed the GenerationContext); these feed the four reasoning modules.

Revision ID: 0048_learning_insights
Revises: 0047_marketing_strategies
Create Date: 2026-07-02
"""

from __future__ import annotations

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "0048_learning_insights"
down_revision: Union[str, None] = "0047_marketing_strategies"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "learning_insights",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("user_id", sa.String(length=255), nullable=False),
        sa.Column(
            "organization_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("organizations.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column(
            "brand_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("brands.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("category", sa.String(length=32), nullable=False),
        sa.Column("observation", sa.Text(), nullable=False),
        sa.Column(
            "evidence",
            postgresql.JSONB(astext_type=sa.Text()),
            server_default="[]",
            nullable=False,
        ),
        sa.Column("recommendation", sa.Text(), nullable=False),
        sa.Column("expected_result", sa.Text(), nullable=False),
        sa.Column(
            "confidence", sa.Integer(), server_default="50", nullable=False
        ),
        sa.Column(
            "direction",
            sa.String(length=16),
            server_default="positive",
            nullable=False,
        ),
        sa.Column(
            "affected_modules",
            postgresql.JSONB(astext_type=sa.Text()),
            server_default="[]",
            nullable=False,
        ),
        sa.Column("learned_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("expires_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column(
            "source", sa.String(length=16), server_default="auto", nullable=False
        ),
        sa.Column(
            "status", sa.String(length=16), server_default="active", nullable=False
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
    )
    op.create_index("ix_learning_insights_user_id", "learning_insights", ["user_id"])
    op.create_index(
        "ix_learning_insights_organization_id",
        "learning_insights",
        ["organization_id"],
    )
    op.create_index(
        "ix_learning_insights_brand_id", "learning_insights", ["brand_id"]
    )
    op.create_index(
        "ix_learning_insights_category", "learning_insights", ["category"]
    )
    op.create_index(
        "ix_learning_insights_learned_at", "learning_insights", ["learned_at"]
    )
    op.create_index(
        "ix_learning_insights_expires_at", "learning_insights", ["expires_at"]
    )
    op.create_index("ix_learning_insights_status", "learning_insights", ["status"])
    # "active lessons for this brand" — the feedback hot path.
    op.create_index(
        "ix_learning_insights_brand_status",
        "learning_insights",
        ["brand_id", "status"],
    )


def downgrade() -> None:
    op.drop_index("ix_learning_insights_brand_status", "learning_insights")
    op.drop_index("ix_learning_insights_status", "learning_insights")
    op.drop_index("ix_learning_insights_expires_at", "learning_insights")
    op.drop_index("ix_learning_insights_learned_at", "learning_insights")
    op.drop_index("ix_learning_insights_category", "learning_insights")
    op.drop_index("ix_learning_insights_brand_id", "learning_insights")
    op.drop_index("ix_learning_insights_organization_id", "learning_insights")
    op.drop_index("ix_learning_insights_user_id", "learning_insights")
    op.drop_table("learning_insights")
