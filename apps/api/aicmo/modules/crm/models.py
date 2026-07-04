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
    # Slice 2 — structured associations (additive, nullable → backward compatible
    # with Slice-1 deals that only had the embedded company/contact strings).
    company_id: Mapped[uuid.UUID | None] = mapped_column(
        PgUUID(as_uuid=True), ForeignKey("crm_companies.id", ondelete="SET NULL"),
        nullable=True, index=True,
    )
    primary_contact_id: Mapped[uuid.UUID | None] = mapped_column(
        PgUUID(as_uuid=True), ForeignKey("crm_contacts.id", ondelete="SET NULL"),
        nullable=True, index=True,
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


# =====================================================================
#  Slice 2 — Companies, Contacts, Activities (timeline)
# =====================================================================
class Company(Base, TimestampMixin, TenantMixin):
    __tablename__ = "crm_companies"

    id: Mapped[uuid.UUID] = mapped_column(PgUUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    name: Mapped[str] = mapped_column(String(200), index=True)
    # Normalised website host — the duplicate-detection key.
    domain: Mapped[str | None] = mapped_column(String(255), nullable=True, index=True)
    website: Mapped[str | None] = mapped_column(String(512), nullable=True)
    industry: Mapped[str | None] = mapped_column(String(120), nullable=True)
    annual_revenue: Mapped[float | None] = mapped_column(Numeric(16, 2), nullable=True)
    employees: Mapped[int | None] = mapped_column(Integer, nullable=True)
    tech_stack: Mapped[list[Any]] = mapped_column(JSONB, server_default="[]")
    social_links: Mapped[dict[str, Any]] = mapped_column(JSONB, server_default="{}")
    address: Mapped[str | None] = mapped_column(Text, nullable=True)
    timezone: Mapped[str | None] = mapped_column(String(48), nullable=True)
    owner_user_id: Mapped[str | None] = mapped_column(String(255), nullable=True, index=True)
    tags: Mapped[list[Any]] = mapped_column(JSONB, server_default="[]")
    custom_fields: Mapped[dict[str, Any]] = mapped_column(JSONB, server_default="{}")
    ai_summary: Mapped[dict[str, Any] | None] = mapped_column(JSONB, nullable=True)
    ai_generated_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    health_score: Mapped[int | None] = mapped_column(Integer, nullable=True)
    health_computed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    archived: Mapped[bool] = mapped_column(Boolean, server_default="false", index=True)


class Contact(Base, TimestampMixin, TenantMixin):
    __tablename__ = "crm_contacts"

    id: Mapped[uuid.UUID] = mapped_column(PgUUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    company_id: Mapped[uuid.UUID | None] = mapped_column(
        PgUUID(as_uuid=True), ForeignKey("crm_companies.id", ondelete="SET NULL"),
        nullable=True, index=True,
    )
    # Reuse the marketing lead as the origin record (no duplicate person).
    lead_id: Mapped[uuid.UUID | None] = mapped_column(
        PgUUID(as_uuid=True), ForeignKey("leads.id", ondelete="SET NULL"), nullable=True, index=True
    )
    name: Mapped[str] = mapped_column(String(200), index=True)
    title: Mapped[str | None] = mapped_column(String(160), nullable=True)
    email: Mapped[str | None] = mapped_column(String(320), nullable=True, index=True)
    phone: Mapped[str | None] = mapped_column(String(64), nullable=True)
    linkedin: Mapped[str | None] = mapped_column(String(512), nullable=True)
    owner_user_id: Mapped[str | None] = mapped_column(String(255), nullable=True, index=True)
    tags: Mapped[list[Any]] = mapped_column(JSONB, server_default="[]")
    custom_fields: Mapped[dict[str, Any]] = mapped_column(JSONB, server_default="{}")
    notes: Mapped[str | None] = mapped_column(Text, nullable=True)
    ai_summary: Mapped[dict[str, Any] | None] = mapped_column(JSONB, nullable=True)
    ai_generated_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    archived: Mapped[bool] = mapped_column(Boolean, server_default="false", index=True)


class Activity(Base, TenantMixin):
    """The CRM timeline — one row per note / email / call / meeting / file /
    linkedin touch, linkable to any of contact / company / deal."""

    __tablename__ = "crm_activities"

    id: Mapped[uuid.UUID] = mapped_column(PgUUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    kind: Mapped[str] = mapped_column(String(16), index=True)  # note|email|call|meeting|file|linkedin
    subject: Mapped[str | None] = mapped_column(String(240), nullable=True)
    body: Mapped[str | None] = mapped_column(Text, nullable=True)
    contact_id: Mapped[uuid.UUID | None] = mapped_column(
        PgUUID(as_uuid=True), ForeignKey("crm_contacts.id", ondelete="CASCADE"), nullable=True, index=True
    )
    company_id: Mapped[uuid.UUID | None] = mapped_column(
        PgUUID(as_uuid=True), ForeignKey("crm_companies.id", ondelete="CASCADE"), nullable=True, index=True
    )
    deal_id: Mapped[uuid.UUID | None] = mapped_column(
        PgUUID(as_uuid=True), ForeignKey("crm_deals.id", ondelete="CASCADE"), nullable=True, index=True
    )
    occurred_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(), index=True)
    actor_user_id: Mapped[str | None] = mapped_column(String(255), nullable=True)
    meta: Mapped[dict[str, Any]] = mapped_column(JSONB, server_default="{}")
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())


class DealContact(Base, TenantMixin):
    """Many contacts per deal (and one contact across many deals)."""

    __tablename__ = "crm_deal_contacts"

    deal_id: Mapped[uuid.UUID] = mapped_column(
        PgUUID(as_uuid=True), ForeignKey("crm_deals.id", ondelete="CASCADE"), primary_key=True
    )
    contact_id: Mapped[uuid.UUID] = mapped_column(
        PgUUID(as_uuid=True), ForeignKey("crm_contacts.id", ondelete="CASCADE"), primary_key=True
    )
    role: Mapped[str | None] = mapped_column(String(48), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())


# =====================================================================
#  Slice 3 — Tasks & Calendar
# =====================================================================
class Task(Base, TimestampMixin, TenantMixin):
    """A CRM task / calendar event. Links (all nullable, SET NULL) to any of
    lead / contact / company / deal / campaign — reuse, never a duplicate."""

    __tablename__ = "crm_tasks"

    id: Mapped[uuid.UUID] = mapped_column(PgUUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    title: Mapped[str] = mapped_column(String(240))
    description: Mapped[str | None] = mapped_column(Text, nullable=True)
    # call|meeting|demo|follow_up|email_reminder|internal|approval|custom
    activity_type: Mapped[str] = mapped_column(String(20), server_default="follow_up", index=True)
    # open|in_progress|completed|cancelled
    status: Mapped[str] = mapped_column(String(16), server_default="open", index=True)
    priority: Mapped[str] = mapped_column(String(8), server_default="medium")  # low|medium|high|urgent
    owner_user_id: Mapped[str | None] = mapped_column(String(255), nullable=True, index=True)
    assignee_user_id: Mapped[str | None] = mapped_column(String(255), nullable=True, index=True)
    due_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True, index=True)
    reminder_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    is_recurring: Mapped[bool] = mapped_column(Boolean, server_default="false")
    # {freq: daily|weekly|monthly, interval: int, until: iso|null, count: int|null}
    recurrence: Mapped[dict[str, Any] | None] = mapped_column(JSONB, nullable=True)
    recurrence_parent_id: Mapped[uuid.UUID | None] = mapped_column(
        PgUUID(as_uuid=True), ForeignKey("crm_tasks.id", ondelete="SET NULL"), nullable=True
    )
    calendar_event: Mapped[bool] = mapped_column(Boolean, server_default="false")
    estimated_minutes: Mapped[int | None] = mapped_column(Integer, nullable=True)
    actual_minutes: Mapped[int | None] = mapped_column(Integer, nullable=True)
    completed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    notes: Mapped[str | None] = mapped_column(Text, nullable=True)
    attachments: Mapped[list[Any]] = mapped_column(JSONB, server_default="[]")
    tags: Mapped[list[Any]] = mapped_column(JSONB, server_default="[]")
    # Relationships (reuse existing tables).
    lead_id: Mapped[uuid.UUID | None] = mapped_column(
        PgUUID(as_uuid=True), ForeignKey("leads.id", ondelete="SET NULL"), nullable=True, index=True
    )
    contact_id: Mapped[uuid.UUID | None] = mapped_column(
        PgUUID(as_uuid=True), ForeignKey("crm_contacts.id", ondelete="SET NULL"), nullable=True, index=True
    )
    company_id: Mapped[uuid.UUID | None] = mapped_column(
        PgUUID(as_uuid=True), ForeignKey("crm_companies.id", ondelete="SET NULL"), nullable=True, index=True
    )
    deal_id: Mapped[uuid.UUID | None] = mapped_column(
        PgUUID(as_uuid=True), ForeignKey("crm_deals.id", ondelete="SET NULL"), nullable=True, index=True
    )
    campaign_id: Mapped[uuid.UUID | None] = mapped_column(
        PgUUID(as_uuid=True), ForeignKey("campaign_plans.id", ondelete="SET NULL"), nullable=True, index=True
    )
    created_by_user_id: Mapped[str | None] = mapped_column(String(255), nullable=True)
    source: Mapped[str | None] = mapped_column(String(32), nullable=True)  # manual|automation:<event>
    ai_suggestion: Mapped[dict[str, Any] | None] = mapped_column(JSONB, nullable=True)
    ai_generated_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
