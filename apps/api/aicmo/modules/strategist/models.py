"""Persisted marketing strategy — one row per generation, newest = current.

Per-brand (TenantMixin → organization_id + brand_id) and versioned (history is
just older rows), so the Planner/Executor read the latest completed strategy
and we keep an audit trail of how the strategy evolved.
"""

from __future__ import annotations

import uuid

from sqlalchemy import String, Text
from sqlalchemy.dialects.postgresql import JSONB, UUID
from sqlalchemy.orm import Mapped, mapped_column

from aicmo.db.base import Base, TenantMixin, TimestampMixin


class MarketingStrategyRecord(Base, TimestampMixin, TenantMixin):
    __tablename__ = "marketing_strategies"

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, default=uuid.uuid4
    )
    user_id: Mapped[str] = mapped_column(String(255), index=True)
    status: Mapped[str] = mapped_column(
        String(16), default="pending", server_default="pending"
    )
    # The MarketingStrategy payload (JSONB); NULL until the async job completes.
    strategy: Mapped[dict | None] = mapped_column(JSONB, nullable=True)
    error: Mapped[str | None] = mapped_column(Text, nullable=True)
    # Phase 7.15 — explainable evidence grounding: which evidence-graded beliefs
    # (from the belief memory) informed this strategy, with confidence; or an
    # INSUFFICIENT_EVIDENCE marker when the brand has no validated beliefs yet.
    # Server-populated from the belief resolver, never by the LLM. NULL for
    # strategies generated before this field existed.
    evidence_grounding: Mapped[dict | None] = mapped_column(JSONB, nullable=True)
