"""Marketing-strategy schemas.

`MarketingStrategy` is BOTH the LLM structured-output schema and the persisted
payload (stored as JSONB on `marketing_strategies.strategy`). Every pillar
carries a `why` (reasoning grounded in the profile) — the Constitution's
"explain WHY / cite the source" rule. The top-level recommendation carries the
full recommendation contract. No numeric metrics are invented.
"""

from __future__ import annotations

import uuid
from datetime import datetime
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field

Priority = Literal["high", "medium", "low"]


class StrategyPillar(BaseModel):
    """One channel / strategy area (content, SEO, ads, email, …)."""

    focus: str = Field(description="The single strategic focus for this channel, plain language.")
    why: str = Field(description="Why this fits THIS business right now — cite profile facts (industry, audience, stage, budget). No fabricated numbers.")
    actions: list[str] = Field(description="2-5 concrete, verb-led tactics. Specific, not generic.")
    priority: Priority = Field(description="How much effort to put here first, given stage + budget.")


class FunnelStage(BaseModel):
    """One stage of the customer journey."""

    stage: Literal["awareness", "interest", "consideration", "conversion", "retention"]
    goal: str = Field(description="What this stage must achieve, in plain language.")
    tactics: list[str] = Field(description="1-4 concrete tactics that move people to the next stage.")


class PlanPeriod(BaseModel):
    """A time-boxed plan (this week / this month / this quarter)."""

    period: str = Field(description="Human label, e.g. 'This week', 'Month 1', 'Q1'.")
    focus: str = Field(description="The one thing to get right in this period.")
    milestones: list[str] = Field(description="3-6 concrete milestones/tasks. Each is a doable action.")


class MarketingStrategy(BaseModel):
    """The full multi-channel marketing strategy for a business."""

    positioning: str = Field(description="One-paragraph positioning: what this business is, for whom, and why it wins.")
    target_summary: str = Field(description="Who to focus on and why now — grounded in the profile's audience.")

    # ---- Channel / strategy pillars (the 13 dimensions, structured) ----
    content: StrategyPillar
    seo: StrategyPillar
    local_seo: StrategyPillar
    paid_ads: StrategyPillar
    organic_social: StrategyPillar
    email: StrategyPillar
    influencer: StrategyPillar

    customer_funnel: list[FunnelStage] = Field(description="The customer journey, awareness → retention.")
    campaign_roadmap: list[str] = Field(description="3-6 campaigns in the sequence to run them, each one line.")

    weekly_plan: PlanPeriod
    monthly_plan: PlanPeriod
    quarterly_plan: PlanPeriod

    # ---- Constitution recommendation contract (the single top move) ----
    recommendation: str = Field(description="The single highest-leverage move to start with.")
    reason: str = Field(max_length=200, description="One line: what this draws on.")
    confidence: int = Field(ge=0, le=100)
    expected_result: str = Field(description="Plain-language outcome, always a range — never a single magic number.")


# ---------- API request/response ----------

StrategyStatus = Literal["pending", "completed", "failed"]


class MarketingStrategyResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    status: StrategyStatus
    strategy: MarketingStrategy | None
    error: str | None
    created_at: datetime
    updated_at: datetime


class MarketingStrategyList(BaseModel):
    items: list[MarketingStrategyResponse]
