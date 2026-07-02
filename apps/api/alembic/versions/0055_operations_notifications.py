"""Phase 4.8 — operations_notifications (Notification Center feed).

Additive table: the in-app notification feed raised by the operations loop,
categorised with the existing notifications-catalog taxonomy. No impact on
existing data or the notification-preferences table.

Revision ID: 0055_operations_notifications
Revises: 0054_scheduled_work
Create Date: 2026-07-02
"""

from __future__ import annotations

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "0055_operations_notifications"
down_revision: Union[str, None] = "0054_scheduled_work"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "operations_notifications",
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
        sa.Column("category", sa.String(length=32), nullable=False),
        sa.Column("kind", sa.String(length=24), nullable=False),
        sa.Column("severity", sa.String(length=16), server_default="info", nullable=False),
        sa.Column("title", sa.Text(), nullable=False),
        sa.Column("body", sa.Text(), nullable=False),
        sa.Column("link", sa.String(length=200), nullable=True),
        sa.Column("source_id", postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column("dedupe_key", sa.String(length=180), nullable=False),
        sa.Column("read", sa.Boolean(), server_default="false", nullable=False),
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
    op.create_index("ix_operations_notifications_organization_id", "operations_notifications", ["organization_id"])
    op.create_index("ix_operations_notifications_brand_id", "operations_notifications", ["brand_id"])
    op.create_index("ix_operations_notifications_category", "operations_notifications", ["category"])
    op.create_index("ix_operations_notifications_kind", "operations_notifications", ["kind"])
    op.create_index("ix_operations_notifications_dedupe_key", "operations_notifications", ["dedupe_key"])
    op.create_index("ix_operations_notifications_read", "operations_notifications", ["read"])
    op.create_index(
        "ix_operations_notifications_brand_read", "operations_notifications", ["brand_id", "read"]
    )


def downgrade() -> None:
    op.drop_index("ix_operations_notifications_brand_read", "operations_notifications")
    op.drop_index("ix_operations_notifications_read", "operations_notifications")
    op.drop_index("ix_operations_notifications_dedupe_key", "operations_notifications")
    op.drop_index("ix_operations_notifications_kind", "operations_notifications")
    op.drop_index("ix_operations_notifications_category", "operations_notifications")
    op.drop_index("ix_operations_notifications_brand_id", "operations_notifications")
    op.drop_index("ix_operations_notifications_organization_id", "operations_notifications")
    op.drop_table("operations_notifications")
