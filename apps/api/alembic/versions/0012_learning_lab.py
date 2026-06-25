"""learning lab

Revision ID: 0012_learning_lab
Revises: 0011_social_intelligence
Create Date: 2026-05-28

Phase 1B — the Campaign Learning Lab. Three tables:

- campaign_experiments  → provenance row per generation
- experiment_results    → perf snapshot once the asset has run
- learning_events       → evidence-backed insights derived from a
                          cluster of experiments + results

All three carry (sample_size, confidence_score, evidence) so the UI can
*show its work* on every assertion. See modules/learning/models.py for
the design rationale.
"""

from __future__ import annotations

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "0012_learning_lab"
down_revision: Union[str, None] = "0011_social_intelligence"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # campaign_experiments
    op.create_table(
        "campaign_experiments",
        sa.Column("id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("user_id", sa.String(length=255), nullable=False),
        sa.Column(
            "source_asset_type", sa.String(length=32), nullable=False
        ),
        sa.Column(
            "source_asset_id",
            postgresql.UUID(as_uuid=True),
            nullable=False,
        ),
        sa.Column("platform", sa.String(length=32), nullable=True),
        sa.Column("goal", sa.Text(), nullable=True),
        sa.Column("hypothesis", sa.Text(), nullable=True),
        sa.Column(
            "inherited_patterns",
            postgresql.JSONB(astext_type=sa.Text()),
            nullable=False,
            server_default=sa.text("'[]'::jsonb"),
        ),
        sa.Column(
            "variable_choices",
            postgresql.JSONB(astext_type=sa.Text()),
            nullable=False,
            server_default=sa.text("'{}'::jsonb"),
        ),
        sa.Column(
            "context_snapshot",
            postgresql.JSONB(astext_type=sa.Text()),
            nullable=False,
            server_default=sa.text("'{}'::jsonb"),
        ),
        sa.Column(
            "status",
            sa.String(length=16),
            nullable=False,
            server_default="pending",
        ),
        sa.Column(
            "sample_size",
            sa.Integer(),
            nullable=False,
            server_default="0",
        ),
        sa.Column(
            "confidence_score",
            sa.Numeric(precision=3, scale=2),
            nullable=False,
            server_default="0.5",
        ),
        sa.Column(
            "evidence",
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
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(
        "ix_campaign_experiments_user_id",
        "campaign_experiments",
        ["user_id"],
    )
    op.create_index(
        "ix_campaign_experiments_source_asset_type",
        "campaign_experiments",
        ["source_asset_type"],
    )
    op.create_index(
        "ix_campaign_experiments_source_asset_id",
        "campaign_experiments",
        ["source_asset_id"],
    )
    op.create_index(
        "ix_campaign_experiments_platform",
        "campaign_experiments",
        ["platform"],
    )
    op.create_index(
        "ix_campaign_experiments_status",
        "campaign_experiments",
        ["status"],
    )

    # experiment_results
    op.create_table(
        "experiment_results",
        sa.Column("id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column(
            "experiment_id",
            postgresql.UUID(as_uuid=True),
            nullable=False,
        ),
        sa.Column(
            "impressions", sa.Integer(), nullable=False, server_default="0"
        ),
        sa.Column("reach", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("likes", sa.Integer(), nullable=False, server_default="0"),
        sa.Column(
            "comments_count",
            sa.Integer(),
            nullable=False,
            server_default="0",
        ),
        sa.Column("saves", sa.Integer(), nullable=False, server_default="0"),
        sa.Column(
            "shares", sa.Integer(), nullable=False, server_default="0"
        ),
        sa.Column(
            "engagement_rate",
            sa.Float(),
            nullable=False,
            server_default="0",
        ),
        sa.Column("leads", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("ctr", sa.Float(), nullable=False, server_default="0"),
        sa.Column("views", sa.Integer(), nullable=False, server_default="0"),
        sa.Column(
            "watch_time_seconds",
            sa.Float(),
            nullable=False,
            server_default="0",
        ),
        sa.Column(
            "raw_json",
            postgresql.JSONB(astext_type=sa.Text()),
            nullable=False,
            server_default=sa.text("'{}'::jsonb"),
        ),
        sa.Column(
            "captured_at", sa.DateTime(timezone=True), nullable=False
        ),
        sa.Column(
            "sample_size",
            sa.Integer(),
            nullable=False,
            server_default="0",
        ),
        sa.Column(
            "confidence_score",
            sa.Numeric(precision=3, scale=2),
            nullable=False,
            server_default="0.5",
        ),
        sa.Column(
            "evidence",
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
            ["experiment_id"],
            ["campaign_experiments.id"],
            ondelete="CASCADE",
        ),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(
        "ix_experiment_results_experiment_id",
        "experiment_results",
        ["experiment_id"],
    )
    op.create_index(
        "ix_experiment_results_captured_at",
        "experiment_results",
        ["captured_at"],
    )

    # learning_events
    op.create_table(
        "learning_events",
        sa.Column("id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("user_id", sa.String(length=255), nullable=False),
        sa.Column("variable", sa.String(length=64), nullable=False),
        sa.Column("finding", sa.Text(), nullable=False),
        sa.Column(
            "direction",
            sa.String(length=16),
            nullable=False,
            server_default="positive",
        ),
        sa.Column("effect_size", sa.Float(), nullable=True),
        sa.Column(
            "experiment_ids",
            postgresql.JSONB(astext_type=sa.Text()),
            nullable=False,
            server_default=sa.text("'[]'::jsonb"),
        ),
        sa.Column(
            "evidence",
            postgresql.JSONB(astext_type=sa.Text()),
            nullable=False,
            server_default=sa.text("'[]'::jsonb"),
        ),
        sa.Column(
            "sample_size",
            sa.Integer(),
            nullable=False,
            server_default="0",
        ),
        sa.Column(
            "confidence_score",
            sa.Numeric(precision=3, scale=2),
            nullable=False,
            server_default="0.5",
        ),
        sa.Column(
            "source",
            sa.String(length=16),
            nullable=False,
            server_default="auto",
        ),
        sa.Column(
            "status",
            sa.String(length=16),
            nullable=False,
            server_default="active",
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
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(
        "ix_learning_events_user_id", "learning_events", ["user_id"]
    )
    op.create_index(
        "ix_learning_events_variable", "learning_events", ["variable"]
    )
    op.create_index(
        "ix_learning_events_status", "learning_events", ["status"]
    )


def downgrade() -> None:
    op.drop_index(
        "ix_learning_events_status", table_name="learning_events"
    )
    op.drop_index(
        "ix_learning_events_variable", table_name="learning_events"
    )
    op.drop_index(
        "ix_learning_events_user_id", table_name="learning_events"
    )
    op.drop_table("learning_events")

    op.drop_index(
        "ix_experiment_results_captured_at",
        table_name="experiment_results",
    )
    op.drop_index(
        "ix_experiment_results_experiment_id",
        table_name="experiment_results",
    )
    op.drop_table("experiment_results")

    op.drop_index(
        "ix_campaign_experiments_status",
        table_name="campaign_experiments",
    )
    op.drop_index(
        "ix_campaign_experiments_platform",
        table_name="campaign_experiments",
    )
    op.drop_index(
        "ix_campaign_experiments_source_asset_id",
        table_name="campaign_experiments",
    )
    op.drop_index(
        "ix_campaign_experiments_source_asset_type",
        table_name="campaign_experiments",
    )
    op.drop_index(
        "ix_campaign_experiments_user_id",
        table_name="campaign_experiments",
    )
    op.drop_table("campaign_experiments")
