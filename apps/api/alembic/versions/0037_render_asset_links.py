"""Render asset links — auto-render Phase 1

Revision ID: 0037_render_asset_links
Revises: 0036_brand_asset_favorite
Create Date: 2026-06-17

Adds carousel slide ordering on rendered_visuals and links generated_ads
to their auto-rendered PNG row.
"""

from __future__ import annotations

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "0037_render_asset_links"
down_revision: Union[str, None] = "0036_brand_asset_favorite"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column(
        "rendered_visuals",
        sa.Column("slide_index", sa.Integer(), nullable=True),
    )
    op.add_column(
        "generated_ads",
        sa.Column(
            "rendered_visual_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("rendered_visuals.id", ondelete="SET NULL"),
            nullable=True,
        ),
    )
    op.create_index(
        "ix_generated_ads_rendered_visual_id",
        "generated_ads",
        ["rendered_visual_id"],
    )


def downgrade() -> None:
    op.drop_index("ix_generated_ads_rendered_visual_id", table_name="generated_ads")
    op.drop_column("generated_ads", "rendered_visual_id")
    op.drop_column("rendered_visuals", "slide_index")
