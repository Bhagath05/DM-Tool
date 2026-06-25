from __future__ import annotations

import uuid

from sqlalchemy import Boolean, ForeignKey, String
from sqlalchemy.dialects.postgresql import JSONB, UUID
from sqlalchemy.orm import Mapped, mapped_column

from aicmo.db.base import Base, TenantMixin, TimestampMixin


class GeneratedAd(Base, TimestampMixin, TenantMixin):
    """One row per ad generation.

    `strategy`, `targeting`, and `output` are stored as three separate JSONB
    columns rather than one blob — the frontend renders them in distinct
    cards and analytics queries (later) will want to slice on targeting.
    """

    __tablename__ = "generated_ads"

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

    # ad_type is the granular product (meta|google_search|instagram_promo|linkedin).
    # platform is derived from ad_type but stored so future SQL filters can index it.
    ad_type: Mapped[str] = mapped_column(String(32))
    platform: Mapped[str] = mapped_column(String(64))

    objective: Mapped[str] = mapped_column(String(32))  # awareness|traffic|...
    goal: Mapped[str] = mapped_column(String(255))      # free-text campaign goal
    tone: Mapped[str] = mapped_column(String(64))

    strategy: Mapped[dict] = mapped_column(JSONB)   # AdStrategy
    targeting: Mapped[dict] = mapped_column(JSONB)  # AdTargeting
    output: Mapped[dict] = mapped_column(JSONB)     # per-ad-type schema

    # Phase 9.1 — Performance Intelligence tags. See generated_visuals
    # for the rationale; same columns, same nullable contract.
    concept_family: Mapped[str | None] = mapped_column(String(64), nullable=True)
    emotion: Mapped[str | None] = mapped_column(String(64), nullable=True)
    audience: Mapped[str | None] = mapped_column(String(96), nullable=True)
    funnel_stage: Mapped[str | None] = mapped_column(String(32), nullable=True)
    business_goal: Mapped[str | None] = mapped_column(String(96), nullable=True)
    offer_type: Mapped[str | None] = mapped_column(String(32), nullable=True)

    is_saved: Mapped[bool] = mapped_column(Boolean, default=False, server_default="false")

    # Auto-rendered companion image (Phase 1 — generate → PNG).
    rendered_visual_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("rendered_visuals.id", ondelete="SET NULL"),
        nullable=True,
        index=True,
    )
