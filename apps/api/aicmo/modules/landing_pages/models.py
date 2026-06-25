from __future__ import annotations

import uuid

from sqlalchemy import Boolean, ForeignKey, Integer, String
from sqlalchemy.dialects.postgresql import JSONB, UUID
from sqlalchemy.orm import Mapped, mapped_column

from aicmo.db.base import Base, TenantMixin, TimestampMixin


class LandingPage(Base, TimestampMixin, TenantMixin):
    """A single-purpose conversion page.

    `content` is a JSONB blob mirroring the on-page structure (headline,
    benefits, CTA, social proof, FAQ, form config). Renderer-agnostic —
    today the Next.js dynamic route consumes it, tomorrow a static export
    or an embed code can read the same shape.

    Why JSONB and not a relational tree (sections / benefits / faqs as
    rows): the renderer is the only consumer, the data is always read
    whole, the schema evolves with the product. JSONB gives us schema
    flexibility + indexable fields if we need them later.
    """

    __tablename__ = "landing_pages"

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, default=uuid.uuid4
    )
    user_id: Mapped[str] = mapped_column(String(255), index=True)
    business_profile_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("business_profiles.id", ondelete="CASCADE"),
        index=True,
    )

    # URL slug. Globally unique because `/p/{slug}` is a flat namespace.
    slug: Mapped[str] = mapped_column(String(80), unique=True, index=True)
    title: Mapped[str] = mapped_column(String(255))

    # draft | published — drafts return 404 to anonymous traffic.
    status: Mapped[str] = mapped_column(String(16), default="draft", server_default="draft")

    # Random token allowing draft previews via /p/{slug}?preview={token}
    preview_token: Mapped[str] = mapped_column(String(64))

    content: Mapped[dict] = mapped_column(JSONB)

    # Optional post-submit redirect. None → render "Thanks!" inline.
    redirect_url: Mapped[str | None] = mapped_column(String(512), nullable=True)

    # Denormalized counters for fast inbox/listing display. Acceptable
    # to be slightly stale; analytics can recompute from leads table.
    view_count: Mapped[int] = mapped_column(Integer, default=0, server_default="0")
    submission_count: Mapped[int] = mapped_column(Integer, default=0, server_default="0")

    is_archived: Mapped[bool] = mapped_column(
        Boolean, default=False, server_default="false"
    )
