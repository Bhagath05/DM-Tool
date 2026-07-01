"""Phase 3.2 — marketing_strategies table (Marketing Strategist).

One row per generated strategy, per brand, newest = current. Purely additive
(a new table) — no impact on existing tables or data.

Revision ID: 0047_marketing_strategies
Revises: 0046_business_understanding
Create Date: 2026-07-01
"""

from __future__ import annotations

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "0047_marketing_strategies"
down_revision: Union[str, None] = "0046_business_understanding"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "marketing_strategies",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("user_id", sa.String(length=255), nullable=False),
        sa.Column(
            "organization_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("organizations.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column(
            "brand_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("brands.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column(
            "status", sa.String(length=16), server_default="pending", nullable=False
        ),
        sa.Column(
            "strategy", postgresql.JSONB(astext_type=sa.Text()), nullable=True
        ),
        sa.Column("error", sa.Text(), nullable=True),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
    )
    op.create_index(
        "ix_marketing_strategies_user_id", "marketing_strategies", ["user_id"]
    )
    op.create_index(
        "ix_marketing_strategies_organization_id",
        "marketing_strategies",
        ["organization_id"],
    )
    op.create_index(
        "ix_marketing_strategies_brand_id", "marketing_strategies", ["brand_id"]
    )
    # "latest strategy for this brand" — the hot read path.
    op.create_index(
        "ix_marketing_strategies_brand_created",
        "marketing_strategies",
        ["brand_id", "created_at"],
    )


def downgrade() -> None:
    op.drop_index("ix_marketing_strategies_brand_created", "marketing_strategies")
    op.drop_index("ix_marketing_strategies_brand_id", "marketing_strategies")
    op.drop_index("ix_marketing_strategies_organization_id", "marketing_strategies")
    op.drop_index("ix_marketing_strategies_user_id", "marketing_strategies")
    op.drop_table("marketing_strategies")
