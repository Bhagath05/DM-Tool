"""generated_content table

Revision ID: 0003_generated_content
Revises: 0002_trend_reports
Create Date: 2026-05-19

"""
from __future__ import annotations

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "0003_generated_content"
down_revision: Union[str, None] = "0002_trend_reports"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "generated_content",
        sa.Column("id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("user_id", sa.String(length=255), nullable=False),
        sa.Column(
            "business_profile_id",
            postgresql.UUID(as_uuid=True),
            nullable=False,
        ),
        sa.Column(
            "trend_report_id",
            postgresql.UUID(as_uuid=True),
            nullable=True,
        ),
        sa.Column("content_type", sa.String(length=32), nullable=False),
        sa.Column("platform", sa.String(length=64), nullable=False),
        sa.Column("goal", sa.String(length=255), nullable=False),
        sa.Column("tone", sa.String(length=64), nullable=False),
        sa.Column(
            "strategy",
            postgresql.JSONB(astext_type=sa.Text()),
            nullable=False,
        ),
        sa.Column(
            "output",
            postgresql.JSONB(astext_type=sa.Text()),
            nullable=False,
        ),
        sa.Column(
            "is_saved",
            sa.Boolean(),
            server_default=sa.text("false"),
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
        sa.ForeignKeyConstraint(
            ["business_profile_id"],
            ["business_profiles.id"],
            ondelete="CASCADE",
            name="fk_generated_content_business_profile",
        ),
        sa.ForeignKeyConstraint(
            ["trend_report_id"],
            ["trend_reports.id"],
            ondelete="SET NULL",
            name="fk_generated_content_trend_report",
        ),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(
        "ix_generated_content_user_id", "generated_content", ["user_id"]
    )
    op.create_index(
        "ix_generated_content_business_profile_id",
        "generated_content",
        ["business_profile_id"],
    )
    op.create_index(
        "ix_generated_content_user_created",
        "generated_content",
        ["user_id", sa.text("created_at DESC")],
    )


def downgrade() -> None:
    op.drop_index(
        "ix_generated_content_user_created", table_name="generated_content"
    )
    op.drop_index(
        "ix_generated_content_business_profile_id",
        table_name="generated_content",
    )
    op.drop_index("ix_generated_content_user_id", table_name="generated_content")
    op.drop_table("generated_content")
