"""trend_reports table

Revision ID: 0002_trend_reports
Revises: 0001_business_profiles
Create Date: 2026-05-19

"""
from __future__ import annotations

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "0002_trend_reports"
down_revision: Union[str, None] = "0001_business_profiles"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "trend_reports",
        sa.Column("id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("user_id", sa.String(length=255), nullable=False),
        sa.Column(
            "status",
            sa.String(length=16),
            server_default=sa.text("'pending'"),
            nullable=False,
        ),
        sa.Column(
            "raw_trends", postgresql.JSONB(astext_type=sa.Text()), nullable=True
        ),
        sa.Column(
            "analysis", postgresql.JSONB(astext_type=sa.Text()), nullable=True
        ),
        sa.Column("analysis_error", sa.Text(), nullable=True),
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
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("user_id", name="uq_trend_reports_user_id"),
    )
    op.create_index("ix_trend_reports_user_id", "trend_reports", ["user_id"])


def downgrade() -> None:
    op.drop_index("ix_trend_reports_user_id", table_name="trend_reports")
    op.drop_table("trend_reports")
