"""Pydantic I/O for the marketing-analytics surface.

The :class:`Insight` model carries BOTH the Phase-3 evidence model (observation
→ evidence → interpretation → recommendation → confidence → window) AND the
product Constitution's recommendation contract (recommendation / reason /
confidence / expected_result / impact_category). One model, both contracts.
"""

from __future__ import annotations

from datetime import date
from typing import Literal

from pydantic import BaseModel, Field

Trend = Literal["up", "down", "flat", "insufficient"]
Severity = Literal["good", "attention", "neutral"]
ImpactCategory = Literal["revenue", "lead", "customer", "time", "cost"]
ConfidenceBand = Literal["high", "medium", "low", "speculative"]


# ---------------- evidence + insight ----------------


class MetricEvidence(BaseModel):
    """A single computed data point backing an insight. The analytics service
    fills these in — the LLM may explain them but may never invent them."""

    metric: str  # canonical family id
    label: str
    provider: str | None = None
    platform: str | None = None
    current: float | None = None
    previous: float | None = None
    absolute_change: float | None = None
    change_percent: float | None = None
    window: str  # e.g. "7d", "28d"


class Insight(BaseModel):
    """One evidence-grounded finding from the Performance Marketer."""

    id: str
    severity: Severity
    observation: str
    evidence: list[MetricEvidence]
    interpretation: str
    recommendation: str
    reason: str  # <=140 chars — what data this drew on
    confidence: int = Field(ge=0, le=100)
    confidence_band: ConfidenceBand
    expected_result: str
    impact_category: ImpactCategory = "lead"
    window: str
    # Phase 6 — when set, this insight is executable: it deep-links into a
    # generator (Creative Studio) pre-filled to "repeat the winning format".
    # Shape matches opportunities.GeneratorHint (target/format/platform/goal).
    generator_hint: dict | None = None


# ---------------- platform + comparison ----------------


class PlatformMetric(BaseModel):
    metric: str
    label: str
    kind: str
    value: float
    unit: str
    comparable: bool
    trend: Trend
    change_percent: float | None = None
    window: str


class PlatformSummary(BaseModel):
    provider_slug: str
    platform: str
    metrics: list[PlatformMetric]
    has_data: bool


class CrossPlatformEntry(BaseModel):
    provider_slug: str
    platform: str
    value: float
    change_percent: float | None = None
    trend: Trend


class CrossPlatformRow(BaseModel):
    """One canonical metric compared across the platforms that report it.

    Only semantically comparable metrics appear here — e.g. audience size across
    platforms, never YouTube lifetime views vs Instagram reach."""

    metric: str
    label: str
    kind: str
    unit: str
    entries: list[CrossPlatformEntry]
    leader_provider: str | None = None
    leader_platform: str | None = None


# ---------------- sufficiency ----------------


class DataSufficiency(BaseModel):
    level: str
    days_covered: int
    observations: int
    message: str


# ---------------- trends ----------------


class TrendPoint(BaseModel):
    bucket: date
    value: float


class PeriodComparison(BaseModel):
    current: float | None = None
    previous: float | None = None
    absolute_change: float | None = None
    change_percent: float | None = None
    trend: Trend
    window_days: int


class MetricTrend(BaseModel):
    provider_slug: str
    platform: str
    metric: str
    label: str
    kind: str
    granularity: str
    points: list[TrendPoint]
    comparison: PeriodComparison


# ---------------- endpoint responses ----------------


class PlatformsResponse(BaseModel):
    platforms: list[PlatformSummary]
    comparison: list[CrossPlatformRow]
    sufficiency: DataSufficiency
    last_sync_at: str | None = None
    has_data: bool


class TrendsResponse(BaseModel):
    trends: list[MetricTrend]
    sufficiency: DataSufficiency
    window_days: int
    granularity: str
    has_data: bool


class InsightsResponse(BaseModel):
    insights: list[Insight]
    sufficiency: DataSufficiency
    has_data: bool


class PerformanceMarketerReport(BaseModel):
    headline: str
    sufficiency: DataSufficiency
    whats_working: list[Insight]
    whats_not_working: list[Insight]
    recommendations: list[Insight]
    platform_comparison: list[CrossPlatformRow]
    narrated: bool
    has_data: bool
    generated_at: str


# ---------------- advisor integration signal (Phase 4) ----------------


class AdvisorPlatformEvidence(BaseModel):
    """One platform's computed metric evidence, compact form for the advisor."""

    provider_slug: str
    platform: str
    metrics: list[MetricEvidence]


EmptyReason = Literal["no_connection", "no_metrics", "short_history"]


# ---------------- per-content performance (Phase 5) ----------------


class ContentPerformanceItem(BaseModel):
    """One published post with its latest computed metrics. Values are the real
    numbers from PerformanceSignal; `available_metrics` says which the provider
    actually reported so the UI never presents an unavailable metric as a 0."""

    asset_id: str
    platform: str
    platform_label: str
    provider_slug: str | None = None
    platform_post_id: str
    asset_type: str
    caption: str | None = None
    permalink: str | None = None
    thumbnail_url: str | None = None
    posted_at: str | None = None
    engagement_rate: float
    reach: int
    impressions: int
    views: int
    likes: int
    comments: int
    shares: int
    saves: int
    available_metrics: list[str]
    above_median: bool


class FormatComparisonRow(BaseModel):
    asset_type: str
    count: int
    median_engagement_rate: float
    avg_reach: float | None = None
    avg_views: float | None = None


class RecommendationEffectiveness(BaseModel):
    """Honest comparison of recommendation-driven content vs the rest. Reports
    what the data shows; it never claims the AI *caused* an improvement."""

    has_data: bool
    recommendation_driven_count: int
    other_count: int
    recommendation_median_engagement: float | None = None
    other_median_engagement: float | None = None
    # rec median vs the overall median, in %, when both are computable.
    vs_overall_percent: float | None = None
    summary: str


class ContentPerformanceReport(BaseModel):
    has_data: bool
    sufficiency: DataSufficiency
    window: str
    median_engagement_rate: float | None = None
    top: list[ContentPerformanceItem] = Field(default_factory=list)
    worst: list[ContentPerformanceItem] = Field(default_factory=list)
    format_comparison: list[FormatComparisonRow] = Field(default_factory=list)
    insights: list[Insight] = Field(default_factory=list)
    recommendation_effectiveness: RecommendationEffectiveness | None = None
    generated_at: str


class AdvisorAnalyticsSignal(BaseModel):
    """Read-only, one-directional feed from marketing analytics → the advisor.

    Contains COMPUTED values only. The advisor/LLM may explain these numbers but
    must never alter or invent them. This is the single object the advisor's
    signal gatherer consumes and the AI Coach UI renders.
    """

    source: Literal["marketing_analytics"] = "marketing_analytics"
    has_data: bool
    connected: bool
    data_sufficiency: str  # none | single_day | short_term | weekly | strong
    window: str
    headline: str
    empty_reason: EmptyReason | None = None
    empty_message: str | None = None
    platforms: list[AdvisorPlatformEvidence] = Field(default_factory=list)
    insights: list[Insight] = Field(default_factory=list)
    evidence: list[MetricEvidence] = Field(default_factory=list)
    confidence_band: ConfidenceBand = "speculative"
    last_sync_at: str | None = None
    # Phase 5 — per-content evidence: insights that reference specific posts, and
    # the top content items, so the advisor can say "your last 3 reels beat your
    # recent median" (computed, never invented).
    content_insights: list[Insight] = Field(default_factory=list)
    top_content: list[ContentPerformanceItem] = Field(default_factory=list)
