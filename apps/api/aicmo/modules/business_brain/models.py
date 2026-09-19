"""ORM models for Business Brain research, evidence, and ICP hypotheses."""

from __future__ import annotations

import uuid
from datetime import datetime

from sqlalchemy import (
    DateTime,
    ForeignKey,
    Index,
    Integer,
    String,
    Text,
    UniqueConstraint,
    func,
    text,
)
from sqlalchemy.dialects.postgresql import JSONB, UUID
from sqlalchemy.orm import Mapped, mapped_column

from aicmo.db.base import Base, TenantMixin, TimestampMixin


class BrainResearchJob(Base, TenantMixin, TimestampMixin):
    """One website (or future) research run for a brand."""

    __tablename__ = "brain_research_jobs"
    __table_args__ = (
        # One active research per brand+kind+URL — DB-enforced idempotency.
        Index(
            "uq_brain_research_jobs_active",
            "brand_id",
            "kind",
            "normalized_url",
            unique=True,
            postgresql_where=text("status IN ('queued', 'running')"),
        ),
        Index("ix_brain_research_jobs_brand_status", "brand_id", "status"),
    )

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, default=uuid.uuid4
    )
    created_by_user_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True))

    kind: Mapped[str] = mapped_column(String(32), default="website", server_default="website")
    input_url: Mapped[str] = mapped_column(String(500))
    normalized_url: Mapped[str] = mapped_column(String(500))

    # queued | running | completed | partial | failed
    status: Mapped[str] = mapped_column(String(16), default="queued", server_default="queued")
    error_category: Mapped[str | None] = mapped_column(String(64), nullable=True)
    error_message: Mapped[str | None] = mapped_column(Text, nullable=True)

    provider: Mapped[str | None] = mapped_column(String(64), nullable=True)
    started_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    finished_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    duration_ms: Mapped[int | None] = mapped_column(Integer, nullable=True)
    source_count: Mapped[int] = mapped_column(Integer, default=0, server_default="0")
    evidence_count: Mapped[int] = mapped_column(Integer, default=0, server_default="0")

    # Structured research payload (competitors / market signals) — never a CRM store.
    result_summary: Mapped[dict | None] = mapped_column(JSONB, nullable=True)

    # Optional link to legacy discovery draft/apply flow.
    discovery_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("website_discoveries.id", ondelete="SET NULL"),
        nullable=True,
    )


class BrainEvidence(Base, TenantMixin, TimestampMixin):
    """Typed business knowledge claim with provenance.

    kind is one of: fact | observation | hypothesis | recommendation
    Never auto-promote hypothesis → fact.
    """

    __tablename__ = "brain_evidence"
    __table_args__ = (
        Index("ix_brain_evidence_brand_kind", "brand_id", "kind"),
        Index("ix_brain_evidence_brand_category", "brand_id", "category"),
        Index("ix_brain_evidence_research_job", "research_job_id"),
        Index("ix_brain_evidence_brand_claim_key", "brand_id", "claim_key"),
    )

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, default=uuid.uuid4
    )
    research_job_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("brain_research_jobs.id", ondelete="SET NULL"),
        nullable=True,
    )

    kind: Mapped[str] = mapped_column(String(32))  # fact|observation|hypothesis|recommendation
    category: Mapped[str] = mapped_column(String(32))  # business|audience|market|marketing
    claim: Mapped[str] = mapped_column(String(1000))
    confidence: Mapped[int] = mapped_column(Integer, default=50, server_default="50")
    # active | superseded | contradicted — never silently overwrite prior claims.
    status: Mapped[str] = mapped_column(String(16), default="active", server_default="active")
    # Stable key for supersession/contradiction (e.g. competitor:<host>).
    claim_key: Mapped[str | None] = mapped_column(String(160), nullable=True)
    superseded_by_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("brain_evidence.id", ondelete="SET NULL"),
        nullable=True,
    )

    source_url: Mapped[str | None] = mapped_column(String(500), nullable=True)
    source_type: Mapped[str] = mapped_column(String(32), default="website", server_default="website")
    snippet: Mapped[str | None] = mapped_column(String(800), nullable=True)

    # Provenance timestamp (retrieved_at alias in API = discovered_at).
    discovered_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )


class BrainIcp(Base, TenantMixin, TimestampMixin):
    """ICP hypothesis: WHO is likely to buy — not a campaign or lead list."""

    __tablename__ = "brain_icps"
    __table_args__ = (Index("ix_brain_icps_brand_status", "brand_id", "status"),)

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, default=uuid.uuid4
    )
    name: Mapped[str] = mapped_column(String(160))
    description: Mapped[str] = mapped_column(Text)
    industries: Mapped[list] = mapped_column(JSONB, default=list, server_default="[]")
    company_size: Mapped[str | None] = mapped_column(String(120), nullable=True)
    geography: Mapped[list] = mapped_column(JSONB, default=list, server_default="[]")
    buyer_roles: Mapped[list] = mapped_column(JSONB, default=list, server_default="[]")
    pain_points: Mapped[list] = mapped_column(JSONB, default=list, server_default="[]")
    buying_signals: Mapped[list] = mapped_column(JSONB, default=list, server_default="[]")
    exclusions: Mapped[list] = mapped_column(JSONB, default=list, server_default="[]")
    confidence: Mapped[int] = mapped_column(Integer, default=40, server_default="40")
    # hypothesis | accepted | rejected | archived
    status: Mapped[str] = mapped_column(String(16), default="hypothesis", server_default="hypothesis")
    research_job_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("brain_research_jobs.id", ondelete="SET NULL"),
        nullable=True,
    )


class BrainIcpEvidence(Base, TenantMixin, TimestampMixin):
    """Join: which evidence supports an ICP hypothesis."""

    __tablename__ = "brain_icp_evidence"
    __table_args__ = (
        UniqueConstraint("icp_id", "evidence_id", name="uq_brain_icp_evidence"),
        Index("ix_brain_icp_evidence_icp", "icp_id"),
    )

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, default=uuid.uuid4
    )
    icp_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("brain_icps.id", ondelete="CASCADE"),
        nullable=False,
    )
    evidence_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("brain_evidence.id", ondelete="CASCADE"),
        nullable=False,
    )
