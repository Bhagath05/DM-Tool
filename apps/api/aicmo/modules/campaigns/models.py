from __future__ import annotations

import uuid

from sqlalchemy import Boolean, ForeignKey, Integer, String
from sqlalchemy.dialects.postgresql import JSONB, UUID
from sqlalchemy.orm import Mapped, mapped_column

from aicmo.db.base import Base, TenantMixin, TimestampMixin


class CampaignPlan(Base, TimestampMixin, TenantMixin):
    """One row per generated campaign plan.

    `strategy` holds the envelope (theme + funnel + platforms + visual
    direction + sequence). `calendar` holds the per-day publish slots.
    Splitting them lets future analytics group across plans on either
    dimension without parsing the other blob.
    """

    __tablename__ = "campaign_plans"

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, default=uuid.uuid4
    )
    user_id: Mapped[str] = mapped_column(String(255), index=True)

    business_profile_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("business_profiles.id", ondelete="CASCADE"),
        index=True,
    )
    trend_report_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("trend_reports.id", ondelete="SET NULL"),
        nullable=True,
    )
    landing_page_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("landing_pages.id", ondelete="SET NULL"),
        nullable=True,
        index=True,
    )

    campaign_type: Mapped[str] = mapped_column(String(32))
    duration_days: Mapped[int] = mapped_column(Integer)
    goal: Mapped[str] = mapped_column(String(255))
    tone: Mapped[str] = mapped_column(String(64))

    strategy: Mapped[dict] = mapped_column(JSONB)
    calendar: Mapped[dict] = mapped_column(JSONB)

    is_saved: Mapped[bool] = mapped_column(Boolean, default=False, server_default="false")
