"""Schemas for the Intelligent Onboarding Website Discovery Engine."""

from __future__ import annotations

import uuid
from datetime import datetime
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field

DiscoveryStatus = Literal["pending", "running", "completed", "failed"]
DiscoverySource = Literal["website", "scratch"]
# Real progress markers the runner advances — the UI timeline reads these
# rather than animating a fake timer.
DiscoveryStage = Literal["queued", "reading", "understanding", "building", "done"]


class DiscoveryDraft(BaseModel):
    """The Brand Brain draft the AI proposes and the user reviews + edits.

    Also the LLM structured-output schema — every field defaults so a
    partial model still validates. Scores are 0-100 confidence-style
    readiness signals, explained in plain language on the review page.
    """

    business_description: str = Field(default="", max_length=2000)
    products: list[str] = Field(default_factory=list)
    services: list[str] = Field(default_factory=list)
    target_audience: str = Field(default="", max_length=2000)
    unique_selling_points: list[str] = Field(default_factory=list)
    competitors: list[str] = Field(default_factory=list)
    brand_tone: str = Field(default="", max_length=120)
    writing_style: str = Field(default="", max_length=2000)
    keywords: list[str] = Field(default_factory=list)
    brand_colors: list[str] = Field(default_factory=list)
    fonts: list[str] = Field(default_factory=list)
    brand_rules: list[str] = Field(default_factory=list)
    goals: list[str] = Field(default_factory=list)

    # Plain-language AI summary + readiness signals for the review page.
    summary: str = Field(default="", max_length=3000)
    content_opportunities: list[str] = Field(default_factory=list)
    marketing_opportunities: list[str] = Field(default_factory=list)
    seo_opportunities: list[str] = Field(default_factory=list)
    brand_completeness_score: int = Field(default=0, ge=0, le=100)
    content_readiness_score: int = Field(default=0, ge=0, le=100)
    advertising_readiness_score: int = Field(default=0, ge=0, le=100)
    seo_readiness_score: int = Field(default=0, ge=0, le=100)


# ---------------------------------------------------------------------
#  Requests
# ---------------------------------------------------------------------


class StartWebsiteDiscovery(BaseModel):
    business_name: str = Field(min_length=1, max_length=255)
    website_url: str = Field(min_length=3, max_length=500)
    industry: str = Field(min_length=2, max_length=128)


class StartScratchDiscovery(BaseModel):
    """Option 3 — six answers, no website."""

    business_name: str = Field(min_length=1, max_length=255)
    what_you_sell: str = Field(min_length=2, max_length=1000)
    who_to_reach: str = Field(min_length=2, max_length=1000)
    what_makes_different: str = Field(default="", max_length=1000)
    style: str = Field(min_length=2, max_length=64)
    main_goal: str = Field(min_length=2, max_length=120)
    industry: str = Field(default="", max_length=128)


class ApplyDiscovery(BaseModel):
    """Apply the (possibly user-edited) draft to the Brand Brain."""

    draft: DiscoveryDraft
    business_name: str | None = Field(default=None, max_length=255)
    industry: str | None = Field(default=None, max_length=128)
    website: str | None = Field(default=None, max_length=500)


# ---------------------------------------------------------------------
#  Responses
# ---------------------------------------------------------------------


class DiscoveryResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    source: DiscoverySource
    url: str | None
    business_name: str
    industry: str | None
    status: DiscoveryStatus
    stage: DiscoveryStage
    draft: DiscoveryDraft | None
    error: str | None
    created_at: datetime
    updated_at: datetime


class DiscoveryStartResult(BaseModel):
    id: uuid.UUID
    status: DiscoveryStatus
