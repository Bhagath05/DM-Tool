"""saas foundation

Revision ID: 0013_saas_foundation
Revises: 0012_learning_lab
Create Date: 2026-05-30

Phase 1 — SaaS foundation. Three tables that establish identity and tenant
hierarchy:

- users               → mirror of Clerk identity, our canonical user row
- organizations       → top-level tenant; owns billing + team
- brands              → second-level tenant; owns business data

Every business object created from this point on is scoped to
(organization_id, brand_id). The columns are added to existing business
tables in migration 0015 (additive, nullable), then backfilled in 0016,
then made NOT NULL in 0017.

This migration is purely additive — no existing table is touched. Safe
to apply on production with zero customer impact.
"""

from __future__ import annotations

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "0013_saas_foundation"
down_revision: Union[str, None] = "0012_learning_lab"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # CITEXT is the right type for email (case-insensitive equality), and
    # it's standard in modern Postgres. We enable the extension here so
    # migrations are self-contained — no manual DB prep required before
    # first deploy.
    op.execute("CREATE EXTENSION IF NOT EXISTS citext")

    # ----- users -----------------------------------------------------------
    # Our mirror of Clerk identity. clerk_user_id is the join key against
    # the Clerk JWT 'sub' claim. We mirror email so we can drive
    # email-based features (invites, team listings) without round-tripping
    # to Clerk on every request.
    op.create_table(
        "users",
        sa.Column("id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("clerk_user_id", sa.Text(), nullable=False),
        sa.Column(
            "email",
            postgresql.CITEXT() if hasattr(postgresql, "CITEXT") else sa.Text(),
            nullable=False,
        ),
        sa.Column("display_name", sa.Text(), nullable=True),
        sa.Column("avatar_url", sa.Text(), nullable=True),
        sa.Column(
            "status",
            sa.String(length=16),
            nullable=False,
            server_default="active",
        ),
        sa.Column("last_seen_at", sa.DateTime(timezone=True), nullable=True),
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
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("clerk_user_id", name="uq_users_clerk_user_id"),
        sa.UniqueConstraint("email", name="uq_users_email"),
        sa.CheckConstraint(
            "status IN ('active', 'suspended', 'deleted')",
            name="ck_users_status",
        ),
    )
    op.create_index(
        "ix_users_status_active",
        "users",
        ["status"],
        postgresql_where=sa.text("status != 'deleted'"),
    )

    # ----- organizations ---------------------------------------------------
    # Top-level tenant. Owns billing, team, and (transitively) all brands.
    # member_count + brand_count are denormalised for fast UI without a
    # COUNT(*) on every dashboard render. Kept in sync by services.
    op.create_table(
        "organizations",
        sa.Column("id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("slug", sa.Text(), nullable=False),
        sa.Column("name", sa.Text(), nullable=False),
        sa.Column(
            "owner_user_id", postgresql.UUID(as_uuid=True), nullable=False
        ),
        sa.Column(
            "status",
            sa.String(length=16),
            nullable=False,
            server_default="active",
        ),
        sa.Column(
            "member_count", sa.Integer(), nullable=False, server_default="1"
        ),
        sa.Column(
            "brand_count", sa.Integer(), nullable=False, server_default="0"
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
        sa.ForeignKeyConstraint(
            ["owner_user_id"], ["users.id"], name="fk_organizations_owner"
        ),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("slug", name="uq_organizations_slug"),
        sa.CheckConstraint(
            "status IN ('active', 'archived', 'deleted')",
            name="ck_organizations_status",
        ),
    )
    op.create_index(
        "ix_organizations_owner_active",
        "organizations",
        ["owner_user_id"],
        postgresql_where=sa.text("status != 'deleted'"),
    )

    # ----- brands ----------------------------------------------------------
    # Second-level tenant — owns all business data. A brand belongs to
    # exactly one org. Slug is unique per org (not globally), since two
    # different orgs may both have a brand called "main".
    op.create_table(
        "brands",
        sa.Column("id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column(
            "organization_id", postgresql.UUID(as_uuid=True), nullable=False
        ),
        sa.Column("slug", sa.Text(), nullable=False),
        sa.Column("name", sa.Text(), nullable=False),
        sa.Column("description", sa.Text(), nullable=True),
        sa.Column(
            "status",
            sa.String(length=16),
            nullable=False,
            server_default="active",
        ),
        sa.Column(
            "created_by_user_id",
            postgresql.UUID(as_uuid=True),
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
        sa.ForeignKeyConstraint(
            ["organization_id"],
            ["organizations.id"],
            ondelete="CASCADE",
            name="fk_brands_org",
        ),
        sa.ForeignKeyConstraint(
            ["created_by_user_id"],
            ["users.id"],
            name="fk_brands_created_by",
        ),
        sa.PrimaryKeyConstraint("id"),
        sa.CheckConstraint(
            "status IN ('active', 'archived', 'deleted')",
            name="ck_brands_status",
        ),
    )
    # Slug uniqueness is per-org and only among non-deleted brands —
    # archived/deleted brands shouldn't block re-use of their slug.
    op.create_index(
        "uq_brands_org_slug_active",
        "brands",
        ["organization_id", "slug"],
        unique=True,
        postgresql_where=sa.text("status != 'deleted'"),
    )
    op.create_index(
        "ix_brands_org_status", "brands", ["organization_id", "status"]
    )


def downgrade() -> None:
    op.drop_index("ix_brands_org_status", table_name="brands")
    op.drop_index("uq_brands_org_slug_active", table_name="brands")
    op.drop_table("brands")

    op.drop_index("ix_organizations_owner_active", table_name="organizations")
    op.drop_table("organizations")

    op.drop_index("ix_users_status_active", table_name="users")
    op.drop_table("users")

    # citext extension is left in place — dropping it could affect other
    # tables in the DB that use it. Safe to leave; cheap to keep.
