"""ORM for Phase 9.1 Performance Intelligence — CSV-only wedge.

Three tables, all brand-scoped via TenantMixin:

  - PerformanceEvent       raw row from a CSV upload (one per ad/day)
  - CreativeResult         per-creative rollup cube
  - PerformanceDiagnostic  Constitution-shaped diagnosis + recommendation

We deliberately do NOT FK PerformanceEvent.matched_asset_id to the
creative tables. The match is best-effort fuzzy text and we want
ingest to succeed even if the founder later deletes the matched
creative — the row's `creative_ref` (the CSV's own name) is the
durable identity.
"""

from __future__ import annotations

import uuid
from datetime import date, datetime

from sqlalchemy import BigInteger, Date, DateTime, Integer, String, Text, func
from sqlalchemy.dialects.postgresql import JSONB, UUID
from sqlalchemy.orm import Mapped, mapped_column

from aicmo.db.base import Base, TenantMixin


class PerformanceEvent(Base, TenantMixin):
    """One row per (creative, day) ingested from a CSV upload."""

    __tablename__ = "performance_events"

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, default=uuid.uuid4
    )
    # Groups all rows from a single CSV upload. Used for "undo last
    # upload" and audit; never exposed in the founder UI.
    upload_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), nullable=False, index=True
    )
    event_date: Mapped[date] = mapped_column(Date, nullable=False)
    platform: Mapped[str] = mapped_column(String(32), nullable=False)
    creative_ref: Mapped[str] = mapped_column(String(255), nullable=False)

    # When fuzzy-match to one of our generated creatives succeeds, the
    # rollup gets to read tags. NULL = ingested but unmatched.
    matched_asset_type: Mapped[str | None] = mapped_column(
        String(16), nullable=True
    )
    matched_asset_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), nullable=True
    )

    impressions: Mapped[int] = mapped_column(
        BigInteger, nullable=False, default=0
    )
    clicks: Mapped[int] = mapped_column(BigInteger, nullable=False, default=0)
    conversions: Mapped[int] = mapped_column(
        BigInteger, nullable=False, default=0
    )
    # Money: integer micros (× 1_000_000) — never float. Currency
    # captured per row because a brand can ingest exports from
    # accounts in different currencies.
    spend_micros: Mapped[int] = mapped_column(
        BigInteger, nullable=False, default=0
    )
    conversion_value_micros: Mapped[int] = mapped_column(
        BigInteger, nullable=False, default=0
    )
    currency: Mapped[str] = mapped_column(String(3), nullable=False)

    source_filename: Mapped[str | None] = mapped_column(
        String(255), nullable=True
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )


class CreativeResult(Base, TenantMixin):
    """Pre-aggregated cube — one row per (brand, creative_ref).

    Refreshed by `service.recompute_rollups()` after every ingest.
    The diagnostic engine reads ONLY from this table (never from raw
    events) so its inputs are stable and pre-tagged.
    """

    __tablename__ = "creative_results"

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, default=uuid.uuid4
    )
    creative_ref: Mapped[str] = mapped_column(String(255), nullable=False)
    platform: Mapped[str] = mapped_column(String(32), nullable=False)

    matched_asset_type: Mapped[str | None] = mapped_column(
        String(16), nullable=True
    )
    matched_asset_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), nullable=True
    )

    # Tag snapshot at rollup time (denormalised from matched asset).
    concept_family: Mapped[str | None] = mapped_column(String(64), nullable=True)
    emotion: Mapped[str | None] = mapped_column(String(64), nullable=True)
    audience: Mapped[str | None] = mapped_column(String(96), nullable=True)
    funnel_stage: Mapped[str | None] = mapped_column(String(32), nullable=True)
    business_goal: Mapped[str | None] = mapped_column(String(96), nullable=True)
    offer_type: Mapped[str | None] = mapped_column(String(32), nullable=True)

    impressions: Mapped[int] = mapped_column(BigInteger, nullable=False, default=0)
    clicks: Mapped[int] = mapped_column(BigInteger, nullable=False, default=0)
    conversions: Mapped[int] = mapped_column(BigInteger, nullable=False, default=0)
    spend_micros: Mapped[int] = mapped_column(
        BigInteger, nullable=False, default=0
    )
    conversion_value_micros: Mapped[int] = mapped_column(
        BigInteger, nullable=False, default=0
    )
    currency: Mapped[str] = mapped_column(String(3), nullable=False)
    first_seen: Mapped[date] = mapped_column(Date, nullable=False)
    last_seen: Mapped[date] = mapped_column(Date, nullable=False)

    # "sufficient" iff minimum-sample thresholds are met. Set by the
    # rollup writer using the same thresholds the diagnostics engine
    # uses, so the engine never re-checks.
    sample_state: Mapped[str] = mapped_column(
        String(16), nullable=False, default="insufficient"
    )

    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=func.now(),
        onupdate=func.now(),
        nullable=False,
    )


class PerformanceDiagnostic(Base, TenantMixin):
    """A Constitution-shaped diagnosis + recommendation card.

    Every field that the AiRecommendation contract requires is NOT NULL
    at the column level. Pydantic enforces it again at the API edge.
    """

    __tablename__ = "performance_diagnostics"

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, default=uuid.uuid4
    )
    kind: Mapped[str] = mapped_column(String(32), nullable=False)
    impact_category: Mapped[str] = mapped_column(String(16), nullable=False)
    what_happened: Mapped[str] = mapped_column(Text, nullable=False)
    why: Mapped[str] = mapped_column(Text, nullable=False)
    recommendation: Mapped[str] = mapped_column(Text, nullable=False)
    expected_result: Mapped[str] = mapped_column(Text, nullable=False)
    reason: Mapped[str] = mapped_column(Text, nullable=False)
    confidence: Mapped[int] = mapped_column(Integer, nullable=False)
    evidence: Mapped[dict] = mapped_column(
        JSONB, nullable=False, default=dict
    )
    status: Mapped[str] = mapped_column(
        String(16), nullable=False, default="open"
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )
    resolved_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
