from __future__ import annotations

import uuid

from sqlalchemy import Boolean, ForeignKey, String
from sqlalchemy.dialects.postgresql import JSONB, UUID
from sqlalchemy.orm import Mapped, mapped_column

from aicmo.db.base import Base, TenantMixin, TimestampMixin


class GeneratedVisual(Base, TimestampMixin, TenantMixin):
    """One row per visual brief generation.

    Stored as `strategy` + `output` JSONB pair — same shape as content/ads —
    so future analytics can group by visual_type/platform without parsing
    the output blob.
    """

    __tablename__ = "generated_visuals"

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

    visual_type: Mapped[str] = mapped_column(String(32))   # ad_creative|carousel|reel|thumbnail
    platform: Mapped[str] = mapped_column(String(64))
    goal: Mapped[str] = mapped_column(String(255))
    tone: Mapped[str] = mapped_column(String(64))

    strategy: Mapped[dict] = mapped_column(JSONB)  # VisualStrategy
    output: Mapped[dict] = mapped_column(JSONB)    # per-type fields

    # Phase 9.1 — Performance Intelligence tags. Nullable so existing
    # rows stay valid; new generations populate them at creation time
    # via `_resolve_creative_tags()` in service.py. Used by the
    # creative_results rollup to attribute outcomes back to tag
    # combinations (concept_family × audience × offer_type, etc.).
    concept_family: Mapped[str | None] = mapped_column(String(64), nullable=True)
    emotion: Mapped[str | None] = mapped_column(String(64), nullable=True)
    audience: Mapped[str | None] = mapped_column(String(96), nullable=True)
    funnel_stage: Mapped[str | None] = mapped_column(String(32), nullable=True)
    business_goal: Mapped[str | None] = mapped_column(String(96), nullable=True)
    offer_type: Mapped[str | None] = mapped_column(String(32), nullable=True)

    is_saved: Mapped[bool] = mapped_column(Boolean, default=False, server_default="false")
