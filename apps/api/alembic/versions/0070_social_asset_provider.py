"""Phase 5 — let SocialAsset represent provider-collected per-content metrics.

Reuses the existing per-post store (`social_assets` + `performance_signals`)
for the integration providers (Facebook/YouTube/LinkedIn/Pinterest) instead of
adding a new content-metrics table. Those providers connect via
`integration_connection`, not `social_connections`, so the existing NOT-NULL
`social_assets.connection_id` FK cannot be satisfied for their posts.

Minimal, backward-compatible change:
  1. `connection_id` becomes NULLABLE (existing Instagram rows keep their value).
  2. add `provider_slug` — which integration provider produced the row.
  3. add `integration_connection_id` — FK to the integration connection
     (ON DELETE SET NULL), the connection reference for provider-collected rows.

Existing rows stay valid: connection_id preserved, the two new columns NULL.
No RLS change (social_assets is app-layer brand-scoped, not RLS-managed).

Revision ID: 0070_social_asset_provider
Revises: 0069_website_discovery
Create Date: 2026-08-22
"""

from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

from alembic import op

revision: str = "0070_social_asset_provider"
down_revision: str | None = "0069_website_discovery"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    # 1. Relax the NOT NULL so integration-provider posts (no social_connection)
    #    can be stored. Existing rows are unaffected.
    op.alter_column(
        "social_assets",
        "connection_id",
        existing_type=postgresql.UUID(as_uuid=True),
        nullable=True,
    )
    # 2. Which integration provider produced the row (facebook_pages, youtube,
    #    linkedin_organic, pinterest). NULL for Instagram/social rows.
    op.add_column(
        "social_assets",
        sa.Column("provider_slug", sa.String(32), nullable=True),
    )
    # 3. Connection reference for provider-collected rows (SET NULL on delete so
    #    the historical asset + its performance signals survive a disconnect).
    op.add_column(
        "social_assets",
        sa.Column(
            "integration_connection_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("integration_connection.id", ondelete="SET NULL"),
            nullable=True,
        ),
    )
    op.create_index("ix_social_assets_provider_slug", "social_assets", ["provider_slug"])


def downgrade() -> None:
    op.drop_index("ix_social_assets_provider_slug", table_name="social_assets")
    op.drop_column("social_assets", "integration_connection_id")
    op.drop_column("social_assets", "provider_slug")
    # Restore NOT NULL. Safe only if no provider-collected (NULL connection_id)
    # rows exist; those are Phase-5 data created after this migration.
    op.alter_column(
        "social_assets",
        "connection_id",
        existing_type=postgresql.UUID(as_uuid=True),
        nullable=False,
    )
