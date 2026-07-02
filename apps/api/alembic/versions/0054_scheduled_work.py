"""Phase 4.4 — scheduled_work (Autonomous Work Scheduler).

Additive table: policy-gated units of marketing work the AI schedules from open
events + goals. No impact on existing data. Nothing executes from here by
default — items await approval.

Revision ID: 0054_scheduled_work
Revises: 0053_operational_goals
Create Date: 2026-07-02
"""

from __future__ import annotations

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "0054_scheduled_work"
down_revision: Union[str, None] = "0053_operational_goals"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "scheduled_work",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
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
        sa.Column("kind", sa.String(length=32), nullable=False),
        sa.Column("action_type", sa.String(length=32), nullable=False),
        sa.Column("title", sa.Text(), nullable=False),
        sa.Column("description", sa.Text(), nullable=False),
        sa.Column("rationale", sa.Text(), nullable=False),
        sa.Column("source_kind", sa.String(length=16), server_default="event", nullable=False),
        sa.Column("source_id", postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column("priority", sa.String(length=16), server_default="medium", nullable=False),
        sa.Column("requires_approval", sa.Boolean(), server_default="true", nullable=False),
        sa.Column("auto_eligible", sa.Boolean(), server_default="false", nullable=False),
        sa.Column("policy_mode", sa.String(length=32), nullable=True),
        sa.Column(
            "status",
            sa.String(length=20),
            server_default="awaiting_approval",
            nullable=False,
        ),
        sa.Column("scheduled_for", sa.DateTime(timezone=True), nullable=True),
        sa.Column("dedupe_key", sa.String(length=160), nullable=False),
        sa.Column(
            "result",
            postgresql.JSONB(astext_type=sa.Text()),
            server_default="{}",
            nullable=False,
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
    op.create_index("ix_scheduled_work_organization_id", "scheduled_work", ["organization_id"])
    op.create_index("ix_scheduled_work_brand_id", "scheduled_work", ["brand_id"])
    op.create_index("ix_scheduled_work_kind", "scheduled_work", ["kind"])
    op.create_index("ix_scheduled_work_status", "scheduled_work", ["status"])
    op.create_index("ix_scheduled_work_dedupe_key", "scheduled_work", ["dedupe_key"])
    op.create_index(
        "ix_scheduled_work_brand_status", "scheduled_work", ["brand_id", "status"]
    )


def downgrade() -> None:
    op.drop_index("ix_scheduled_work_brand_status", "scheduled_work")
    op.drop_index("ix_scheduled_work_dedupe_key", "scheduled_work")
    op.drop_index("ix_scheduled_work_status", "scheduled_work")
    op.drop_index("ix_scheduled_work_kind", "scheduled_work")
    op.drop_index("ix_scheduled_work_brand_id", "scheduled_work")
    op.drop_index("ix_scheduled_work_organization_id", "scheduled_work")
    op.drop_table("scheduled_work")
