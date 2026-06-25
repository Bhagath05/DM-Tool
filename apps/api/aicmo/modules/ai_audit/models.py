"""AI generation audit trail — ORM model.

One row per AI generation call (success or failure). Distinct from:
- `audit_events` (admin / RBAC mutations).
- `experiments` (learning-lab analytics about prompt variants).

CRITICAL: this table NEVER stores generated content. No captions, no
ad copy, no image URLs, no hooks. Storing it would create a privacy
liability and is explicitly out of scope. The asset_id pointer lets
investigators join back to the canonical asset table when needed.
"""

from __future__ import annotations

import uuid
from datetime import datetime

from sqlalchemy import DateTime, ForeignKey, Integer, String, func
from sqlalchemy.dialects.postgresql import INET, JSONB, UUID
from sqlalchemy.orm import Mapped, mapped_column

from aicmo.db.base import Base


class AiAuditEvent(Base):
    __tablename__ = "ai_audit_events"

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, default=uuid.uuid4
    )
    user_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("users.id", ondelete="SET NULL"),
        nullable=True,
    )
    organization_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("organizations.id", ondelete="CASCADE"),
    )
    brand_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("brands.id", ondelete="SET NULL"),
        nullable=True,
    )
    action_type: Mapped[str] = mapped_column(String(64))
    model_used: Mapped[str | None] = mapped_column(String(128), nullable=True)
    asset_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), nullable=True
    )
    generation_status: Mapped[str] = mapped_column(
        String(32), server_default="success"
    )
    error_class: Mapped[str | None] = mapped_column(String(255), nullable=True)
    duration_ms: Mapped[int | None] = mapped_column(Integer, nullable=True)
    request_id: Mapped[str | None] = mapped_column(String(64), nullable=True)
    prompt_token_count: Mapped[int | None] = mapped_column(Integer, nullable=True)
    completion_token_count: Mapped[int | None] = mapped_column(
        Integer, nullable=True
    )
    ip_address: Mapped[str | None] = mapped_column(INET, nullable=True)
    metadata_json: Mapped[dict] = mapped_column(
        JSONB, default=dict, server_default="{}"
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )
