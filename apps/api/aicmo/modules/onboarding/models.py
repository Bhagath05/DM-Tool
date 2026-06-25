from __future__ import annotations

import uuid
from typing import Literal

from sqlalchemy import String, Text
from sqlalchemy.dialects.postgresql import JSONB, UUID
from sqlalchemy.orm import Mapped, mapped_column

from aicmo.db.base import Base, TenantMixin, TimestampMixin

AnalysisStatus = Literal["pending", "completed", "failed"]


class BusinessProfile(Base, TimestampMixin, TenantMixin):
    """One row per Clerk user. The source-of-truth for every downstream
    module (trends, content, ads, analytics)."""

    __tablename__ = "business_profiles"

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, default=uuid.uuid4
    )
    user_id: Mapped[str] = mapped_column(String(255), unique=True, index=True)

    business_name: Mapped[str] = mapped_column(String(255))
    website: Mapped[str | None] = mapped_column(String(512), nullable=True)
    industry: Mapped[str] = mapped_column(String(128))
    business_type: Mapped[str | None] = mapped_column(String(64), nullable=True)
    target_audience: Mapped[str] = mapped_column(Text)
    brand_tone: Mapped[str] = mapped_column(String(64))

    # JSONB string-arrays. Cheaper than separate tables for short lists and
    # the rows here are rarely queried by element.
    competitors: Mapped[list[str]] = mapped_column(JSONB, default=list)
    goals: Mapped[list[str]] = mapped_column(JSONB, default=list)
    preferred_platforms: Mapped[list[str]] = mapped_column(JSONB, default=list)

    # ---- Phase 2.0 conversational-onboarding fields ----
    # All four are nullable for backward compatibility with profiles created
    # via the legacy wizard. The new stepper collects them; downstream
    # modules ignore them today and read them as needed in Phase 2.1+.
    business_location: Mapped[str | None] = mapped_column(
        String(255), nullable=True
    )
    current_monthly_leads_band: Mapped[str | None] = mapped_column(
        String(32), nullable=True
    )
    monthly_budget_band: Mapped[str | None] = mapped_column(
        String(32), nullable=True
    )
    primary_goal_text: Mapped[str | None] = mapped_column(
        String(500), nullable=True
    )

    # ---- Persona segmentation ----
    # NOT an authorization role (those live in member_roles). A free hint
    # about WHO the user is so downstream copy + tutorials can adapt:
    # solo_founder, in_house_marketer, agency, freelancer, consultant, other.
    # CHECK constraint on the DB side enforces the enum (migration 0019).
    persona: Mapped[str | None] = mapped_column(String(32), nullable=True)

    # AI-generated insights. Populated asynchronously after onboarding.
    analysis_status: Mapped[str] = mapped_column(String(16), default="pending")
    analysis: Mapped[dict | None] = mapped_column(JSONB, nullable=True)
    analysis_error: Mapped[str | None] = mapped_column(Text, nullable=True)
