"""Phase 1 — ORM for DB-configurable plans + quotas + Stripe idempotency.

These tables make pricing/quotas the system of record in Postgres so
they're tunable without a deploy (mirrors migration 0033 column-for-
column; the WHY lives in the migration). Thin models, no relationship()
joins — queried explicitly by the plan_service, same boundary rule as
the other billing models.
"""

from __future__ import annotations

import uuid
from datetime import datetime

from sqlalchemy import (
    Boolean,
    DateTime,
    ForeignKey,
    Integer,
    String,
    Text,
    UniqueConstraint,
    func,
)
from sqlalchemy.dialects.postgresql import UUID as PgUUID
from sqlalchemy.orm import Mapped, mapped_column

from aicmo.db.base import Base


class Plan(Base):
    __tablename__ = "plan"

    slug: Mapped[str] = mapped_column(String(32), primary_key=True)
    display_name: Mapped[str] = mapped_column(String(64), nullable=False)
    tagline: Mapped[str | None] = mapped_column(Text, nullable=True)
    monthly_price_cents: Mapped[int | None] = mapped_column(Integer, nullable=True)
    currency: Mapped[str] = mapped_column(String(3), nullable=False, server_default="USD")
    stripe_price_id: Mapped[str | None] = mapped_column(String(128), nullable=True)
    availability: Mapped[str] = mapped_column(
        String(16), nullable=False, server_default="upcoming"
    )
    is_default: Mapped[bool] = mapped_column(
        Boolean, nullable=False, server_default="false"
    )
    is_active: Mapped[bool] = mapped_column(
        Boolean, nullable=False, server_default="true"
    )
    sort_order: Mapped[int] = mapped_column(Integer, nullable=False, server_default="0")
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )


class PlanQuota(Base):
    __tablename__ = "plan_quota"
    __table_args__ = (
        UniqueConstraint("plan_slug", "usage_kind", name="uq_plan_quota_plan_kind"),
    )

    id: Mapped[uuid.UUID] = mapped_column(
        PgUUID(as_uuid=True), primary_key=True, server_default=func.gen_random_uuid()
    )
    plan_slug: Mapped[str] = mapped_column(
        String(32), ForeignKey("plan.slug", ondelete="CASCADE"), nullable=False
    )
    usage_kind: Mapped[str] = mapped_column(String(32), nullable=False)
    # NULL = unlimited.
    monthly_limit: Mapped[int | None] = mapped_column(Integer, nullable=True)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )


class StripeEvent(Base):
    """Webhook idempotency log — one row per processed Stripe event id.
    Account-level (not tenant data); excluded from RLS by design."""

    __tablename__ = "stripe_event"

    event_id: Mapped[str] = mapped_column(String(64), primary_key=True)
    type: Mapped[str] = mapped_column(String(64), nullable=False)
    organization_id: Mapped[uuid.UUID | None] = mapped_column(
        PgUUID(as_uuid=True),
        ForeignKey("organizations.id", ondelete="SET NULL"),
        nullable=True,
    )
    received_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )
    processed_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
