"""Connector metrics for organic platform data

Revision ID: 0040_connector_metrics
Revises: 0039_advisor_outcomes
Create Date: 2026-06-19
"""

from __future__ import annotations

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "0040_connector_metrics"
down_revision: Union[str, None] = "0039_advisor_outcomes"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "connector_sync_runs",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column(
            "brand_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("brands.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column(
            "connection_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("integration_connection.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("provider_slug", sa.String(length=32), nullable=False),
        sa.Column("status", sa.String(length=16), nullable=False),
        sa.Column("rows_pulled", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("error_message", sa.Text(), nullable=True),
        sa.Column("started_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("finished_at", sa.DateTime(timezone=True), nullable=True),
    )
    op.create_index(
        "ix_connector_sync_runs_brand_provider",
        "connector_sync_runs",
        ["brand_id", "provider_slug", "started_at"],
    )

    op.create_table(
        "connector_metrics",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column(
            "brand_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("brands.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("provider_slug", sa.String(length=32), nullable=False),
        sa.Column("metric_key", sa.String(length=64), nullable=False),
        sa.Column("metric_value", sa.Numeric(18, 4), nullable=False),
        sa.Column("period_start", sa.DateTime(timezone=True), nullable=True),
        sa.Column("period_end", sa.DateTime(timezone=True), nullable=True),
        sa.Column(
            "raw_json",
            postgresql.JSONB(astext_type=sa.Text()),
            nullable=False,
            server_default=sa.text("'{}'::jsonb"),
        ),
        sa.Column("synced_at", sa.DateTime(timezone=True), nullable=False),
        sa.UniqueConstraint(
            "brand_id",
            "provider_slug",
            "metric_key",
            "period_end",
            name="uq_connector_metrics_brand_provider_key_period",
        ),
    )
    op.create_index(
        "ix_connector_metrics_brand_provider",
        "connector_metrics",
        ["brand_id", "provider_slug"],
    )


def downgrade() -> None:
    op.drop_index("ix_connector_metrics_brand_provider", table_name="connector_metrics")
    op.drop_table("connector_metrics")
    op.drop_index(
        "ix_connector_sync_runs_brand_provider", table_name="connector_sync_runs"
    )
    op.drop_table("connector_sync_runs")
