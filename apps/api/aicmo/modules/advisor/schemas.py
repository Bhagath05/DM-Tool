"""Advisor API schemas."""

from __future__ import annotations

import uuid
from datetime import datetime
from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field

RecommendationStatus = Literal[
    "not_started", "in_progress", "completed", "skipped"
]

RecordType = Literal[
    "recommendation_created",
    "recommendation_completed",
    "recommendation_skipped",
    "ad_generated",
    "post_generated",
    "reel_generated",
    "campaign_launched",
    "lead_generated",
    "lead_converted",
    "opportunity_closed",
]

ImpactCategory = Literal["revenue", "lead", "customer", "time", "cost"]


class DataSourceRef(BaseModel):
    key: str
    label: str
    value: str


class AdvisorRecommendationResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    record_type: str
    title: str
    description: str
    status: RecommendationStatus
    impact_score: int
    confidence: int
    impact_category: ImpactCategory | None = None
    why: str | None = None
    data_used: list[DataSourceRef] = Field(default_factory=list)
    expected_result: str | None = None
    source_surface: str
    outcome_summary: str | None = None
    repeat_rationale: str | None = None
    created_at: datetime
    updated_at: datetime
    completed_at: datetime | None = None
    skipped_at: datetime | None = None


class AdvisorRecommendationList(BaseModel):
    items: list[AdvisorRecommendationResponse]


class UpdateRecommendationStatusRequest(BaseModel):
    status: RecommendationStatus


class AdvisorHistoryItem(BaseModel):
    id: uuid.UUID
    date: str
    title: str
    description: str
    status: RecommendationStatus
    observation: str | None = None
    root_cause: str | None = None
    recommended_action: str | None = None
    expected_impact: str | None = None
    result_summary: str | None = None
    outcome_status: str | None = None
    effectiveness_score: int | None = None
    learning: str | None = None
    impact_score: int
    impact_label: Literal["High", "Medium", "Low"]
    confidence: int
    why: str | None = None
    data_used: list[DataSourceRef] = Field(default_factory=list)
    expected_result: str | None = None


class AdvisorHistoryList(BaseModel):
    items: list[AdvisorHistoryItem]


class AdvisorReadinessResponse(BaseModel):
    ready: bool
    message: str | None = None
    suggested_setup_steps: list[str] = Field(default_factory=list)
    signal_count: int = 0


class AdvisorEmptyPlan(BaseModel):
    """Returned when insufficient data — no fake recommendations."""

    ready: bool = False
    headline: str
    message: str
    suggested_setup_steps: list[str] = Field(default_factory=list)
    signals_used: list[str] = Field(default_factory=list)
    generated_at: str


# ---------- Intelligence Engine (Phase 7) ----------


class IntelligenceRecommendation(BaseModel):
    """Full 6-field contract for every recommendation."""

    id: uuid.UUID | None = None
    observation: str = Field(min_length=10)
    root_cause: str = Field(min_length=10)
    recommended_action: str = Field(min_length=10)
    expected_impact: str = Field(min_length=10)
    confidence: int = Field(ge=0, le=100)
    data_sources_used: list[DataSourceRef] = Field(min_length=1)
    impact_category: ImpactCategory = "lead"
    generator_hint: dict[str, Any] | None = None
    task_status: RecommendationStatus | None = None
    recommendation_id: uuid.UUID | None = None


class IntelligenceOpportunity(IntelligenceRecommendation):
    """Content or ad opportunity with generator deep-link."""

    kind: Literal["content", "ad"] = "content"
    headline: str = Field(min_length=5)


class DailyBrief(BaseModel):
    """What happened — grounded in real metrics."""

    what_happened: str = Field(min_length=10)
    why_it_happened: str = Field(min_length=10)
    confidence: int = Field(ge=0, le=100)
    data_sources_used: list[DataSourceRef] = Field(default_factory=list)


class IntelligenceReport(BaseModel):
    ready: bool
    empty: AdvisorEmptyPlan | None = None
    hero: IntelligenceRecommendation | None = None
    content_opportunities: list[IntelligenceOpportunity] = Field(default_factory=list)
    ad_opportunities: list[IntelligenceOpportunity] = Field(default_factory=list)
    trend: IntelligenceRecommendation | None = None
    daily_brief: DailyBrief | None = None
    signals_used: list[str] = Field(default_factory=list)
    confidence_cap: int = 55
    generated_at: str


class BusinessBrainResponse(BaseModel):
    industry: str
    business_type: str
    target_audience: str
    monthly_budget: str | None = None
    growth_goal: str | None = None
    location: str | None = None
    competitors: list[str] = Field(default_factory=list)
    completeness_score: int = Field(ge=0, le=7)
    missing_steps: list[str] = Field(default_factory=list)


class BusinessBrainUpdate(BaseModel):
    industry: str | None = None
    business_type: str | None = None
    target_audience: str | None = None
    monthly_budget_band: str | None = None
    primary_goal_text: str | None = None
    business_location: str | None = None
    competitors: list[str] | None = None


class EffectivenessChannel(BaseModel):
    dimension: str
    key: str
    label: str
    success_rate: float | None = None
    avg_effectiveness: int | None = None
    sample_size: int


class EffectivenessResponse(BaseModel):
    channels: list[EffectivenessChannel]


class ExecuteRecommendationRequest(BaseModel):
    recommendation_id: uuid.UUID


class ExecuteRecommendationResponse(BaseModel):
    asset_type: str
    asset_id: uuid.UUID
    content_asset_id: uuid.UUID | None = None
    status: Literal["created", "linked"]
    preview_url: str | None = None


# ---------- Autonomous Agent (Phase 11) ----------


AgentReportType = Literal[
    "daily",
    "weekly",
    "monthly",
    "lead_trends",
    "campaign_performance",
    "budget",
]


class AgentReportSection(BaseModel):
    title: str
    body: str
    confidence: int = Field(ge=0, le=100)


class AgentReportRecommendation(BaseModel):
    observation: str
    root_cause: str
    recommended_action: str
    expected_impact: str
    confidence: int = Field(ge=0, le=100)
    data_sources_used: list[DataSourceRef] = Field(default_factory=list)


class AgentReport(BaseModel):
    report_type: AgentReportType
    ready: bool
    summary: str = ""
    sections: list[AgentReportSection] = Field(default_factory=list)
    recommendations: list[AgentReportRecommendation] = Field(default_factory=list)
    setup_steps: list[str] = Field(default_factory=list)
    confidence: int = Field(ge=0, le=100, default=0)
    data_sources_used: list[DataSourceRef] = Field(default_factory=list)
    period_start: str
    period_end: str
    generated_at: str


# ---------------------------------------------------------------------
#  AI Marketing Health (Phase 8 — the AI headquarters scores)
# ---------------------------------------------------------------------


class HealthScore(BaseModel):
    """One plain-language health score. Carries the full constitution
    contract: what it means, why it matters, and what to do next."""

    key: str
    label: str
    score: int = Field(ge=0, le=100)
    status: Literal["good", "watch", "bad"]
    explanation: str
    why: str
    recommendation: str


class MarketingHealthResponse(BaseModel):
    overall: int = Field(ge=0, le=100)
    overall_status: Literal["good", "watch", "bad"]
    headline: str
    focus_key: str = Field(description="Key of the weakest score — what to fix first.")
    scores: list[HealthScore] = Field(default_factory=list)
