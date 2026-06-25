"""Advisor outcome learning + intelligence fields

Revision ID: 0039_advisor_outcomes
Revises: 0038_advisor_memory
Create Date: 2026-06-19
"""

from __future__ import annotations

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "0039_advisor_outcomes"
down_revision: Union[str, None] = "0038_advisor_memory"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "advisor_outcomes",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column(
            "brand_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("brands.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column(
            "recommendation_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("advisor_recommendations.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column(
            "evaluation_status",
            sa.String(length=16),
            nullable=False,
            server_default="pending",
        ),
        sa.Column(
            "baseline_snapshot",
            postgresql.JSONB(astext_type=sa.Text()),
            nullable=False,
            server_default=sa.text("'{}'::jsonb"),
        ),
        sa.Column(
            "outcome_snapshot",
            postgresql.JSONB(astext_type=sa.Text()),
            nullable=False,
            server_default=sa.text("'{}'::jsonb"),
        ),
        sa.Column("delta_summary", sa.Text(), nullable=True),
        sa.Column("effectiveness_score", sa.Integer(), nullable=True),
        sa.Column("evaluate_after", sa.DateTime(timezone=True), nullable=False),
        sa.Column("evaluated_at", sa.DateTime(timezone=True), nullable=True),
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
    op.create_index(
        "ix_advisor_outcomes_brand_status_evaluate",
        "advisor_outcomes",
        ["brand_id", "evaluation_status", "evaluate_after"],
    )
    op.create_index(
        "ix_advisor_outcomes_recommendation_id",
        "advisor_outcomes",
        ["recommendation_id"],
        unique=True,
    )

    op.create_table(
        "advisor_effectiveness_scores",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column(
            "brand_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("brands.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("dimension", sa.String(length=32), nullable=False),
        sa.Column("dimension_key", sa.String(length=64), nullable=False),
        sa.Column("sample_size", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("success_rate", sa.Numeric(5, 2), nullable=True),
        sa.Column("avg_effectiveness", sa.Integer(), nullable=True),
        sa.Column("last_computed_at", sa.DateTime(timezone=True), nullable=True),
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
        sa.UniqueConstraint(
            "brand_id",
            "dimension",
            "dimension_key",
            name="uq_advisor_effectiveness_brand_dim_key",
        ),
    )

    op.add_column(
        "advisor_recommendations",
        sa.Column("observation", sa.Text(), nullable=True),
    )
    op.add_column(
        "advisor_recommendations",
        sa.Column("root_cause", sa.Text(), nullable=True),
    )


def downgrade() -> None:
    op.drop_column("advisor_recommendations", "root_cause")
    op.drop_column("advisor_recommendations", "observation")
    op.drop_table("advisor_effectiveness_scores")
    op.drop_index("ix_advisor_outcomes_recommendation_id", table_name="advisor_outcomes")
    op.drop_index(
        "ix_advisor_outcomes_brand_status_evaluate", table_name="advisor_outcomes"
    )
    op.drop_table("advisor_outcomes")
