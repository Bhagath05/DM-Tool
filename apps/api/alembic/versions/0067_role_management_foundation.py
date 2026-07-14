"""Phase 6.6 Slice 2 — Role Management foundation.

Additive + idempotent. (1) `role_permissions.effect` ('allow'|'deny') so the
permission engine supports ALLOW / DENY / INHERIT (INHERIT = no row). Existing
rows default to 'allow' → identical resolution as before. (2) `roles.priority`
(hierarchy) + `roles.color` (display). (3) Seven new system roles
(marketing_manager … analyst) alongside the existing admin/editor/viewer/owner,
with priority + color set on all. (4) Default permission grants per role, drawn
ONLY from the existing permission catalog (no fabricated slugs).

System roles are global (organization_id IS NULL) — every workspace shares them,
so there is nothing to duplicate per workspace.

Revision ID: 0067_role_management_foundation
Revises: 0066_admin_full_permissions
Create Date: 2026-07-06
"""

from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op

revision: str = "0067_role_management_foundation"
down_revision: str | None = "0066_admin_full_permissions"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

# (slug, name, description, priority, color) — higher priority manages lower.
# Owner (internal) sits above Admin; Admin is the displayed top role.
_ROLES = [
    ("owner", "Owner", "Workspace creator. Internal-only — displayed as Admin.", 110, "#6366f1"),
    ("admin", "Admin", "Full administrator. Manage everything in the workspace.", 100, "#6366f1"),
    ("marketing_manager", "Marketing Manager", "Owns campaigns, publishing, analytics, and tasks.", 80, "#8b5cf6"),
    ("performance_marketer", "Performance Marketer", "Runs ads and campaigns; reads analytics and audience.", 70, "#0ea5e9"),
    ("content_creator", "Content Creator", "Creates posts, content, and assets in the Studio.", 60, "#22c55e"),
    ("designer", "Designer", "Designs creatives and manages brand assets.", 55, "#14b8a6"),
    ("crm_manager", "CRM Manager", "Manages the CRM, leads, and pipeline.", 50, "#f59e0b"),
    ("sales", "Sales", "Works leads, opportunities, and deals in the CRM.", 45, "#f97316"),
    ("analyst", "Analyst", "Reads reports and analytics; can export.", 40, "#a855f7"),
    ("editor", "Editor", "Create + edit content, publish, view analytics.", 35, "#64748b"),
    ("viewer", "Viewer", "Read-only access.", 10, "#94a3b8"),
]

# Default permission grants — EXISTING catalog slugs only (grounded, enforced).
# 'admin'/'owner' get every permission via a separate CROSS JOIN (see below).
_DEFAULTS: dict[str, list[str]] = {
    "marketing_manager": [
        "campaign.create", "campaign.edit", "campaign.delete", "publish.content",
        "content.create", "content.edit", "analytics.view", "library.view",
        "crm.view", "crm.manage",
    ],
    "performance_marketer": [
        "campaign.create", "campaign.edit", "publish.content", "analytics.view", "library.view",
    ],
    "content_creator": ["content.create", "content.edit", "library.view"],
    "designer": ["content.create", "content.edit", "library.view"],
    "crm_manager": ["crm.view", "crm.manage", "lead.view", "lead.export"],
    "sales": ["crm.view", "crm.manage", "lead.view"],
    "analyst": ["analytics.view", "lead.export", "library.view"],
    "editor": [
        "content.create", "content.edit", "content.delete", "campaign.create",
        "campaign.edit", "publish.content", "analytics.view", "library.view", "lead.view",
    ],
    "viewer": ["lead.view", "analytics.view", "library.view", "crm.view"],
}


def upgrade() -> None:
    bind = op.get_bind()

    # 1) role_permissions.effect (allow|deny) — INHERIT is the absence of a row.
    op.add_column(
        "role_permissions",
        sa.Column("effect", sa.String(8), server_default="allow", nullable=False),
    )

    # 2) roles.priority + roles.color.
    op.add_column("roles", sa.Column("priority", sa.Integer(), server_default="0", nullable=False))
    op.add_column("roles", sa.Column("color", sa.String(16), nullable=True))

    # 3) Upsert the system roles (idempotent) + set priority/color/description.
    for slug, name, desc, priority, color in _ROLES:
        bind.execute(
            sa.text(
                """
                INSERT INTO roles (id, organization_id, slug, name, description, is_system, priority, color)
                VALUES (gen_random_uuid(), NULL, :slug, :name, :desc, true, :priority, :color)
                ON CONFLICT DO NOTHING
                """
            ),
            {"slug": slug, "name": name, "desc": desc, "priority": priority, "color": color},
        )
        # Keep priority/color/description current for pre-existing roles too.
        bind.execute(
            sa.text(
                """
                UPDATE roles SET priority = :priority, color = :color, description = :desc
                WHERE slug = :slug AND organization_id IS NULL AND is_system = true
                """
            ),
            {"slug": slug, "priority": priority, "color": color, "desc": desc},
        )

    # 4a) admin + owner → every permission (idempotent; owner already had all).
    for role_slug in ("owner", "admin"):
        bind.execute(
            sa.text(
                """
                INSERT INTO role_permissions (role_id, permission_id, effect)
                SELECT r.id, p.id, 'allow' FROM roles r CROSS JOIN permissions p
                WHERE r.slug = :role AND r.organization_id IS NULL AND r.is_system = true
                ON CONFLICT DO NOTHING
                """
            ),
            {"role": role_slug},
        )

    # 4b) the rest → their default grants (allow). Absent permissions = INHERIT.
    for role_slug, perm_slugs in _DEFAULTS.items():
        for perm_slug in perm_slugs:
            bind.execute(
                sa.text(
                    """
                    INSERT INTO role_permissions (role_id, permission_id, effect)
                    SELECT r.id, p.id, 'allow' FROM roles r, permissions p
                    WHERE r.slug = :role AND r.organization_id IS NULL AND r.is_system = true
                      AND p.slug = :perm
                    ON CONFLICT DO NOTHING
                    """
                ),
                {"role": role_slug, "perm": perm_slug},
            )


def downgrade() -> None:
    op.drop_column("roles", "color")
    op.drop_column("roles", "priority")
    op.drop_column("role_permissions", "effect")
