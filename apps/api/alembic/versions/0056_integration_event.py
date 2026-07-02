"""Phase 6.1 — integration_event (activity log / sync history / error center).

Additive append-only table logging OAuth/sync/disconnect/error events per
connection. No impact on existing integration_connection / integration_credential
data. Contains no secrets.

Revision ID: 0056_integration_event
Revises: 0055_operations_notifications
Create Date: 2026-07-03
"""

from __future__ import annotations

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "0056_integration_event"
down_revision: Union[str, None] = "0055_operations_notifications"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "integration_event",
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
            nullable=True,
        ),
        sa.Column(
            "connection_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("integration_connection.id", ondelete="SET NULL"),
            nullable=True,
        ),
        sa.Column("provider_slug", sa.String(length=32), nullable=False),
        sa.Column("event_type", sa.String(length=32), nullable=False),
        sa.Column("status", sa.String(length=16), server_default="info", nullable=False),
        sa.Column("message", sa.Text(), nullable=True),
        sa.Column(
            "detail",
            postgresql.JSONB(astext_type=sa.Text()),
            server_default="{}",
            nullable=False,
        ),
        sa.Column("duration_ms", sa.Integer(), nullable=True),
        sa.Column(
            "occurred_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
    )
    op.create_index("ix_integration_event_organization_id", "integration_event", ["organization_id"])
    op.create_index("ix_integration_event_brand_id", "integration_event", ["brand_id"])
    op.create_index("ix_integration_event_connection_id", "integration_event", ["connection_id"])
    op.create_index("ix_integration_event_provider_slug", "integration_event", ["provider_slug"])
    op.create_index("ix_integration_event_event_type", "integration_event", ["event_type"])
    op.create_index("ix_integration_event_status", "integration_event", ["status"])
    op.create_index("ix_integration_event_occurred_at", "integration_event", ["occurred_at"])
    # "recent events for this org" — the activity-feed hot path.
    op.create_index(
        "ix_integration_event_org_occurred", "integration_event", ["organization_id", "occurred_at"]
    )


def downgrade() -> None:
    op.drop_index("ix_integration_event_org_occurred", "integration_event")
    op.drop_index("ix_integration_event_occurred_at", "integration_event")
    op.drop_index("ix_integration_event_status", "integration_event")
    op.drop_index("ix_integration_event_event_type", "integration_event")
    op.drop_index("ix_integration_event_provider_slug", "integration_event")
    op.drop_index("ix_integration_event_connection_id", "integration_event")
    op.drop_index("ix_integration_event_brand_id", "integration_event")
    op.drop_index("ix_integration_event_organization_id", "integration_event")
    op.drop_table("integration_event")
