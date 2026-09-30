"""Belief / learning memory (Phase 3A).

Adds ``beliefs`` (scoped, evidence-derived knowledge with status + supersession
lineage) and ``belief_evidence`` (thin references to EXISTING evidence rows — no
copies). Both are tenant-scoped (organization_id + brand_id) and receive the same
dormant org-scoped RLS policy as the other tenant tables. Purely additive.

Revision ID: 0077_belief_memory
Revises: 0076_agent_conversations
Create Date: 2026-10-01
"""

from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa

from aicmo.db import rls
from alembic import op

revision: str = "0077_belief_memory"
down_revision: str | None = "0076_agent_conversations"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

_UUID = sa.dialects.postgresql.UUID(as_uuid=True)

_CATEGORY = (
    "business, audience, market, positioning, offer, content, channel, campaign, "
    "creative, performance, learning"
)
_CATEGORY_IN = ", ".join(f"'{c.strip()}'" for c in _CATEGORY.split(","))
_STATUS_IN = "'active', 'superseded', 'contradicted', 'unvalidated', 'retired'"
_REFKIND_IN = (
    "'brain_evidence', 'advisor_recommendation', 'advisor_outcome', "
    "'learning_insight', 'data_source'"
)
_RELATION_IN = "'supports', 'contradicts'"


def _tenant_cols() -> list[sa.Column]:
    return [
        sa.Column("organization_id", _UUID, sa.ForeignKey("organizations.id", ondelete="CASCADE"), nullable=False),
        sa.Column("brand_id", _UUID, sa.ForeignKey("brands.id", ondelete="CASCADE"), nullable=False),
    ]


def _timestamps() -> list[sa.Column]:
    return [
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
    ]


def upgrade() -> None:
    op.create_table(
        "beliefs",
        sa.Column("id", _UUID, primary_key=True),
        *_tenant_cols(),
        sa.Column("category", sa.String(24), nullable=False),
        sa.Column("subject_key", sa.String(200), nullable=False),
        sa.Column("statement", sa.Text(), nullable=False),
        sa.Column("scope", sa.dialects.postgresql.JSONB(), server_default=sa.text("'{}'::jsonb"), nullable=False),
        sa.Column("status", sa.String(16), server_default="unvalidated", nullable=False),
        sa.Column("confidence", sa.Integer(), server_default="0", nullable=False),
        sa.Column("confidence_reason", sa.Text(), server_default="", nullable=False),
        sa.Column("evidence_count", sa.Integer(), server_default="0", nullable=False),
        sa.Column("validated_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("valid_from", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("valid_until", sa.DateTime(timezone=True), nullable=True),
        sa.Column("superseded_by_id", _UUID, sa.ForeignKey("beliefs.id", ondelete="SET NULL"), nullable=True),
        sa.Column("parent_belief_id", _UUID, sa.ForeignKey("beliefs.id", ondelete="SET NULL"), nullable=True),
        *_timestamps(),
        sa.CheckConstraint(f"category IN ({_CATEGORY_IN})", name="ck_beliefs_category"),
        sa.CheckConstraint(f"status IN ({_STATUS_IN})", name="ck_beliefs_status"),
        sa.CheckConstraint("confidence >= 0 AND confidence <= 100", name="ck_beliefs_confidence"),
    )
    op.create_index("ix_beliefs_organization_id", "beliefs", ["organization_id"])
    op.create_index("ix_beliefs_brand_category", "beliefs", ["brand_id", "category"])
    op.create_index("ix_beliefs_brand_subject", "beliefs", ["brand_id", "subject_key"])
    op.create_index("ix_beliefs_brand_status", "beliefs", ["brand_id", "status"])
    op.create_index("ix_beliefs_superseded_by", "beliefs", ["superseded_by_id"])

    op.create_table(
        "belief_evidence",
        sa.Column("id", _UUID, primary_key=True),
        *_tenant_cols(),
        sa.Column("belief_id", _UUID, sa.ForeignKey("beliefs.id", ondelete="CASCADE"), nullable=False),
        sa.Column("ref_kind", sa.String(32), nullable=False),
        sa.Column("ref_id", _UUID, nullable=True),
        sa.Column("relation", sa.String(16), server_default="supports", nullable=False),
        sa.Column("note", sa.String(280), nullable=True),
        *_timestamps(),
        sa.CheckConstraint(f"ref_kind IN ({_REFKIND_IN})", name="ck_belief_evidence_refkind"),
        sa.CheckConstraint(f"relation IN ({_RELATION_IN})", name="ck_belief_evidence_relation"),
        sa.UniqueConstraint("belief_id", "ref_kind", "ref_id", "relation", name="uq_belief_evidence_ref"),
    )
    op.create_index("ix_belief_evidence_organization_id", "belief_evidence", ["organization_id"])
    op.create_index("ix_belief_evidence_belief", "belief_evidence", ["belief_id"])
    op.create_index("ix_belief_evidence_ref", "belief_evidence", ["ref_kind", "ref_id"])

    for table in ("beliefs", "belief_evidence"):
        op.execute(rls.create_policy_sql(table))


def downgrade() -> None:
    for table in ("belief_evidence", "beliefs"):
        op.execute(rls.drop_policy_sql(table))
    op.drop_index("ix_belief_evidence_ref", table_name="belief_evidence")
    op.drop_index("ix_belief_evidence_belief", table_name="belief_evidence")
    op.drop_index("ix_belief_evidence_organization_id", table_name="belief_evidence")
    op.drop_table("belief_evidence")
    op.drop_index("ix_beliefs_superseded_by", table_name="beliefs")
    op.drop_index("ix_beliefs_brand_status", table_name="beliefs")
    op.drop_index("ix_beliefs_brand_subject", table_name="beliefs")
    op.drop_index("ix_beliefs_brand_category", table_name="beliefs")
    op.drop_index("ix_beliefs_organization_id", table_name="beliefs")
    op.drop_table("beliefs")
