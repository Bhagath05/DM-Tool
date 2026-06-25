"""rbac foundation

Revision ID: 0014_rbac_foundation
Revises: 0013_saas_foundation
Create Date: 2026-05-30

Permission-based RBAC. Five tables plus seed data:

- roles                  → 4 system roles seeded; future custom roles per org
- permissions            → 16 permission slugs covering all S1 surface area
- role_permissions       → role↔permission map
- organization_members   → user's membership in an org (one row per active membership)
- member_roles           → member ↔ role assignment (N:N — a member can hold many roles)

Why N:N membership ↔ role: keeps the door open for stacked roles
('Editor' + 'Publisher' on the same member) without a schema rewrite.
For S1 each member holds exactly one role, but the architecture costs
nothing extra to support more.

System roles are seeded with organization_id IS NULL. They are shared
across all orgs — no per-org copies, no row explosion. Custom roles
(future Tier 4) will be created with organization_id set.
"""

from __future__ import annotations

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "0014_rbac_foundation"
down_revision: Union[str, None] = "0013_saas_foundation"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


# ---------------------------------------------------------------------
#  Seed data
# ---------------------------------------------------------------------

# 16 permission slugs that cover everything S1 needs to gate.
# Categories map roughly to UI surface areas + backend resource groups.
PERMISSIONS = [
    # Organization
    ("organization.manage", "Manage organization", "Edit name, delete org", "organization"),
    ("brand.manage", "Manage brands", "Create, edit, archive brands", "brand"),
    ("team.manage", "Manage team", "Invite, remove, change roles", "organization"),
    ("billing.manage", "Manage billing", "Plan, payment, subscription", "billing"),
    ("settings.manage", "Manage settings", "Org + brand settings", "organization"),
    # Campaigns
    ("campaign.create", "Create campaigns", "Create campaigns + bundles", "campaign"),
    ("campaign.edit", "Edit campaigns", "Edit any campaign in the brand", "campaign"),
    ("campaign.delete", "Delete campaigns", "Delete any campaign", "campaign"),
    # Content
    ("content.create", "Create content", "Generate ads, content, visuals", "content"),
    ("content.edit", "Edit content", "Edit generated content", "content"),
    ("content.delete", "Delete content", "Delete content", "content"),
    # Leads
    ("lead.view", "View leads", "View leads + landing-page submissions", "lead"),
    ("lead.export", "Export leads", "Export leads to CSV", "lead"),
    # Publishing
    ("publish.content", "Publish content", "Publish to connected platforms", "publish"),
    # Read-only surfaces
    ("analytics.view", "View analytics", "View analytics dashboards", "analytics"),
    ("library.view", "View library", "Browse asset library", "library"),
]

# 4 system roles. owner/admin/editor/viewer.
ROLES = [
    ("owner", "Owner", "Full access. Only the org creator initially."),
    ("admin", "Admin", "Manage team + brands + content. No billing."),
    ("editor", "Editor", "Create + edit content, publish, view analytics."),
    ("viewer", "Viewer", "Read-only — leads, analytics, library."),
]

# Role → permissions matrix. Mirrors CTO plan §3.8.
ROLE_PERMISSIONS: dict[str, list[str]] = {
    "owner": [p[0] for p in PERMISSIONS],  # all permissions
    "admin": [
        "brand.manage",
        "team.manage",
        "settings.manage",
        "campaign.create",
        "campaign.edit",
        "campaign.delete",
        "content.create",
        "content.edit",
        "content.delete",
        "lead.view",
        "lead.export",
        "publish.content",
        "analytics.view",
        "library.view",
    ],
    "editor": [
        "campaign.create",
        "campaign.edit",
        "content.create",
        "content.edit",
        "lead.view",
        "publish.content",
        "analytics.view",
        "library.view",
    ],
    "viewer": [
        "lead.view",
        "analytics.view",
        "library.view",
    ],
}


