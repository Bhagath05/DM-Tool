"""Add the content.read permission and grant it to content-capable roles.

Phase 6.7 — the Creative Studio's brief + design READ routes gate on
``require_permission("content.read")`` (aicmo/modules/creative/brief_router.py
and aicmo/modules/creative/design/router.py), but that slug was never added to
the permission catalog seeded in 0014/0067. Owner and admin receive "every
permission" via a CROSS JOIN over the catalog, so a slug that is NOT a catalog
row is granted to nobody — every role (owner included) is denied, and the
Studio shows "missing permission 'content.read'".

This migration is additive and necessary: a permission has to exist as a DB row
for the gate to resolve. It:

  1. inserts ``content.read`` into the catalog, and
  2. grants it (allow) to every role that already holds a content WRITE
     permission (content.create / content.edit / content.delete) — i.e. owner,
     admin, and the content-worker roles. Being able to read content you can
     already write is the least privilege: no unrelated role is touched, no
     broad bypass is introduced, and the slug's meaning (view content) is
     unchanged. Read-only roles with no content permission (viewer, analyst)
     are deliberately NOT granted it.

Idempotent (ON CONFLICT DO NOTHING) and reversible.

Revision ID: 0080_content_read_permission
Revises: 0079_widen_outcome_status
Create Date: 2026-10-09
"""

from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0080_content_read_permission"
down_revision: str | None = "0079_widen_outcome_status"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

_SLUG = "content.read"


def upgrade() -> None:
    bind = op.get_bind()

    # 1) Catalog row (idempotent on the unique slug).
    bind.execute(
        sa.text(
            """
            INSERT INTO permissions (id, slug, name, description, category, created_at)
            VALUES (gen_random_uuid(), :slug, 'View content',
                    'View generated content, briefs, and designs', 'content', now())
            ON CONFLICT (slug) DO NOTHING
            """
        ),
        {"slug": _SLUG},
    )

    # 2) Grant content.read to every role that can already write content.
    #    This reaches owner + admin (they hold every write permission) and the
    #    content-worker roles, without touching unrelated roles.
    bind.execute(
        sa.text(
            """
            INSERT INTO role_permissions (role_id, permission_id, effect)
            SELECT DISTINCT rp.role_id, cr.id, 'allow'
            FROM role_permissions rp
            JOIN permissions p ON p.id = rp.permission_id
            CROSS JOIN (SELECT id FROM permissions WHERE slug = :slug) cr
            WHERE p.slug IN ('content.create', 'content.edit', 'content.delete')
              AND rp.effect = 'allow'
            ON CONFLICT (role_id, permission_id) DO NOTHING
            """
        ),
        {"slug": _SLUG},
    )


def downgrade() -> None:
    bind = op.get_bind()
    bind.execute(
        sa.text(
            """
            DELETE FROM role_permissions
            WHERE permission_id IN (SELECT id FROM permissions WHERE slug = :slug)
            """
        ),
        {"slug": _SLUG},
    )
    bind.execute(
        sa.text("DELETE FROM permissions WHERE slug = :slug"),
        {"slug": _SLUG},
    )
