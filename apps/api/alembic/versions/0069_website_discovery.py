"""Phase 8 — Intelligent Onboarding: website discovery runs.

Adds `website_discoveries` — one row per AI onboarding discovery (website or
from-scratch). Holds the extracted signals + the AI-proposed Brand Brain
draft the user reviews before it's applied to `business_profiles`.

Revision ID: 0069_website_discovery
Revises: 0068_brand_brain_identity
Create Date: 2026-07-15
"""

from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

from alembic import op

revision: str = "0069_website_discovery"
down_revision: str | None = "0068_brand_brain_identity"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "website_discoveries",
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
        sa.Column(
            "created_by_user_id", postgresql.UUID(as_uuid=True), nullable=False
        ),
        sa.Column("source", sa.String(16), nullable=False, server_default="website"),
        sa.Column("url", sa.String(500), nullable=True),
        sa.Column("business_name", sa.String(255), nullable=False, server_default=""),
        sa.Column("industry", sa.String(128), nullable=True),
        sa.Column("status", sa.String(16), nullable=False, server_default="pending"),
        sa.Column("stage", sa.String(24), nullable=False, server_default="queued"),
        sa.Column("signals", postgresql.JSONB(astext_type=sa.Text()), nullable=True),
        sa.Column("draft", postgresql.JSONB(astext_type=sa.Text()), nullable=True),
        sa.Column("seed", postgresql.JSONB(astext_type=sa.Text()), nullable=True),
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
        "ix_website_discoveries_brand_id", "website_discoveries", ["brand_id"]
    )


def downgrade() -> None:
    op.drop_index("ix_website_discoveries_brand_id", table_name="website_discoveries")
    op.drop_table("website_discoveries")
