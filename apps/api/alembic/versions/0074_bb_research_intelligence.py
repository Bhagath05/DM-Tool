"""Business Brain Phase 2 — research intelligence columns.

Revision ID: 0074_bb_research_intelligence
Revises: 0073_business_brain_foundation
Create Date: 2026-09-15

Additive only:
- brain_evidence.claim_key / superseded_by_id (supersession + contradiction)
- brain_research_jobs.result_summary (structured competitor/market payloads)

Does not modify auth tables. Does not create company/person/lead tables.
"""

from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

from alembic import op

revision: str = "0074_bb_research_intelligence"
down_revision: str | None = "0073_business_brain_foundation"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column(
        "brain_evidence",
        sa.Column("claim_key", sa.String(160), nullable=True),
    )
    op.add_column(
        "brain_evidence",
        sa.Column(
            "superseded_by_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("brain_evidence.id", ondelete="SET NULL"),
            nullable=True,
        ),
    )
    op.create_index(
        "ix_brain_evidence_brand_claim_key",
        "brain_evidence",
        ["brand_id", "claim_key"],
    )

    op.add_column(
        "brain_research_jobs",
        sa.Column(
            "result_summary",
            postgresql.JSONB(astext_type=sa.Text()),
            nullable=True,
        ),
    )


def downgrade() -> None:
    op.drop_column("brain_research_jobs", "result_summary")
    op.drop_index("ix_brain_evidence_brand_claim_key", table_name="brain_evidence")
    op.drop_column("brain_evidence", "superseded_by_id")
    op.drop_column("brain_evidence", "claim_key")
