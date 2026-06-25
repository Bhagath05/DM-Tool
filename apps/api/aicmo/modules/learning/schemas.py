"""Pydantic schemas for the Learning Lab.

Three shape families:
- API request/response models — what the router exposes.
- The LLM-output model (`_LearningOutput`) — private, used by the engine.
- Internal `RecordExperimentInput` — what generators pass in when they
  hand us a freshly-created asset to track.

Anything starting with `_` is internal.
"""

from __future__ import annotations

import uuid
from datetime import datetime
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field

# What kinds of assets we can experiment over. Mirrors the
# `source_asset_type` values used in analytics + context.
ExperimentAssetType = Literal[
    "content",
    "ad",
    "visual",
    "landing_page",
    "bundle",
]


ExperimentStatus = Literal["pending", "live", "completed", "archived"]

LearningDirection = Literal["positive", "negative", "neutral"]
LearningSource = Literal["auto", "manual"]
LearningStatus = Literal["active", "archived", "superseded"]


# ---------------------------------------------------------------------
#  CampaignExperiment
# ---------------------------------------------------------------------


class CampaignExperimentResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    user_id: str
    source_asset_type: ExperimentAssetType
    source_asset_id: uuid.UUID
    platform: str | None
    goal: str | None
    hypothesis: str | None
    inherited_patterns: list[str]
    variable_choices: dict
    context_snapshot: dict
    status: ExperimentStatus
    sample_size: int
    confidence_score: float
    evidence: list[str]
    created_at: datetime
    updated_at: datetime


class CampaignExperimentList(BaseModel):
    items: list[CampaignExperimentResponse]


class RecordExperimentInput(BaseModel):
    """The payload generators hand to `learning.service.record_experiment`.

    Generators construct this from their CreativeBrief + GenerationContext
    immediately after writing the asset row. Keep it small and explicit —
    we want the call site to be one line.
    """

    source_asset_type: ExperimentAssetType
    source_asset_id: uuid.UUID
    platform: str | None = None
    goal: str | None = None
    hypothesis: str | None = None
    inherited_patterns: list[str] = Field(default_factory=list)
    variable_choices: dict = Field(default_factory=dict)
    context_snapshot: dict = Field(default_factory=dict)


# ---------------------------------------------------------------------
#  ExperimentResult
# ---------------------------------------------------------------------


class ExperimentResultResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    experiment_id: uuid.UUID
    impressions: int
    reach: int
    likes: int
    comments_count: int
    saves: int
    shares: int
    engagement_rate: float
    leads: int
    ctr: float
    views: int
    watch_time_seconds: float
    captured_at: datetime
    sample_size: int
    confidence_score: float
    evidence: list[str]


class ExperimentResultList(BaseModel):
    items: list[ExperimentResultResponse]


class RecordResultInput(BaseModel):
    """Snapshot a perf row for an existing experiment. Usually called by
    the result-attribution job that pulls from analytics nightly."""

    experiment_id: uuid.UUID
    impressions: int = 0
    reach: int = 0
    likes: int = 0
    comments_count: int = 0
    saves: int = 0
    shares: int = 0
    leads: int = 0
    ctr: float = 0.0
    views: int = 0
    watch_time_seconds: float = 0.0
    raw_json: dict = Field(default_factory=dict)


# ---------------------------------------------------------------------
#  LearningEvent
# ---------------------------------------------------------------------


class LearningEventResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    user_id: str
    variable: str
    finding: str
    direction: LearningDirection
    effect_size: float | None
    experiment_ids: list[uuid.UUID]
    evidence: list[str]
    sample_size: int
    confidence_score: float
    source: LearningSource
    status: LearningStatus
    created_at: datetime
    updated_at: datetime


class LearningEventList(BaseModel):
    items: list[LearningEventResponse]


# ---------------------------------------------------------------------
#  Engine trigger
# ---------------------------------------------------------------------


class LearningRunRequest(BaseModel):
    """Trigger the Learning Engine. Optionally scope to one variable."""

    variable: str | None = Field(
        default=None,
        description="Limit the run to one variable (hook_style, format, …). Omit to scan everything.",
    )


class LearningRunResult(BaseModel):
    events_created: int
    events_superseded: int
    experiments_considered: int


# ---------------------------------------------------------------------
#  Asset-level provenance (used by WhyGeneratedCard)
# ---------------------------------------------------------------------


class ExperimentProvenance(BaseModel):
    """Compact bundle the result-card asks for when it wants to render
    'why this generation looks the way it does'. Joins the experiment to
    any matching LearningEvents the engine has emitted for the variables
    this experiment chose."""

    experiment: CampaignExperimentResponse
    matched_events: list[LearningEventResponse] = Field(default_factory=list)
    latest_result: ExperimentResultResponse | None = None


# ---------------------------------------------------------------------
#  LLM-output shape (private — engine-only)
# ---------------------------------------------------------------------


class _DerivedLearningEvent(BaseModel):
    """One insight the engine extracted from a cluster of experiments."""

    variable: str = Field(
        description="One of: hook_style, format, tone, length, platform, cta_style, visual_style, posting_time, offer, audience_segment."
    )
    finding: str = Field(
        description="One-sentence English statement of the insight. Should cite a number (leads, lift, n) wherever possible."
    )
    direction: LearningDirection = Field(
        description="positive if the chosen variable helped, negative if it hurt, neutral if mixed."
    )
    effect_size: float | None = Field(
        default=None,
        description="Numerical lift if computable (e.g. 2.3 for '2.3x more saves'). Null when qualitative.",
    )
    evidence: list[str] = Field(
        default_factory=list,
        description="2-5 short bullets: what changed, what held constant, the math. Don't pad — fewer concrete bullets beats vague ones.",
    )
    sample_size: int = Field(
        ge=0,
        description="n of experiments backing this finding. Engine should refuse to emit when n<3 unless effect is extreme.",
    )
    confidence_score: float = Field(
        ge=0.0,
        le=1.0,
        description="0.0–1.0. Lower for small n, mixed direction, or thin evidence.",
    )
    experiment_indices: list[int] = Field(
        default_factory=list,
        description="Indices into the experiments-given list this finding cites.",
    )


class _LearningOutput(BaseModel):
    events: list[_DerivedLearningEvent] = Field(
        description="0-6 insights. Empty list is the right answer when the data is too thin — never invent a finding to fill space."
    )
