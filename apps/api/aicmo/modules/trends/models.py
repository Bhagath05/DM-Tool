from __future__ import annotations

import uuid

from sqlalchemy import String, Text
from sqlalchemy.dialects.postgresql import JSONB, UUID
from sqlalchemy.orm import Mapped, mapped_column

from aicmo.db.base import Base, TenantMixin, TimestampMixin


class TrendReport(Base, TimestampMixin, TenantMixin):
    """One latest trend report per user. Overwritten on refresh.

    History isn't an MVP requirement; storing every snapshot would balloon
    the JSONB column for no immediate user value.
    """

    __tablename__ = "trend_reports"

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, default=uuid.uuid4
    )
    user_id: Mapped[str] = mapped_column(String(255), unique=True, index=True)

    status: Mapped[str] = mapped_column(String(16), default="pending")

    # Raw collector output (pytrends + reddit). Persisted so the analyzer
    # is deterministic given a row, and for debugging.
    raw_trends: Mapped[dict | None] = mapped_column(JSONB, nullable=True)

    # AI-generated structured analysis. Schema = TrendAnalysis.
    analysis: Mapped[dict | None] = mapped_column(JSONB, nullable=True)
    analysis_error: Mapped[str | None] = mapped_column(Text, nullable=True)
