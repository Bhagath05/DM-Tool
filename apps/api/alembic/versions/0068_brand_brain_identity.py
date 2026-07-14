"""Phase 8 — Brand Brain: structured brand identity.

Adds the brand-identity fields the Brand Brain needs but `business_profiles`
didn't yet store: colours, fonts, keywords, brand rules, and a free-text
writing style. Everything the platform generates references these through
the generation-context block, so the Brand Brain becomes the single source
of truth for every AI workflow.

Additive + backward compatible: list columns default to `[]`, `writing_style`
is nullable. Existing rows are untouched and keep working.

Revision ID: 0068_brand_brain_identity
Revises: 0067_role_management_foundation
Create Date: 2026-07-14
"""

from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

from alembic import op

revision: str = "0068_brand_brain_identity"
down_revision: str | None = "0067_role_management_foundation"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

# JSONB string-arrays — same shape as the existing products/services columns.
_LIST_COLUMNS = ("brand_colors", "fonts", "keywords", "brand_rules")


def upgrade() -> None:
    for col in _LIST_COLUMNS:
        op.add_column(
            "business_profiles",
            sa.Column(
                col,
                postgresql.JSONB(astext_type=sa.Text()),
                server_default="[]",
                nullable=False,
            ),
        )
    op.add_column(
        "business_profiles",
        sa.Column("writing_style", sa.Text(), nullable=True),
    )


def downgrade() -> None:
    op.drop_column("business_profiles", "writing_style")
    for col in reversed(_LIST_COLUMNS):
        op.drop_column("business_profiles", col)
