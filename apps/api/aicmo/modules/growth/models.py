"""Growth module ORM — outcome objective + the outcome catalogs.

Mirrors migration 0035 column-for-column; WHY lives in the migration.
Thin models, no relationship() joins (queried explicitly by brand_id —
same boundary rule as billing/creative).

`objective_kind` + `layout_primitive` are non-tenant catalogs (like
`creative_format`/`plan`) — OUTCOME / COMPOSITION semantics, never
industry. `growth_objective` is the tenant-scoped primary object.
"""

from __future__ import annotations

import uuid
from datetime import datetime
from typing import Any

from sqlalchemy import Boolean, DateTime, ForeignKey, Integer, String, Text, func
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.dialects.postgresql import UUID as PgUUID
from sqlalchemy.orm import Mapped, mapped_column

from aicmo.db.base import Base, TenantMixin, TimestampMixin


class ObjectiveKind(Base):
    """Non-tenant outcome taxonomy (excluded from RLS, like `plan`)."""

    __tablename__ = "objective_kind"

    slug: Mapped[str] = mapped_column(String(48), primary_key=True)
    display_name: Mapped[str] = mapped_column(String(64))
    category: Mapped[str] = mapped_column(String(24))  # lead|booking|sale|awareness|install|hire|signup|traffic|retention
    kpi_hint: Mapped[str | None] = mapped_column(String(128), nullable=True)
    default_channels: Mapped[list[Any]] = mapped_column(JSONB, server_default="[]")
    is_active: Mapped[bool] = mapped_column(Boolean, server_default="true")
    sort_order: Mapped[int] = mapped_column(Integer, server_default="0")
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())


class LayoutPrimitive(Base):
    """Non-tenant composition library (excluded from RLS). Generated, never
    categorized by industry (Law 2). `objective_affinity` keys are
    objective_kind.category values — outcome semantics only."""

    __tablename__ = "layout_primitive"

    slug: Mapped[str] = mapped_column(String(48), primary_key=True)
    kind: Mapped[str] = mapped_column(String(24))  # focal|hierarchy|grid|type_scale|color_system
    params: Mapped[dict[str, Any]] = mapped_column(JSONB, server_default="{}")
    objective_affinity: Mapped[dict[str, Any]] = mapped_column(JSONB, server_default="{}")
    is_active: Mapped[bool] = mapped_column(Boolean, server_default="true")
    sort_order: Mapped[int] = mapped_column(Integer, server_default="0")
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())


class GrowthObjective(Base, TimestampMixin, TenantMixin):
    """The primary object (Law 1). `statement` is free text (the goal);
    `objective_kind` is the outcome category. No industry column."""

    __tablename__ = "growth_objective"

    id: Mapped[uuid.UUID] = mapped_column(PgUUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    user_id: Mapped[str | None] = mapped_column(String(255), nullable=True)
    business_profile_id: Mapped[uuid.UUID | None] = mapped_column(PgUUID(as_uuid=True), nullable=True)
    objective_kind: Mapped[str] = mapped_column(
        String(48), ForeignKey("objective_kind.slug", ondelete="RESTRICT")
    )
    statement: Mapped[str] = mapped_column(Text)
    audience_hypothesis: Mapped[str | None] = mapped_column(Text, nullable=True)
    budget_cents: Mapped[int | None] = mapped_column(Integer, nullable=True)
    status: Mapped[str] = mapped_column(String(16), server_default="active")
