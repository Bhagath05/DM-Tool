"""Phase 4.2 — detected_events (Event Detection Engine).

Additive table (no impact on existing data): meaningful changes the monitoring
loop detects by comparing consecutive metric snapshots. Structured input for the
Decision Engine.

Revision ID: 0052_detected_events
Revises: 0051_operations_monitoring
Create Date: 2026-07-02
"""

from __future__ import annotations

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "0052_detected_events"
down_revision: Union[str, None] = "0051_operations_monitoring"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "detected_events",
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
        sa.Column("detected_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("event_type", sa.String(length=48), nullable=False),
        sa.Column("severity", sa.String(length=16), server_default="medium", nullable=False),
        sa.Column("direction", sa.String(length=16), server_default="negative", nullable=False),
        sa.Column("metric", sa.String(length=48), nullable=False),
        sa.Column("previous_value", sa.Float(), nullable=True),
        sa.Column("current_value", sa.Float(), nullable=True),
        sa.Column("change_pct", sa.Float(), nullable=True),
        sa.Column("title", sa.Text(), nullable=False),
        sa.Column("summary", sa.Text(), nullable=False),
        sa.Column(
            "evidence",
            postgresql.JSONB(astext_type=sa.Text()),
            server_default="[]",
            nullable=False,
        ),
        sa.Column("dedupe_key", sa.String(length=128), nullable=False),
        sa.Column("status", sa.String(length=16), server_default="new", nullable=False),
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
    op.create_index("ix_detected_events_organization_id", "detected_events", ["organization_id"])
    op.create_index("ix_detected_events_brand_id", "detected_events", ["brand_id"])
    op.create_index("ix_detected_events_detected_at", "detected_events", ["detected_at"])
    op.create_index("ix_detected_events_event_type", "detected_events", ["event_type"])
    op.create_index("ix_detected_events_dedupe_key", "detected_events", ["dedupe_key"])
    op.create_index("ix_detected_events_status", "detected_events", ["status"])
    # "open events for this brand" — the hot read path (dashboard + pipeline).
    op.create_index(
        "ix_detected_events_brand_status", "detected_events", ["brand_id", "status"]
    )


def downgrade() -> None:
    op.drop_index("ix_detected_events_brand_status", "detected_events")
    op.drop_index("ix_detected_events_status", "detected_events")
    op.drop_index("ix_detected_events_dedupe_key", "detected_events")
    op.drop_index("ix_detected_events_event_type", "detected_events")
    op.drop_index("ix_detected_events_detected_at", "detected_events")
    op.drop_index("ix_detected_events_brand_id", "detected_events")
    op.drop_index("ix_detected_events_organization_id", "detected_events")
    op.drop_table("detected_events")
