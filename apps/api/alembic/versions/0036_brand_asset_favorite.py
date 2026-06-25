"""Brand asset favorite flag (CS5.1)

Revision ID: 0036_brand_asset_favorite
Revises: 0035_creative_studio
Create Date: 2026-06-16

Adds `is_favorite` to brand_asset so the asset library can favorite/sort.
Additive + reversible. Image crop/mask/fit live in the design doc JSONB —
no schema change for those.
"""

from __future__ import annotations

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "0036_brand_asset_favorite"
down_revision: Union[str, None] = "0035_creative_studio"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column(
        "brand_asset",
        sa.Column("is_favorite", sa.Boolean(), nullable=False, server_default=sa.text("false")),
    )
    op.create_index("ix_brand_asset_brand_favorite", "brand_asset", ["brand_id", "is_favorite"])


def downgrade() -> None:
    op.drop_index("ix_brand_asset_brand_favorite", table_name="brand_asset")
    op.drop_column("brand_asset", "is_favorite")
