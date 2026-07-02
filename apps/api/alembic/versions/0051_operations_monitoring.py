"""Phase 4.1 — metric_snapshots + operations_runs (Continuous Monitoring Engine).

Two additive tables (no impact on existing data):
- metric_snapshots  — per-brand time series of real metrics (tenant-scoped).
- operations_runs   — one row per continuous-loop cycle (system-wide audit +
                      idempotency anchor).

Revision ID: 0051_operations_monitoring
Revises: 0050_autonomy_level
Create Date: 2026-07-02
"""

from __future__ import annotations

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "0051_operations_monitoring"
down_revision: Union[str, None] = "0050_autonomy_level"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "metric_snapshots",
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
        sa.Column("captured_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column(
            "metrics",
            postgresql.JSONB(astext_type=sa.Text()),
            server_default="{}",
            nullable=False,
        ),
        sa.Column(
            "sources_ok",
            postgresql.JSONB(astext_type=sa.Text()),
            server_default="[]",
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
    op.create_index(
        "ix_metric_snapshots_organization_id", "metric_snapshots", ["organization_id"]
    )
    op.create_index("ix_metric_snapshots_brand_id", "metric_snapshots", ["brand_id"])
    op.create_index(
        "ix_metric_snapshots_captured_at", "metric_snapshots", ["captured_at"]
    )
    # "latest snapshot for this brand" — the hot read path (monitoring + events).
    op.create_index(
        "ix_metric_snapshots_brand_captured",
        "metric_snapshots",
        ["brand_id", "captured_at"],
    )

    op.create_table(
        "operations_runs",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("started_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("finished_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("trigger", sa.String(length=16), server_default="api", nullable=False),
        sa.Column(
            "status", sa.String(length=16), server_default="completed", nullable=False
        ),
        sa.Column("brands_scanned", sa.Integer(), server_default="0", nullable=False),
        sa.Column(
            "snapshots_captured", sa.Integer(), server_default="0", nullable=False
        ),
        sa.Column("events_detected", sa.Integer(), server_default="0", nullable=False),
        sa.Column(
            "detail",
            postgresql.JSONB(astext_type=sa.Text()),
            server_default="{}",
            nullable=False,
        ),
        sa.Column("error", sa.Text(), nullable=True),
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
        "ix_operations_runs_started_at", "operations_runs", ["started_at"]
    )


def downgrade() -> None:
    op.drop_index("ix_operations_runs_started_at", "operations_runs")
    op.drop_table("operations_runs")
    op.drop_index("ix_metric_snapshots_brand_captured", "metric_snapshots")
    op.drop_index("ix_metric_snapshots_captured_at", "metric_snapshots")
    op.drop_index("ix_metric_snapshots_brand_id", "metric_snapshots")
    op.drop_index("ix_metric_snapshots_organization_id", "metric_snapshots")
    op.drop_table("metric_snapshots")
