"""Pydantic surfaces for Phase 9.1 Performance Intelligence.

Three contracts:

  1. Ingest    — what we accept from the CSV upload endpoint.
  2. Diagnose  — Constitution-shaped recommendation card.
  3. Overview  — the founder-facing payload (cards + summary).

Constitution enforcement is on the response models. Every diagnostic
that ships to the frontend MUST have all four contract fields
(recommendation + reason + confidence + expected_result) and they
must be non-empty. Pydantic's `min_length=3` is the gate.
"""

from __future__ import annotations

import uuid
from datetime import date, datetime
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field

# ---------------------------------------------------------------------
#  Shared enums — keep in lock-step with:
#    apps/api/alembic/versions/0020_performance_intelligence.py
#    apps/web/src/lib/performance-translator.ts
# ---------------------------------------------------------------------

ImpactCategory = Literal["revenue", "lead", "customer", "time", "cost"]
DiagnosticKind = Literal[
    # 9.1 baseline
    "winner",
    "loser",
    "fatigue",
    "audience_shift",
    "budget_reallocation",
    # 9.1.5 — Performance Marketer Brain (keep in lock-step with
    # apps/api/alembic/versions/0021_performance_intelligence_kinds.py
    # and apps/web/src/lib/api.ts)
    "audience_winner",
    "audience_loser",
    "concept_winner",
    "emotion_winner",
    "funnel_winner",
    "pattern_winner",
    "offer_winner",
    "offer_pricing_sensitivity",
    "scale_candidate",
    "budget_waste",
    "creative_dna",
]
DiagnosticStatus = Literal["open", "acted_on", "dismissed", "expired"]
FunnelStage = Literal["awareness", "consideration", "conversion", "retention"]
OfferType = Literal[
    "discount",
    "free_trial",
    "consultation",
    "bundle",
    "promotion",
    "seasonal",
    "none",
]
Platform = Literal[
    "meta", "google", "linkedin", "tiktok", "youtube", "other"
]


# ---------------------------------------------------------------------
#  Ingest path
# ---------------------------------------------------------------------


class CsvIngestRow(BaseModel):
    """One parsed CSV row, after header normalisation + type coercion.

    All fields are required at the row level. The parser converts
    empty cells to 0 for numeric columns and rejects the row if a
    required field is structurally missing.
    """

    model_config = ConfigDict(extra="forbid")

    event_date: date
    creative_ref: str = Field(min_length=1, max_length=255)
    platform: Platform = "meta"
    impressions: int = Field(ge=0)
    clicks: int = Field(ge=0)
    spend_micros: int = Field(ge=0)
    conversions: int = Field(ge=0, default=0)
    conversion_value_micros: int = Field(ge=0, default=0)
    currency: str = Field(min_length=3, max_length=3)


class CsvParseError(BaseModel):
    """A single row that failed to parse — surfaced so the founder
    can fix the file rather than having the whole upload error."""

    row_number: int
    raw: dict[str, str]
    error: str


class CsvIngestSummary(BaseModel):
    """What we tell the founder after a successful upload."""

    upload_id: uuid.UUID
    rows_accepted: int
    rows_rejected: int
    creatives_matched: int
    creatives_unmatched: int
    date_range: tuple[date, date] | None
    currency: str | None
    errors: list[CsvParseError] = Field(default_factory=list)


# ---------------------------------------------------------------------
#  Diagnostic / recommendation cards
# ---------------------------------------------------------------------


class PerformanceDiagnosticCard(BaseModel):
    """Constitution-shaped diagnosis card sent to the dashboard.

    Mirrors the frontend `<AiRecommendation>` props shape but with
    server-controlled fields (id, kind, status, evidence).
    """

    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    kind: DiagnosticKind
    impact_category: ImpactCategory
    what_happened: str = Field(min_length=3)
    why: str = Field(min_length=3)
    recommendation: str = Field(min_length=3)
    expected_result: str = Field(min_length=3)
    reason: str = Field(min_length=3)
    confidence: int = Field(ge=0, le=100)
    evidence: dict
    status: DiagnosticStatus
    created_at: datetime


class PerformanceOverview(BaseModel):
    """The founder-facing payload — one summary, N diagnostic cards.

    Caller (the dashboard) renders each diagnostic through the
    existing `<AiRecommendation>` component. The summary is a single
    line for the hero card; when no cards are ready, the dashboard
    surfaces a ComingSoonCard instead.
    """

    has_data: bool
    rows_ingested: int
    creatives_tracked: int
    last_upload_at: datetime | None
    diagnostics: list[PerformanceDiagnosticCard]


# ---------------------------------------------------------------------
#  Diagnostic-engine internal shapes — used by service + tests
# ---------------------------------------------------------------------


class CreativeRollup(BaseModel):
    """Pure-Python projection of a `creative_results` row.

    The diagnostics engine and the recommender both work off this
    shape so they can be unit-tested without touching the DB.
    """

    model_config = ConfigDict(frozen=True)

    creative_ref: str
    platform: Platform
    matched_asset_type: str | None
    matched_asset_id: uuid.UUID | None
    concept_family: str | None
    emotion: str | None
    audience: str | None
    funnel_stage: FunnelStage | None
    business_goal: str | None
    offer_type: OfferType | None
    impressions: int
    clicks: int
    conversions: int
    spend_micros: int
    conversion_value_micros: int
    currency: str
    first_seen: date
    last_seen: date
    sample_state: Literal["sufficient", "insufficient"]

    # Derived metrics — computed properties keep the source-of-truth
    # in the integer micros columns.
    @property
    def spend(self) -> float:
        return self.spend_micros / 1_000_000

    @property
    def conversion_value(self) -> float:
        return self.conversion_value_micros / 1_000_000

    @property
    def ctr(self) -> float:
        return self.clicks / self.impressions if self.impressions else 0.0

    @property
    def cvr(self) -> float:
        return self.conversions / self.clicks if self.clicks else 0.0

    @property
    def cpl(self) -> float | None:
        """Cost per lead — None when no conversions (avoid 1/0 noise)."""
        if self.conversions == 0:
            return None
        return self.spend / self.conversions

    @property
    def roas(self) -> float | None:
        """Return on ad spend. None when no spend or no conv value."""
        if self.spend == 0 or self.conversion_value == 0:
            return None
        return self.conversion_value / self.spend


class DiagnosticDraft(BaseModel):
    """What `diagnostics.diagnose()` emits, before the recommender
    rewrites into Constitution language and the service persists."""

    kind: DiagnosticKind
    impact_category: ImpactCategory
    confidence: int = Field(ge=0, le=100)
    subject_creative_ref: str
    evidence: dict
