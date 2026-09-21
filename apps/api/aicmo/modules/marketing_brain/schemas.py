"""Structured Marketing Brain context — provenance-aware, kind-explicit.

Evidence kinds stay separated so callers never promote a hypothesis to a fact.
Timestamps and confidence are copied from source rows; never invented.
"""

from __future__ import annotations

import uuid
from datetime import datetime
from typing import Literal

from pydantic import BaseModel, Field

from aicmo.modules.business_brain.schemas import (
    CompetitorCandidate,
    EvidenceItem,
    IcpItem,
    MarketSignal,
    ResearchJobResponse,
)


class MarketingBrainProfileSnapshot(BaseModel):
    """Canonical onboarding profile fields — None means unknown, not fabricated."""

    present: bool
    business_name: str | None = None
    website: str | None = None
    industry: str | None = None
    business_type: str | None = None
    target_audience: str | None = None
    location: str | None = None
    competitors: list[str] = Field(default_factory=list)
    monthly_budget_band: str | None = None
    primary_goal: str | None = None


class MarketingBrainAnalyticsSnapshot(BaseModel):
    """Real analytics KPIs only — zeros are honest absence, not estimates."""

    total_leads: int
    leads_7d: int
    leads_30d: int
    hot_leads: int
    conversion_rate: float
    landing_pages_published: int
    total_views: int
    total_submissions: int


class MarketingBrainRecommendationRef(BaseModel):
    """Advisor recommendation pointer — status preserved; not an execution grant."""

    id: uuid.UUID
    title: str
    status: str
    source_surface: str
    confidence: int
    impact_category: str | None = None
    expected_result: str | None = None
    created_at: datetime
    updated_at: datetime
    completed_at: datetime | None = None
    skipped_at: datetime | None = None
    outcome_summary: str | None = None


class MarketingBrainOutcomeItem(BaseModel):
    title: str
    delta_summary: str | None = None
    effectiveness_score: float | None = None
    source_surface: str | None = None
    kind: Literal["evaluated_success", "failed_or_skipped"] = "evaluated_success"


class MarketingBrainLearningItem(BaseModel):
    """Cross-domain learning insight — distinct from BrainEvidence."""

    id: uuid.UUID
    category: str
    observation: str
    recommendation: str
    expected_result: str
    confidence: int
    direction: str
    status: str
    learned_at: datetime
    expires_at: datetime | None = None
    evidence: list[str] = Field(default_factory=list)


class MarketingBrainResearchSnapshot(BaseModel):
    latest_website_job: ResearchJobResponse | None = None
    latest_competitor_job: ResearchJobResponse | None = None
    latest_market_job: ResearchJobResponse | None = None
    competitor_candidates: list[CompetitorCandidate] = Field(default_factory=list)
    competitor_status: str = "INSUFFICIENT_EVIDENCE"
    competitor_message: str | None = None
    market_signals: list[MarketSignal] = Field(default_factory=list)
    market_status: str = "INSUFFICIENT_EVIDENCE"
    market_message: str | None = None


class MarketingBrainContext(BaseModel):
    """Unified read-only marketing state for one brand.

    Layer separation is intentional:
      facts / observations / hypotheses / evidence_recommendations
      ≠ advisor recommendations ≠ outcomes ≠ learning_insights ≠ ICPs
    """

    brand_id: uuid.UUID
    organization_id: uuid.UUID
    built_at: datetime

    profile: MarketingBrainProfileSnapshot
    known: list[str] = Field(default_factory=list)
    unknown: list[str] = Field(default_factory=list)
    limitations: list[str] = Field(default_factory=list)

    # Business Brain evidence — partitioned by kind (active only).
    facts: list[EvidenceItem] = Field(default_factory=list)
    observations: list[EvidenceItem] = Field(default_factory=list)
    hypotheses: list[EvidenceItem] = Field(default_factory=list)
    evidence_recommendations: list[EvidenceItem] = Field(default_factory=list)
    evidence_counts: dict[str, int] = Field(default_factory=dict)
    # Active list excludes superseded/contradicted; count is informational.
    superseded_excluded_count: int = 0

    icps: list[IcpItem] = Field(default_factory=list)
    icp_status: Literal["ok", "INSUFFICIENT_EVIDENCE"] = "INSUFFICIENT_EVIDENCE"
    icp_message: str | None = None

    research: MarketingBrainResearchSnapshot = Field(default_factory=MarketingBrainResearchSnapshot)

    analytics: MarketingBrainAnalyticsSnapshot | None = None
    recommendations: list[MarketingBrainRecommendationRef] = Field(default_factory=list)
    outcomes: list[MarketingBrainOutcomeItem] = Field(default_factory=list)
    learning_insights: list[MarketingBrainLearningItem] = Field(default_factory=list)
