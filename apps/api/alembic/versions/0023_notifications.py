"""notification preferences — phase 10.2b

Revision ID: 0023_notifications
Revises: 0022_integrations
Create Date: 2026-06-05

Phase 10.2b — Per-user, per-org notification preference matrix.

Design notes:

- Sparse storage. A user with all-defaults stores ZERO rows. Each row
  is an explicit divergence from the code-defined defaults (see
  `aicmo/modules/notifications/catalog.py`). This means adding a new
  category or channel later requires NO backfill — the defaults just
  flow through on read.

- Composite PK on (user_id, organization_id, category, channel). One
  row = one toggle. Idempotent upserts via ON CONFLICT.

- CHECK constraints on category + channel keep the DB honest about the
  enum range — Pydantic Literals are belt-and-braces, not the only line.

- Per-org keying: a consultant who's a member of three workspaces gets
  three independent matrices. Billing alerts for their startup don't
  spam them with billing alerts for client orgs.

- No `enabled DEFAULT TRUE`. Defaults live in code (channel-aware:
  email defaults on for everything, slack/sms default off). Storing
  defaults in the DB would mean two sources of truth.

Rollback drops the table. No data lost beyond explicit overrides —
the matrix re-materialises from defaults on first read.
"""

from __future__ import annotations

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql


revision: str = "0023_notifications"
down_revision: Union[str, None] = "0022_integrations"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


# Kept in lock-step with aicmo/modules/notifications/catalog.py.
# Adding/removing values here REQUIRES a follow-up migration; we don't
# auto-evolve enums based on code constants.
_CATEGORIES = (
    "weekly_digest",
    "winner_alert",
    "campaign_alert",
    "billing_alert",
    "security_alert",
    "system_alert",
)

_CHANNELS = ("email", "slack", "sms")

# `source` tells us where a row came from. Today every row is
# 'user' (founder flipped a switch). Future: 'admin' (org-wide policy
# override), 'system' (compliance default). Keeping the column now means
# Phase 10.2d/10.2e can write rows without a migration.
_SOURCES = ("user", "admin", "system")


def upgrade() -> None:
    op.create_table(
        "notification_preference",
        sa.Column(
            "user_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("users.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column(
            "organization_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("organizations.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("category", sa.String(32), nullable=False),
        sa.Column("channel", sa.String(16), nullable=False),
        sa.Column("enabled", sa.Boolean(), nullable=False),
        sa.Column(
            "source",
            sa.String(16),
            nullable=False,
            server_default="user",
            comment="Who wrote this row — user/admin/system. Phase 10.2b only writes 'user'.",
        ),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.func.now(),
            nullable=False,
        ),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            server_default=sa.func.now(),
            nullable=False,
        ),
        sa.PrimaryKeyConstraint(
            "user_id",
            "organization_id",
            "category",
            "channel",
            name="pk_notification_preference",
        ),
    )

    # CHECK constraints — DB-side enum policing.
    quoted_cats = ", ".join(f"'{c}'" for c in _CATEGORIES)
    op.execute(
        "ALTER TABLE notification_preference "
        "ADD CONSTRAINT ck_notification_preference_category "
        f"CHECK (category IN ({quoted_cats}))"
    )
    quoted_chs = ", ".join(f"'{c}'" for c in _CHANNELS)
    op.execute(
        "ALTER TABLE notification_preference "
        "ADD CONSTRAINT ck_notification_preference_channel "
        f"CHECK (channel IN ({quoted_chs}))"
    )
    quoted_srcs = ", ".join(f"'{s}'" for s in _SOURCES)
    op.execute(
        "ALTER TABLE notification_preference "
        "ADD CONSTRAINT ck_notification_preference_source "
        f"CHECK (source IN ({quoted_srcs}))"
    )

    # Hot path: "load this user's prefs for this org" — the PK already
    # serves that. Add an index for the inverse: "which users have
    # category X on channel Y enabled?" — needed when the dispatcher
    # ships (Phase 12+). Cheap to add now; expensive to add later under
    # a large table.
    op.create_index(
        "ix_notification_preference_dispatch",
        "notification_preference",
        ["category", "channel", "enabled"],
    )


def downgrade() -> None:
    op.drop_index(
        "ix_notification_preference_dispatch",
        table_name="notification_preference",
    )
    # CHECK constraints + PK drop with the table.
    op.drop_table("notification_preference")
