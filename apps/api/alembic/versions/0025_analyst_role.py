"""seed analyst system role — phase 10.2d

Revision ID: 0025_analyst_role
Revises: 0024_security
Create Date: 2026-06-05

Phase 10.2d — adds the `analyst` system role to the RBAC seed.

Pre-10.2d the seeded roles were: owner, admin, editor, viewer.
Phase 10.2d's canonical 4-role surface is:
  owner, admin, ANALYST, viewer

Why we don't drop `editor`:
  - Existing orgs may have editor assignments. Dropping would orphan them.
  - `editor` is a perfectly valid role (more capable than analyst); it
    just isn't surfaced on the Settings → Team page UI by default.

Analyst permissions — derived from the spec ("Access workspace data,
no user management"):
  - analytics.view   — see dashboards
  - lead.view        — see leads
  - lead.export      — extract data (the differentiator vs viewer)
  - library.view     — browse asset library

Analyst is deliberately read-only on the content / campaign / publishing
surfaces. Promote to `editor` if a teammate needs to create content.

The seed is idempotent: every INSERT is guarded by ON CONFLICT DO NOTHING
on the unique slug index so re-running this migration (e.g. during
schema repair) is safe.
"""

from __future__ import annotations

from typing import Sequence, Union

from alembic import op


revision: str = "0025_analyst_role"
down_revision: Union[str, None] = "0024_security"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


_ANALYST_PERMISSIONS = (
    "analytics.view",
    "lead.view",
    "lead.export",
    "library.view",
)


def upgrade() -> None:
    # 1. Insert the analyst system role (organization_id NULL, is_system true).
    #
    # `uq_roles_system_slug` from migration 0014 is a partial UNIQUE INDEX
    # (not a NAMED CONSTRAINT), so `ON CONFLICT ON CONSTRAINT` doesn't apply.
    # We use ON CONFLICT inference with the matching WHERE predicate instead.
    # An NOT EXISTS guard would also work; using ON CONFLICT keeps the
    # rerun-safe semantics in a single statement.
    op.execute(
        """
        INSERT INTO roles (id, organization_id, slug, name, description, is_system)
        VALUES (
            gen_random_uuid(),
            NULL,
            'analyst',
            'Analyst',
            'Read-only access to workspace data, plus the ability to export leads.',
            true
        )
        ON CONFLICT (slug) WHERE organization_id IS NULL DO NOTHING;
        """
    )

    # 2. Grant the analyst role its permissions. SELECT-INSERT to handle
    #    permission ids without hardcoding them — and ON CONFLICT to
    #    keep the migration idempotent.
    for perm_slug in _ANALYST_PERMISSIONS:
        op.execute(
            f"""
            INSERT INTO role_permissions (role_id, permission_id)
            SELECT r.id, p.id
            FROM roles r
            CROSS JOIN permissions p
            WHERE r.slug = 'analyst'
              AND r.is_system = true
              AND p.slug = '{perm_slug}'
            ON CONFLICT DO NOTHING;
            """
        )


def downgrade() -> None:
    # Remove permission grants first (FK cascade would also handle it
    # if we dropped the role, but being explicit is cheap and safer).
    op.execute(
        """
        DELETE FROM role_permissions
        WHERE role_id IN (
            SELECT id FROM roles
            WHERE slug = 'analyst' AND is_system = true
        );
        """
    )
    # Then any member_roles pointing at it (defensive — production may
    # have assignments). Without this, the role delete would fail.
    op.execute(
        """
        DELETE FROM member_roles
        WHERE role_id IN (
            SELECT id FROM roles
            WHERE slug = 'analyst' AND is_system = true
        );
        """
    )
    op.execute(
        "DELETE FROM roles WHERE slug = 'analyst' AND is_system = true;"
    )
