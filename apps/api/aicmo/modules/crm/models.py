"""CRM core ORM (Phase 6.5) — pipelines, stages, deals.

The sales backbone. Deals move through configurable pipeline stages, link
(optionally) to the EXISTING `leads` row they originated from (reuse — no
duplicate person record), and carry the AI next-action produced from real CRM
data. Media-agnostic boundary rule: no cross-module ORM relationships; the
lead link is a plain nullable FK (SET NULL) so a deal outlives its lead.
"""

from __future__ import annotations

import uuid
from datetime import date, datetime
from typing import Any

from sqlalchemy import (
    Boolean,
    Date,
    DateTime,
    ForeignKey,
    Integer,
    Numeric,
    String,
    Text,
    func,
)
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.dialects.postgresql import UUID as PgUUID
from sqlalchemy.orm import Mapped, mapped_column

from aicmo.db.base import Base, TenantMixin, TimestampMixin


class Pipeline(Base, TimestampMixin, TenantMixin):
    __tablename__ = "crm_pipelines"

    id: Mapped[uuid.UUID] = mapped_column(PgUUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    name: Mapped[str] = mapped_column(String(120))
    # marketing | sales | enterprise | agency | custom — free-text label, never
    # an industry branch (Creative-Studio Law 2 spirit: no code forks per kind).
    kind: Mapped[str] = mapped_column(String(24), server_default="sales")
    is_default: Mapped[bool] = mapped_column(Boolean, server_default="false")
    archived: Mapped[bool] = mapped_column(Boolean, server_default="false", index=True)
    created_by_user_id: Mapped[str | None] = mapped_column(String(255), nullable=True)


class PipelineStage(Base, TimestampMixin, TenantMixin):
    __tablename__ = "crm_pipeline_stages"

    id: Mapped[uuid.UUID] = mapped_column(PgUUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    pipeline_id: Mapped[uuid.UUID] = mapped_column(
        PgUUID(as_uuid=True), ForeignKey("crm_pipelines.id", ondelete="CASCADE"), index=True
    )
    name: Mapped[str] = mapped_column(String(80))
    position: Mapped[int] = mapped_column(Integer, server_default="0")
    # Default win probability for a deal sitting in this stage (0-100).
    probability: Mapped[int] = mapped_column(Integer, server_default="0")
    is_won: Mapped[bool] = mapped_column(Boolean, server_default="false")
    is_lost: Mapped[bool] = mapped_column(Boolean, server_default="false")


class Deal(Base, TimestampMixin, TenantMixin):
    __tablename__ = "crm_deals"

    id: Mapped[uuid.UUID] = mapped_column(PgUUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    pipeline_id: Mapped[uuid.UUID] = mapped_column(
        PgUUID(as_uuid=True), ForeignKey("crm_pipelines.id", ondelete="CASCADE"), index=True
    )
    stage_id: Mapped[uuid.UUID | None] = mapped_column(
        PgUUID(as_uuid=True), ForeignKey("crm_pipeline_stages.id", ondelete="SET NULL"),
        nullable=True, index=True,
    )
    # Reuse the existing marketing lead as the source person (no duplicate).
    lead_id: Mapped[uuid.UUID | None] = mapped_column(
        PgUUID(as_uuid=True), ForeignKey("leads.id", ondelete="SET NULL"), nullable=True, index=True
    )
    title: Mapped[str] = mapped_column(String(200))
    company: Mapped[str | None] = mapped_column(String(200), nullable=True)
    contact_name: Mapped[str | None] = mapped_column(String(200), nullable=True)
    contact_email: Mapped[str | None] = mapped_column(String(320), nullable=True)
    contact_phone: Mapped[str | None] = mapped_column(String(64), nullable=True)
    value: Mapped[float] = mapped_column(Numeric(14, 2), server_default="0")
    currency: Mapped[str] = mapped_column(String(3), server_default="USD")
    # Effective probability — overrides the stage default when set.
    probability: Mapped[int | None] = mapped_column(Integer, nullable=True)
    status: Mapped[str] = mapped_column(String(12), server_default="open", index=True)  # open|won|lost
    priority: Mapped[str] = mapped_column(String(8), server_default="medium")  # low|medium|high
    expected_close_date: Mapped[date | None] = mapped_column(Date, nullable=True)
    owner_user_id: Mapped[str | None] = mapped_column(String(255), nullable=True, index=True)
    source: Mapped[str | None] = mapped_column(String(64), nullable=True)
    tags: Mapped[list[Any]] = mapped_column(JSONB, server_default="[]")
    products: Mapped[list[Any]] = mapped_column(JSONB, server_default="[]")
    competitors: Mapped[list[Any]] = mapped_column(JSONB, server_default="[]")
    lost_reason: Mapped[str | None] = mapped_column(Text, nullable=True)
    won_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    lost_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    # Cached grounded AI next-action (recommendation/reason/confidence/expected_result + scores).
    ai_next_action: Mapped[dict[str, Any] | None] = mapped_column(JSONB, nullable=True)
    ai_generated_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)


class DealStageEvent(Base, TenantMixin):
    """Immutable audit of every stage move (the deal's activity timeline seed)."""

    __tablename__ = "crm_deal_stage_events"

    id: Mapped[uuid.UUID] = mapped_column(PgUUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    deal_id: Mapped[uuid.UUID] = mapped_column(
        PgUUID(as_uuid=True), ForeignKey("crm_deals.id", ondelete="CASCADE"), index=True
    )
    from_stage_id: Mapped[uuid.UUID | None] = mapped_column(PgUUID(as_uuid=True), nullable=True)
    to_stage_id: Mapped[uuid.UUID | None] = mapped_column(PgUUID(as_uuid=True), nullable=True)
    from_status: Mapped[str | None] = mapped_column(String(12), nullable=True)
    to_status: Mapped[str | None] = mapped_column(String(12), nullable=True)
    actor_user_id: Mapped[str | None] = mapped_column(String(255), nullable=True)
    note: Mapped[str | None] = mapped_column(Text, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
