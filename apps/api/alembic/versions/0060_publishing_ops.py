"""Phase 6.4 — enterprise publishing queue lifecycle.

Additive columns on scheduled_posts: exponential-backoff retry gate
(next_attempt_at), the approval gate (approval_status / approval_required /
reviewed_by_user_id / approval_reason), and schedule_timezone. No rewrite, no
backfill — every existing row defaults to the pre-6.4 behaviour
(approval_status="not_required", approval_required=false).

Revision ID: 0060_publishing_ops
Revises: 0059_creative_brief
Create Date: 2026-07-03
"""

from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op

revision: str = "0060_publishing_ops"
down_revision: str | None = "0059_creative_brief"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column(
        "scheduled_posts",
        sa.Column("next_attempt_at", sa.DateTime(timezone=True), nullable=True),
    )
    op.add_column(
        "scheduled_posts",
        sa.Column(
            "approval_status", sa.String(20),
            server_default="not_required", nullable=False,
        ),
    )
    op.add_column(
        "scheduled_posts",
        sa.Column(
            "approval_required", sa.Boolean(), server_default="false", nullable=False
        ),
    )
    op.add_column(
        "scheduled_posts",
        sa.Column("reviewed_by_user_id", sa.String(255), nullable=True),
    )
    op.add_column(
        "scheduled_posts",
        sa.Column("approval_reason", sa.Text(), nullable=True),
    )
    op.add_column(
        "scheduled_posts",
        sa.Column("schedule_timezone", sa.String(48), nullable=True),
    )
    op.create_index(
        "ix_scheduled_posts_next_attempt_at", "scheduled_posts", ["next_attempt_at"]
    )
    op.create_index(
        "ix_scheduled_posts_approval_status", "scheduled_posts", ["approval_status"]
    )


def downgrade() -> None:
    op.drop_index("ix_scheduled_posts_approval_status", table_name="scheduled_posts")
    op.drop_index("ix_scheduled_posts_next_attempt_at", table_name="scheduled_posts")
    op.drop_column("scheduled_posts", "schedule_timezone")
    op.drop_column("scheduled_posts", "approval_reason")
    op.drop_column("scheduled_posts", "reviewed_by_user_id")
    op.drop_column("scheduled_posts", "approval_required")
    op.drop_column("scheduled_posts", "approval_status")
    op.drop_column("scheduled_posts", "next_attempt_at")
