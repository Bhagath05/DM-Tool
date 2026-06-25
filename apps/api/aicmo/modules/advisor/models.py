"""ORM models for the Advisor memory layer."""

from __future__ import annotations

import uuid
from datetime import datetime

from sqlalchemy import DateTime, ForeignKey, Integer, Numeric, String, Text, func
from sqlalchemy.dialects.postgresql import JSONB, UUID
from sqlalchemy.orm import Mapped, mapped_column

from aicmo.db.base import Base, TenantMixin, TimestampMixin


class AdvisorRecommendation(Base, TimestampMixin, TenantMixin):
    __tablename__ = "advisor_recommendations"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True)
    user_id: Mapped[str] = mapped_column(String(255), index=True)

    record_type: Mapped[str] = mapped_column(String(32), index=True)
    title: Mapped[str] = mapped_column(Text)
    description: Mapped[str] = mapped_column(Text, default="")

    status: Mapped[str] = mapped_column(String(16), index=True, default="not_started")
    impact_score: Mapped[int] = mapped_column(Integer, default=0)
    confidence: Mapped[int] = mapped_column(Integer, default=0)
    impact_category: Mapped[str | None] = mapped_column(String(16), nullable=True)

    observation: Mapped[str | None] = mapped_column(Text, nullable=True)
    root_cause: Mapped[str | None] = mapped_column(Text, nullable=True)
    why: Mapped[str | None] = mapped_column(Text, nullable=True)
    data_used: Mapped[list] = mapped_column(JSONB, default=list)
    expected_result: Mapped[str | None] = mapped_column(Text, nullable=True)

    source_surface: Mapped[str] = mapped_column(String(32))
    source_fingerprint: Mapped[str] = mapped_column(String(128), index=True)

    generator_hint: Mapped[dict | None] = mapped_column(JSONB, nullable=True)
    linked_asset_type: Mapped[str | None] = mapped_column(String(32), nullable=True)
    linked_asset_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), nullable=True
    )
    parent_recommendation_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), nullable=True
    )

    outcome_summary: Mapped[str | None] = mapped_column(Text, nullable=True)
    repeat_rationale: Mapped[str | None] = mapped_column(Text, nullable=True)

    completed_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    skipped_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    completed_by_user_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), nullable=True
    )


class AdvisorOutcome(Base, TimestampMixin):
    __tablename__ = "advisor_outcomes"

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, default=uuid.uuid4
    )
    brand_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), index=True, nullable=False
    )
    recommendation_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("advisor_recommendations.id", ondelete="CASCADE"),
        unique=True,
        index=True,
    )
    evaluation_status: Mapped[str] = mapped_column(
        String(16), index=True, default="pending"
    )
    baseline_snapshot: Mapped[dict] = mapped_column(JSONB, default=dict)
    outcome_snapshot: Mapped[dict] = mapped_column(JSONB, default=dict)
    delta_summary: Mapped[str | None] = mapped_column(Text, nullable=True)
    effectiveness_score: Mapped[int | None] = mapped_column(Integer, nullable=True)
    evaluate_after: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    evaluated_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )


class AdvisorEffectivenessScore(Base, TimestampMixin):
    __tablename__ = "advisor_effectiveness_scores"

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, default=uuid.uuid4
    )
    brand_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), index=True)
    dimension: Mapped[str] = mapped_column(String(32))
    dimension_key: Mapped[str] = mapped_column(String(64))
    sample_size: Mapped[int] = mapped_column(Integer, default=0)
    success_rate: Mapped[float | None] = mapped_column(Numeric(5, 2), nullable=True)
    avg_effectiveness: Mapped[int | None] = mapped_column(Integer, nullable=True)
    last_computed_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )


class AdvisorAgentReport(Base):
    __tablename__ = "advisor_agent_reports"

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, default=uuid.uuid4
    )
    brand_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), index=True)
    report_type: Mapped[str] = mapped_column(String(32), index=True)
    period_start: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    period_end: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    confidence: Mapped[int] = mapped_column(Integer, default=0)
    data_sources_used: Mapped[list] = mapped_column(JSONB, default=list)
    sections: Mapped[list] = mapped_column(JSONB, default=list)
    summary: Mapped[str] = mapped_column(Text, default="")
    recommendations: Mapped[list] = mapped_column(JSONB, default=list)
    ready: Mapped[bool] = mapped_column(default=False)
    setup_steps: Mapped[list | None] = mapped_column(JSONB, nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=func.now(),
        nullable=False,
    )


class AdvisorMemoryEvent(Base):
    __tablename__ = "advisor_memory_events"

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, default=uuid.uuid4
    )
    recommendation_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("advisor_recommendations.id", ondelete="CASCADE"),
        index=True,
    )
    event_type: Mapped[str] = mapped_column(String(32))
    payload: Mapped[dict] = mapped_column(JSONB, default=dict)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=func.now(),
        nullable=False,
    )
