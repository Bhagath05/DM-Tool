"""AI Sales Assistant ORM (Phase 6.5, Slice 5).

One tenant-scoped `crm_ai_insights` cache. Every row IS the evidence contract:
summary + recommendation + evidence + reasoning + confidence + affected_records
+ expected_outcome + generated_at + expires_at. `insufficient_evidence=True`
rows record the honest "Not enough evidence." verdict (no LLM was called). The
polymorphic (subject_type, subject_id) pointer reuses the existing CRM rows —
no data is duplicated.
"""

from __future__ import annotations

import uuid
from datetime import datetime
from typing import Any

from sqlalchemy import Boolean, DateTime, Integer, String, Text, func
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.dialects.postgresql import UUID as PgUUID
from sqlalchemy.orm import Mapped, mapped_column

from aicmo.db.base import Base, TenantMixin


class AIInsight(Base, TenantMixin):
    __tablename__ = "crm_ai_insights"

    id: Mapped[uuid.UUID] = mapped_column(PgUUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    # lead | deal | contact | company | task | email
    subject_type: Mapped[str] = mapped_column(String(16), index=True)
    subject_id: Mapped[uuid.UUID] = mapped_column(PgUUID(as_uuid=True), index=True)
    kind: Mapped[str] = mapped_column(String(40), index=True)
    summary: Mapped[str | None] = mapped_column(Text, nullable=True)
    recommendation: Mapped[str | None] = mapped_column(Text, nullable=True)
    evidence: Mapped[list[Any]] = mapped_column(JSONB, server_default="[]")
    reasoning: Mapped[str | None] = mapped_column(Text, nullable=True)
    confidence: Mapped[int] = mapped_column(Integer, server_default="0")
    affected_records: Mapped[list[Any]] = mapped_column(JSONB, server_default="[]")
    expected_outcome: Mapped[str | None] = mapped_column(Text, nullable=True)
    insufficient_evidence: Mapped[bool] = mapped_column(Boolean, server_default="false", index=True)
    model: Mapped[str | None] = mapped_column(String(64), nullable=True)
    generated_by_user_id: Mapped[str | None] = mapped_column(String(255), nullable=True)
    generated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    expires_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True, index=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
