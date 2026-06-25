"""brand profile fields + default-per-org — phase 10.2f

Revision ID: 0029_brand_profile
Revises: 0028_org_profile
Create Date: 2026-06-05

Phase 10.2f — Extends `brands` with profile metadata and a default flag.

Three new columns:

  logo_url    TEXT      — Public URL to the brand logo.
  website    TEXT      — Public URL to the brand website.
  is_default  BOOLEAN  — Is this the org's default brand for new members?

Design notes on `is_default`:

  - NOT NULL with default FALSE — every existing brand starts non-default.
  - At most ONE default per organization, enforced by a partial unique
    index on (organization_id) WHERE is_default = true. The DB owns the
    invariant; service-layer code calls `set_default_brand()` which
    clears any prior default in the same transaction.
  - Archive-aware: the partial index doesn't gate on `status`, so a
    brand that gets archived while default still occupies the "default
    slot" until a service-layer cleanup runs. The recommended flow is
    to clear is_default in `archive_brand()` (Phase 10.2f service work).

  - Why not an `organizations.default_brand_id` column instead? Two
    reasons:
      1. Inverse-on-row makes "give me this org's default brand" a
         simple WHERE-clause without a join (faster + cleaner).
      2. Symmetric with how RBAC handles roles: state lives on the
         related row, not as a back-pointer.

  - Active-brand-switching (POST /brands/{id}/activate) is a DIFFERENT
    concept — it updates `organization_members.last_active_brand_id`
    (which already exists from Phase W1). `is_default` is the org-wide
    fallback when no per-user choice exists.

The `active` field exposed via the API is DERIVED from the existing
`status` column (`active = status == 'active'`). No new column is
added for it — Phase W1's status column remains the source of truth
and every existing query that filters on `status = 'active'` keeps
working unchanged.

Rollback drops the columns + index. No data loss beyond profile fields
and the default flag.
"""

from __future__ import annotations

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op


revision: str = "0029_brand_profile"
down_revision: Union[str, None] = "0028_org_profile"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column("brands", sa.Column("logo_url", sa.Text(), nullable=True))
    op.add_column("brands", sa.Column("website", sa.Text(), nullable=True))
    op.add_column(
        "brands",
        sa.Column(
            "is_default",
            sa.Boolean(),
            nullable=False,
            server_default=sa.text("false"),
        ),
    )

    # At most ONE default brand per organization.
    # The partial UNIQUE INDEX is the SOLE enforcement; the service
    # layer's "clear prior default before setting new" is an
    # optimisation, not the invariant.
    op.execute(
        "CREATE UNIQUE INDEX uq_brands_one_default_per_org "
        "ON brands (organization_id) "
        "WHERE is_default = true"
    )


def downgrade() -> None:
    op.execute("DROP INDEX IF EXISTS uq_brands_one_default_per_org")
    op.drop_column("brands", "is_default")
    op.drop_column("brands", "website")
    op.drop_column("brands", "logo_url")
