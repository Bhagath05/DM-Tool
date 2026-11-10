"""CS-1 generation jobs. One row per Auto, Manual, or Compare request."""

from __future__ import annotations

import uuid
from typing import Any

from sqlalchemy import Integer, String, Text
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.dialects.postgresql import UUID as PGUUID
from sqlalchemy.orm import Mapped, mapped_column

from aicmo.db.base import Base, TenantMixin, TimestampMixin


class CreativeGenerationJob(Base, TimestampMixin, TenantMixin):
    __tablename__ = "creative_generation_job"

    id: Mapped[uuid.UUID] = mapped_column(PGUUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    user_id: Mapped[str | None] = mapped_column(String(255), nullable=True)
    mode: Mapped[str] = mapped_column(String(16))
    task: Mapped[str] = mapped_column(String(32))
    status: Mapped[str] = mapped_column(String(16), server_default="pending")
    prompt: Mapped[str] = mapped_column(Text)
    params: Mapped[dict[str, Any]] = mapped_column(JSONB, server_default="{}")
    explanation: Mapped[str | None] = mapped_column(Text, nullable=True)
    results: Mapped[list[Any]] = mapped_column(JSONB, server_default="[]")
    error_message: Mapped[str | None] = mapped_column(Text, nullable=True)
    attempt_count: Mapped[int] = mapped_column(Integer, server_default="0")
