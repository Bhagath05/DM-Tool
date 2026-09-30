"""Belief / learning memory — a thin, tenant-scoped graph over EXISTING evidence.

A ``Belief`` records what DM Tool currently holds true for a scoped subject, with
a server-derived confidence and an explicit status. It does NOT copy evidence:
``BeliefEvidence`` rows reference existing rows (brain_evidence, advisor
recommendations/outcomes, learning insights) by id, or carry a provenance label.
Supersession/contradiction are modeled as relationships, never destructive edits,
so the historical chain stays auditable.
"""

from __future__ import annotations

import uuid
from datetime import datetime

from sqlalchemy import (
    CheckConstraint,
    DateTime,
    ForeignKey,
    Index,
    Integer,
    String,
    Text,
    UniqueConstraint,
    func,
)
from sqlalchemy.dialects.postgresql import JSONB, UUID
from sqlalchemy.orm import Mapped, mapped_column

from aicmo.db.base import Base, TenantMixin, TimestampMixin
from aicmo.modules.belief.enums import (
    BeliefCategory,
    BeliefStatus,
    EvidenceRefKind,
    EvidenceRelation,
)

_CATEGORY_IN = ", ".join(f"'{c.value}'" for c in BeliefCategory)
_STATUS_IN = ", ".join(f"'{s.value}'" for s in BeliefStatus)
_REFKIND_IN = ", ".join(f"'{k.value}'" for k in EvidenceRefKind)
_RELATION_IN = ", ".join(f"'{r.value}'" for r in EvidenceRelation)


class Belief(Base, TenantMixin, TimestampMixin):
    """One scoped, evidence-backed belief for a brand."""

    __tablename__ = "beliefs"
    __table_args__ = (
        CheckConstraint(f"category IN ({_CATEGORY_IN})", name="ck_beliefs_category"),
        CheckConstraint(f"status IN ({_STATUS_IN})", name="ck_beliefs_status"),
        CheckConstraint("confidence >= 0 AND confidence <= 100", name="ck_beliefs_confidence"),
        Index("ix_beliefs_brand_category", "brand_id", "category"),
        Index("ix_beliefs_brand_subject", "brand_id", "subject_key"),
        Index("ix_beliefs_brand_status", "brand_id", "status"),
        Index("ix_beliefs_superseded_by", "superseded_by_id"),
    )

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    category: Mapped[str] = mapped_column(String(24), nullable=False)
    # Stable key for supersession/lookup within (brand, category), e.g.
    # "channel:reels_vs_static:aud:in_b2c_fitness_18_30".
    subject_key: Mapped[str] = mapped_column(String(200), nullable=False)
    statement: Mapped[str] = mapped_column(Text, nullable=False)
    # Structured scope so a belief never overgeneralizes (audience/channel/
    # campaign/content_type/market/time_window). Bounded, non-sensitive dict.
    scope: Mapped[dict] = mapped_column(JSONB, nullable=False, server_default="{}")

    status: Mapped[str] = mapped_column(String(16), nullable=False, server_default="unvalidated")
    # Confidence is DERIVED from evidence by the service — never LLM-asserted.
    confidence: Mapped[int] = mapped_column(Integer, nullable=False, server_default="0")
    confidence_reason: Mapped[str] = mapped_column(Text, nullable=False, server_default="")
    evidence_count: Mapped[int] = mapped_column(Integer, nullable=False, server_default="0")
    validated_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)

    valid_from: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )
    valid_until: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)

    # Lineage: the belief that replaced this one, and the belief this one grew from.
    superseded_by_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("beliefs.id", ondelete="SET NULL"), nullable=True
    )
    parent_belief_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("beliefs.id", ondelete="SET NULL"), nullable=True
    )


class BeliefEvidence(Base, TenantMixin, TimestampMixin):
    """A reference from a belief to a piece of EXISTING evidence (by id) — never a
    copy. ``relation`` records whether it supports or contradicts the belief."""

    __tablename__ = "belief_evidence"
    __table_args__ = (
        CheckConstraint(f"ref_kind IN ({_REFKIND_IN})", name="ck_belief_evidence_refkind"),
        CheckConstraint(f"relation IN ({_RELATION_IN})", name="ck_belief_evidence_relation"),
        UniqueConstraint("belief_id", "ref_kind", "ref_id", "relation", name="uq_belief_evidence_ref"),
        Index("ix_belief_evidence_belief", "belief_id"),
        Index("ix_belief_evidence_ref", "ref_kind", "ref_id"),
    )

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    belief_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("beliefs.id", ondelete="CASCADE"), nullable=False
    )
    ref_kind: Mapped[str] = mapped_column(String(32), nullable=False)
    # The referenced row's id (NULL for a DATA_SOURCE provenance label).
    ref_id: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True), nullable=True)
    relation: Mapped[str] = mapped_column(String(16), nullable=False, server_default="supports")
    # Short provenance label (e.g. a source name). Never a secret or payload copy.
    note: Mapped[str | None] = mapped_column(String(280), nullable=True)
