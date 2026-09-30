"""Auth email suppression: permanently-undeliverable destination addresses.

Adds `email_suppressions` — a first-party record of auth email destinations that
are permanently undeliverable (a terminal recipient rejection). The auth
delivery path checks it (by the user's current normalized email) before sending
and skips a suppressed address. Keyed by the normalized email so an old
suppressed address never blocks a new one after an email change; `user_id` is a
best-effort reference (SET NULL on user delete) so a future MTA bounce/DSN
pipeline can reuse the table for an address without a known user.

Purely additive: one new table, no existing column changed. Holds no token,
URL, or credential.

Revision ID: 0075_auth_email_suppression
Revises: 0074_bb_research_intelligence
Create Date: 2026-09-30
"""

from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op

revision: str = "0075_auth_email_suppression"
down_revision: str | None = "0074_bb_research_intelligence"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "email_suppressions",
        sa.Column("id", sa.dialects.postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column(
            "user_id",
            sa.dialects.postgresql.UUID(as_uuid=True),
            sa.ForeignKey("users.id", ondelete="SET NULL"),
            nullable=True,
        ),
        sa.Column("email", sa.Text(), nullable=False),
        sa.Column("reason", sa.String(32), nullable=False),
        sa.Column("source", sa.String(48), nullable=False),
        sa.Column(
            "meta",
            sa.dialects.postgresql.JSONB(),
            server_default=sa.text("'{}'::jsonb"),
            nullable=False,
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
    )
    # Normalized email is the suppression identity + idempotency key.
    op.create_unique_constraint("uq_email_suppressions_email", "email_suppressions", ["email"])
    op.create_index("ix_email_suppressions_user_id", "email_suppressions", ["user_id"])


def downgrade() -> None:
    op.drop_index("ix_email_suppressions_user_id", table_name="email_suppressions")
    op.drop_constraint("uq_email_suppressions_email", "email_suppressions", type_="unique")
    op.drop_table("email_suppressions")
