"""Phase 6.6 Slice 1 — Admin ≡ Owner permissions.

The Admin model (Part 10): the displayed "Admin" role must have the SAME
capabilities as the internal Owner (a Discord-style Administrator). Owner
already holds every permission; this grants the system `admin` role every
permission currently in the catalog too. Idempotent + additive — no member
loses access, and Owner stays the protected internal creator role.

Revision ID: 0066_admin_full_permissions
Revises: 0065_crm_ai_insights
Create Date: 2026-07-06
"""

from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op

revision: str = "0066_admin_full_permissions"
down_revision: str | None = "0065_crm_ai_insights"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    # Grant the system admin role every permission that exists (idempotent).
    op.get_bind().execute(
        sa.text(
            """
            INSERT INTO role_permissions (role_id, permission_id)
            SELECT r.id, p.id
            FROM roles r
            CROSS JOIN permissions p
            WHERE r.slug = 'admin' AND r.organization_id IS NULL AND r.is_system = true
            ON CONFLICT DO NOTHING
            """
        )
    )


def downgrade() -> None:
    # Non-destructive by design: we do not strip admin permissions on downgrade
    # (removing granted access is riskier than leaving the additive grant).
    pass
