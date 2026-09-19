"""First-party authentication: user credentials + sessions + email tokens.

Adds the columns and tables that let DM Tool be the system of record for
authentication (replacing Clerk):

  * users.password_hash / email_verified_at / password_changed_at
  * users.clerk_user_id → NULLABLE (retained for history; no longer required)
  * user_sessions  — server-side sessions, stored as token *hashes*
  * email_tokens   — single-use, hashed, expiring verify/reset tokens
  * login_attempts — brute-force / credential-stuffing throttle ledger

Purely additive to existing data: no column is dropped and clerk_user_id is
only relaxed to nullable, so the migration is safe and reversible.

Revision ID: 0072_first_party_auth
Revises: 0071_social_asset_provenance
Create Date: 2026-09-14
"""

from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op

revision: str = "0072_first_party_auth"
down_revision: str | None = "0071_social_asset_provenance"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    # --- users: first-party credential columns ---
    op.add_column("users", sa.Column("password_hash", sa.Text(), nullable=True))
    op.add_column(
        "users",
        sa.Column("email_verified_at", sa.DateTime(timezone=True), nullable=True),
    )
    op.add_column(
        "users",
        sa.Column("password_changed_at", sa.DateTime(timezone=True), nullable=True),
    )
    # Clerk id is no longer the auth key — relax to nullable, keep the unique
    # index so any surviving values stay unique.
    op.alter_column(
        "users",
        "clerk_user_id",
        existing_type=sa.Text(),
        nullable=True,
    )

    # --- user_sessions ---
    op.create_table(
        "user_sessions",
        sa.Column("id", sa.dialects.postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column(
            "user_id",
            sa.dialects.postgresql.UUID(as_uuid=True),
            sa.ForeignKey("users.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("token_hash", sa.Text(), nullable=False),
        sa.Column("expires_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("last_used_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("revoked_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("ip", sa.Text(), nullable=True),
        sa.Column("user_agent", sa.Text(), nullable=True),
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
    op.create_index("ix_user_sessions_user_id", "user_sessions", ["user_id"])
    op.create_unique_constraint("uq_user_sessions_token_hash", "user_sessions", ["token_hash"])

    # --- email_tokens ---
    op.create_table(
        "email_tokens",
        sa.Column("id", sa.dialects.postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column(
            "user_id",
            sa.dialects.postgresql.UUID(as_uuid=True),
            sa.ForeignKey("users.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("purpose", sa.String(16), nullable=False),
        sa.Column("token_hash", sa.Text(), nullable=False),
        sa.Column("expires_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("used_at", sa.DateTime(timezone=True), nullable=True),
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
        sa.CheckConstraint("purpose IN ('verify', 'reset')", name="ck_email_tokens_purpose"),
    )
    op.create_index("ix_email_tokens_user_id", "email_tokens", ["user_id"])
    op.create_index("ix_email_tokens_user_purpose", "email_tokens", ["user_id", "purpose"])
    op.create_unique_constraint("uq_email_tokens_token_hash", "email_tokens", ["token_hash"])

    # --- login_attempts ---
    op.create_table(
        "login_attempts",
        sa.Column("id", sa.dialects.postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("email", sa.Text(), nullable=True),
        sa.Column("ip", sa.Text(), nullable=True),
        sa.Column("successful", sa.Boolean(), nullable=False, server_default=sa.false()),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.func.now(),
            nullable=False,
        ),
    )
    op.create_index("ix_login_attempts_created_at", "login_attempts", ["created_at"])
    op.create_index("ix_login_attempts_email_time", "login_attempts", ["email", "created_at"])
    op.create_index("ix_login_attempts_ip_time", "login_attempts", ["ip", "created_at"])


def downgrade() -> None:
    op.drop_table("login_attempts")
    op.drop_table("email_tokens")
    op.drop_table("user_sessions")
    op.alter_column(
        "users",
        "clerk_user_id",
        existing_type=sa.Text(),
        nullable=False,
    )
    op.drop_column("users", "password_changed_at")
    op.drop_column("users", "email_verified_at")
    op.drop_column("users", "password_hash")
