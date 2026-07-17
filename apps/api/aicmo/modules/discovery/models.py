from __future__ import annotations

import uuid

from sqlalchemy import String, Text
from sqlalchemy.dialects.postgresql import JSONB, UUID
from sqlalchemy.orm import Mapped, mapped_column

from aicmo.db.base import Base, TenantMixin, TimestampMixin


class WebsiteDiscovery(Base, TenantMixin, TimestampMixin):
    """One AI onboarding-discovery run for a brand.

    Holds the extracted website signals + the AI-proposed Brand Brain draft
    the user reviews before it's applied. Org/brand scoped via TenantMixin;
    a run can happen before a BusinessProfile exists (the whole point).
    """

    __tablename__ = "website_discoveries"

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, default=uuid.uuid4
    )
    created_by_user_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True))

    # 'website' | 'scratch'
    source: Mapped[str] = mapped_column(String(16), default="website")
    url: Mapped[str | None] = mapped_column(String(500), nullable=True)
    business_name: Mapped[str] = mapped_column(String(255), default="")
    industry: Mapped[str | None] = mapped_column(String(128), nullable=True)

    # pending | running | completed | failed
    status: Mapped[str] = mapped_column(
        String(16), default="pending", server_default="pending"
    )
    # Real progress marker the runner advances as it works — drives the
    # discovery timeline. queued | reading | understanding | building | done
    stage: Mapped[str] = mapped_column(
        String(24), default="queued", server_default="queued"
    )
    # Raw extracted signals (website source) — kept for transparency / retry.
    signals: Mapped[dict | None] = mapped_column(JSONB, nullable=True)
    # The AI-proposed Brand Brain draft (DiscoveryDraft shape).
    draft: Mapped[dict | None] = mapped_column(JSONB, nullable=True)
    error: Mapped[str | None] = mapped_column(Text, nullable=True)
    # The seed answers for the 'scratch' source (Option 3).
    seed: Mapped[dict | None] = mapped_column(JSONB, nullable=True)
