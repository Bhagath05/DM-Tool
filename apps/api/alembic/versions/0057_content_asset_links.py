"""Phase 6.2 — asset traceability links on generated_content.

Adds 4 nullable FK columns so every generated asset is fully traceable to its
campaign / bundle / strategy / recommendation. All nullable + SET NULL on delete
(the content outlives the thing it was linked to). Additive — no rewrite, no
backfill, no impact on existing rows.

Revision ID: 0057_content_asset_links
Revises: 0056_integration_event
Create Date: 2026-07-03
"""

from __future__ import annotations

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "0057_content_asset_links"
down_revision: Union[str, None] = "0056_integration_event"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

_LINKS = [
    ("campaign_id", "campaign_plans"),
    ("bundle_id", "bundles"),
    ("strategy_id", "marketing_strategies"),
    ("recommendation_id", "advisor_recommendations"),
]


def upgrade() -> None:
    for col, target in _LINKS:
        op.add_column(
            "generated_content",
            sa.Column(col, postgresql.UUID(as_uuid=True), nullable=True),
        )
        op.create_foreign_key(
            f"fk_generated_content_{col}",
            "generated_content",
            target,
            [col],
            ["id"],
            ondelete="SET NULL",
        )
        op.create_index(f"ix_generated_content_{col}", "generated_content", [col])


def downgrade() -> None:
    for col, _ in _LINKS:
        op.drop_index(f"ix_generated_content_{col}", "generated_content")
        op.drop_constraint(
            f"fk_generated_content_{col}", "generated_content", type_="foreignkey"
        )
        op.drop_column("generated_content", col)
