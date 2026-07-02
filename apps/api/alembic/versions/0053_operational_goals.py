"""Phase 4.3 — operational_goals (Autonomous Goal Engine).

Additive table: user-defined marketing goals the AI works toward, measured from
real metric snapshots. No impact on existing data.

Revision ID: 0053_operational_goals
Revises: 0052_detected_events
Create Date: 2026-07-02
"""

from __future__ import annotations

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "0053_operational_goals"
down_revision: Union[str, None] = "0052_detected_events"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "operational_goals",
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
        sa.Column("title", sa.Text(), nullable=False),
        sa.Column("metric", sa.String(length=32), nullable=False),
        sa.Column("goal_type", sa.String(length=16), server_default="increase", nullable=False),
        sa.Column("target_value", sa.Float(), nullable=False),
        sa.Column("baseline_value", sa.Float(), server_default="0", nullable=False),
        sa.Column("current_value", sa.Float(), server_default="0", nullable=False),
        sa.Column("timeframe_days", sa.Integer(), nullable=True),
        sa.Column("measurable", sa.Boolean(), server_default="true", nullable=False),
        sa.Column("status", sa.String(length=16), server_default="active", nullable=False),
        sa.Column("achieved_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("last_measured_at", sa.DateTime(timezone=True), nullable=True),
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
    op.create_index("ix_operational_goals_user_id", "operational_goals", ["user_id"])
    op.create_index(
        "ix_operational_goals_organization_id", "operational_goals", ["organization_id"]
    )
    op.create_index("ix_operational_goals_brand_id", "operational_goals", ["brand_id"])
    op.create_index("ix_operational_goals_metric", "operational_goals", ["metric"])
    op.create_index("ix_operational_goals_status", "operational_goals", ["status"])


def downgrade() -> None:
    op.drop_index("ix_operational_goals_status", "operational_goals")
    op.drop_index("ix_operational_goals_metric", "operational_goals")
    op.drop_index("ix_operational_goals_brand_id", "operational_goals")
    op.drop_index("ix_operational_goals_organization_id", "operational_goals")
    op.drop_index("ix_operational_goals_user_id", "operational_goals")
    op.drop_table("operational_goals")
