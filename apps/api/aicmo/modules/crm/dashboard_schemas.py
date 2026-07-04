"""Executive CRM Dashboard schemas (Phase 6.5, Slice 6).

A read-only aggregation layer — every number is composed from the EXISTING CRM /
email / activity / insight data. Nulls are returned honestly where the data
doesn't exist (never fabricated).
"""

from __future__ import annotations

import uuid
from datetime import datetime

from pydantic import BaseModel

from aicmo.modules.crm.assistant_schemas import InsightResponse
from aicmo.modules.crm.schemas import PipelineAnalytics


class ExecutiveKPIs(BaseModel):
    total_leads: int
    qualified_leads: int          # leads in the hot/warm buckets (this taxonomy has no "qualified" status)
    active_opportunities: int     # open deals
    won_deals: int
    lost_deals: int
    revenue: float                # Σ won value
    pipeline_value: float         # Σ open value
    avg_deal_size: float
    win_rate: float
    conversion_rate: float
    sales_velocity: float         # (open_deals × avg_deal_size × win_rate) / avg_cycle_days
    avg_sales_cycle_days: float | None
    lead_response_time_hours: float | None
    email_open_rate: float
    email_reply_rate: float
    meetings_completed: int
    tasks_completed: int
    follow_up_compliance: float | None  # completed-on-time / total due


class StageFunnel(BaseModel):
    stage_id: uuid.UUID | None
    stage_name: str
    count: int
    value: float
    avg_days_in_stage: float | None


class LostReason(BaseModel):
    reason: str
    count: int


class RiskBand(BaseModel):
    band: str  # high|medium|low
    count: int
    value: float


class StalledDeal(BaseModel):
    id: uuid.UUID
    title: str
    value: float
    days_inactive: int
    owner_user_id: str | None


class PipelineDashboard(BaseModel):
    analytics: PipelineAnalytics       # REUSED from crm.service.analytics
    funnel: list[StageFunnel]
    lost_reasons: list[LostReason]
    risk_distribution: list[RiskBand]
    stalled_deals: list[StalledDeal]


class RepPerformance(BaseModel):
    owner_user_id: str
    revenue: float
    won_deals: int
    open_deals: int
    pipeline_value: float
    win_rate: float
    activities: int
    meetings: int
    calls: int
    emails: int
    tasks_completed: int


class ActivityCounts(BaseModel):
    calls: int
    meetings: int
    emails: int
    notes: int
    tasks_open: int
    tasks_completed: int
    follow_ups_due: int


class ForecastPeriod(BaseModel):
    period: str      # e.g. "2026-07" or "2026-Q3"
    won_revenue: float
    deals: int


class Forecast(BaseModel):
    monthly: list[ForecastPeriod]
    quarterly: list[ForecastPeriod]
    pipeline_weighted_forecast: float   # REUSED weighted forecast
    open_pipeline_value: float


class ExecutiveDashboard(BaseModel):
    kpis: ExecutiveKPIs
    pipeline: PipelineDashboard
    reps: list[RepPerformance]
    activity: ActivityCounts
    forecast: Forecast
    ai_insights: list[InsightResponse]   # REUSED cached AI Assistant insights
    generated_at: datetime
    filters: dict
