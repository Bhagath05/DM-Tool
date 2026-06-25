"""Business Brain — business_type on profiles

Revision ID: 0041_business_brain
Revises: 0040_connector_metrics
Create Date: 2026-06-19
"""

from __future__ import annotations

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "0041_business_brain"
down_revision: Union[str, None] = "0040_connector_metrics"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column(
        "business_profiles",
        sa.Column("business_type", sa.String(length=64), nullable=True),
    )
    op.execute(
        "UPDATE business_profiles SET business_type = industry WHERE business_type IS NULL"
    )


def downgrade() -> None:
    op.drop_column("business_profiles", "business_type")
