"""Add creative_provenance to social_assets.

Lets an ingested/published post be labelled as AI-generated, human-created, or
unknown so the evidence engine can build honest AI-vs-human performance
cohorts. Nullable + no default: an unlabelled row stays NULL and the evaluator
treats it as unknown (excluded from comparisons), never guessed.

Revision ID: 0071_social_asset_provenance
Revises: 0070_social_asset_provider
Create Date: 2026-09-11
"""

from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op

revision: str = "0071_social_asset_provenance"
down_revision: str | None = "0070_social_asset_provider"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column(
        "social_assets",
        sa.Column("creative_provenance", sa.String(16), nullable=True),
    )


def downgrade() -> None:
    op.drop_column("social_assets", "creative_provenance")