def upgrade() -> None:
    # ----- roles -----------------------------------------------------------
    op.create_table(
        "roles",
        sa.Column("id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column(
            "organization_id",
            postgresql.UUID(as_uuid=True),
            nullable=True,
            comment="NULL = system role, available to all orgs",
        ),
        sa.Column("slug", sa.String(length=64), nullable=False),
        sa.Column("name", sa.Text(), nullable=False),
        sa.Column("description", sa.Text(), nullable=True),
        sa.Column(
            "is_system", sa.Boolean(), nullable=False, server_default=sa.text("false")
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
            name="fk_roles_org",
        ),
        sa.PrimaryKeyConstraint("id"),
    )
    # System roles: slug is globally unique among org_id IS NULL rows.
    op.create_index(
        "uq_roles_system_slug",
        "roles",
        ["slug"],
        unique=True,
        postgresql_where=sa.text("organization_id IS NULL"),
    )
    # Org-scoped custom roles: slug unique per org.
    op.create_index(
        "uq_roles_org_slug",
        "roles",
        ["organization_id", "slug"],
        unique=True,
        postgresql_where=sa.text("organization_id IS NOT NULL"),
    )

    # ----- permissions -----------------------------------------------------
    op.create_table(
        "permissions",
        sa.Column("id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("slug", sa.String(length=64), nullable=False),
        sa.Column("name", sa.Text(), nullable=False),
        sa.Column("description", sa.Text(), nullable=True),
        sa.Column("category", sa.String(length=32), nullable=False),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("slug", name="uq_permissions_slug"),
    )
    op.create_index("ix_permissions_category", "permissions", ["category"])

    # ----- role_permissions ------------------------------------------------
    op.create_table(
        "role_permissions",
        sa.Column("role_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column(
            "permission_id", postgresql.UUID(as_uuid=True), nullable=False
        ),
        sa.ForeignKeyConstraint(
            ["role_id"], ["roles.id"], ondelete="CASCADE"
        ),
        sa.ForeignKeyConstraint(
            ["permission_id"], ["permissions.id"], ondelete="CASCADE"
        ),
        sa.PrimaryKeyConstraint("role_id", "permission_id"),
    )
    op.create_index(
        "ix_role_permissions_permission_id",
        "role_permissions",
        ["permission_id"],
    )

    # ----- organization_members --------------------------------------------
    # last_active_brand_id is sticky brand selection — when a user logs in,
    # we restore the brand they were last working on in this org.
    op.create_table(
        "organization_members",
        sa.Column("id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column(
            "organization_id", postgresql.UUID(as_uuid=True), nullable=False
        ),
        sa.Column("user_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column(
            "invited_by_user_id",
            postgresql.UUID(as_uuid=True),
            nullable=True,
        ),
        sa.Column(
            "last_active_brand_id",
            postgresql.UUID(as_uuid=True),
            nullable=True,
        ),
        sa.Column(
            "joined_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.Column(
            "status",
            sa.String(length=16),
            nullable=False,
            server_default="active",
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
        ),
        sa.ForeignKeyConstraint(
            ["user_id"], ["users.id"], ondelete="CASCADE"
        ),
        sa.ForeignKeyConstraint(
            ["invited_by_user_id"], ["users.id"], ondelete="SET NULL"
        ),
        sa.ForeignKeyConstraint(
            ["last_active_brand_id"], ["brands.id"], ondelete="SET NULL"
        ),
        sa.PrimaryKeyConstraint("id"),
        sa.CheckConstraint(
            "status IN ('active', 'suspended', 'removed')",
            name="ck_org_members_status",
        ),
    )
    # A user can only have one active membership per org.
    op.create_index(
        "uq_org_members_org_user_active",
        "organization_members",
        ["organization_id", "user_id"],
        unique=True,
        postgresql_where=sa.text("status = 'active'"),
    )
    op.create_index(
        "ix_org_members_user_status",
        "organization_members",
        ["user_id", "status"],
    )

    # ----- member_roles ----------------------------------------------------
    op.create_table(
        "member_roles",
        sa.Column("id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("member_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("role_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column(
            "assigned_by_user_id",
            postgresql.UUID(as_uuid=True),
            nullable=True,
        ),
        sa.Column(
            "assigned_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.ForeignKeyConstraint(
            ["member_id"],
            ["organization_members.id"],
            ondelete="CASCADE",
        ),
        sa.ForeignKeyConstraint(
            ["role_id"], ["roles.id"], ondelete="CASCADE"
        ),
        sa.ForeignKeyConstraint(
            ["assigned_by_user_id"], ["users.id"], ondelete="SET NULL"
        ),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint(
            "member_id", "role_id", name="uq_member_roles_member_role"
        ),
    )
    op.create_index("ix_member_roles_role_id", "member_roles", ["role_id"])

    # -----------------------------------------------------------------------
    #  Seed: 16 permissions + 4 system roles + role↔permission mapping
    # -----------------------------------------------------------------------
    _seed_rbac()


def _seed_rbac() -> None:
    """Idempotent seed. Re-runnable on schema repair."""
    bind = op.get_bind()

    # Insert permissions
    for slug, name, description, category in PERMISSIONS:
        bind.execute(
            sa.text(
                """
                INSERT INTO permissions (id, slug, name, description, category)
                VALUES (gen_random_uuid(), :slug, :name, :description, :category)
                ON CONFLICT (slug) DO NOTHING
                """
            ),
            {
                "slug": slug,
                "name": name,
                "description": description,
                "category": category,
            },
        )

    # Insert system roles (organization_id NULL, is_system TRUE)
    for slug, name, description in ROLES:
        bind.execute(
            sa.text(
                """
                INSERT INTO roles (id, organization_id, slug, name, description, is_system)
                VALUES (gen_random_uuid(), NULL, :slug, :name, :description, true)
                ON CONFLICT DO NOTHING
                """
            ),
            {"slug": slug, "name": name, "description": description},
        )

    # Map role↔permissions. We re-fetch IDs each time for portability —
    # gen_random_uuid above means we can't rely on hardcoded IDs.
    for role_slug, perm_slugs in ROLE_PERMISSIONS.items():
        for perm_slug in perm_slugs:
            bind.execute(
                sa.text(
                    """
                    INSERT INTO role_permissions (role_id, permission_id)
                    SELECT r.id, p.id
                    FROM roles r, permissions p
                    WHERE r.slug = :role_slug
                      AND r.organization_id IS NULL
                      AND r.is_system = true
                      AND p.slug = :perm_slug
                    ON CONFLICT DO NOTHING
                    """
                ),
                {"role_slug": role_slug, "perm_slug": perm_slug},
            )


def downgrade() -> None:
    op.drop_index("ix_member_roles_role_id", table_name="member_roles")
    op.drop_table("member_roles")

    op.drop_index(
        "ix_org_members_user_status", table_name="organization_members"
    )
    op.drop_index(
        "uq_org_members_org_user_active", table_name="organization_members"
    )
    op.drop_table("organization_members")

    op.drop_index(
        "ix_role_permissions_permission_id", table_name="role_permissions"
    )
    op.drop_table("role_permissions")

    op.drop_index("ix_permissions_category", table_name="permissions")
    op.drop_table("permissions")

    op.drop_index("uq_roles_org_slug", table_name="roles")
    op.drop_index("uq_roles_system_slug", table_name="roles")
    op.drop_table("roles")
