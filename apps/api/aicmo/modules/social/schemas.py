"""Social Intelligence Layer schemas.

Two distinct shapes:
- API request/response models (what the router speaks).
- The LLM-output model (`_WinningPatternBatch`) — private, used by the
  analyzer only.

Naming convention: anything starting with `_` is internal.
"""

from __future__ import annotations

import uuid
from datetime import datetime
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field


# Platform we support for read-only ingestion in Phase 1.
SocialPlatform = Literal[
    "instagram",
    "facebook",
    "linkedin",
    "youtube",
    "tiktok",
]


# Source of the data: did it come from a real OAuth sync, or did the user
# paste it in via the manual-import path?
ConnectionSource = Literal["oauth", "manual_import"]


# ---------------------------------------------------------------------
#  Connection
# ---------------------------------------------------------------------


class SocialConnectionResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    user_id: str
    platform: SocialPlatform
    source: ConnectionSource
    metadata_json: dict
    last_synced_at: datetime | None
    expires_at: datetime | None
    created_at: datetime
    updated_at: datetime


class SocialConnectionList(BaseModel):
    items: list[SocialConnectionResponse]


# ---------------------------------------------------------------------
#  Asset + signal
# ---------------------------------------------------------------------


class PerformanceSignalResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    impressions: int
    reach: int
    likes: int
    comments_count: int
    saves: int
    shares: int
    engagement_rate: float
    views: int
    watch_time_seconds: float
    ctr: float
    captured_at: datetime


class SocialAssetResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    platform: SocialPlatform
    platform_post_id: str
    asset_type: str
    caption: str | None
    thumbnail_url: str | None
    permalink: str | None
    hashtags: list[str]
    posted_at: datetime | None
    # Latest signal joined in. May be null when no signals have synced yet.
    latest_signal: PerformanceSignalResponse | None = None


class SocialAssetList(BaseModel):
    items: list[SocialAssetResponse]


# ---------------------------------------------------------------------
#  Patterns
# ---------------------------------------------------------------------


class WinningPatternResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    platform: SocialPlatform | None
    summary: str
    hook_pattern: str | None
    visual_pattern: str | None
    caption_pattern: str | None
    cta_pattern: str | None
    format_pattern: str | None
    posting_time_pattern: str | None
    performance_score: float
    source_asset_ids: list[uuid.UUID]
    created_at: datetime


class WinningPatternList(BaseModel):
    items: list[WinningPatternResponse]


class AudiencePatternResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    platform: SocialPlatform
    pattern_type: str
    description: str
    confidence_score: float
    created_at: datetime


class AudiencePatternList(BaseModel):
    items: list[AudiencePatternResponse]


# ---------------------------------------------------------------------
#  Manual import — the testable-today path.
#  Users paste JSON they exported from Instagram Insights / LinkedIn /
#  YouTube Studio. We accept a permissive shape and pull fields we
#  recognize.
# ---------------------------------------------------------------------


class ManualImportAssetPayload(BaseModel):
    """One asset in a manual import. Loose by design — the user might
    paste fields with different keys from different platforms."""

    platform_post_id: str = Field(min_length=1, max_length=128)
    asset_type: str = Field(min_length=1, max_length=32)
    caption: str | None = None
    thumbnail_url: str | None = None
    permalink: str | None = None
    hashtags: list[str] = Field(default_factory=list)
    posted_at: datetime | None = None

    # Optional perf snapshot — if present, we'll create a PerformanceSignal
    # row too. If absent, the asset is recorded with no signal yet.
    impressions: int = 0
    reach: int = 0
    likes: int = 0
    comments_count: int = 0
    saves: int = 0
    shares: int = 0
    views: int = 0
    watch_time_seconds: float = 0.0
    ctr: float = 0.0

    # Everything else the user pasted, raw.
    raw_json: dict = Field(default_factory=dict)


class ManualImportPayload(BaseModel):
    """Top-level import request. Creates a connection (or reuses one) and
    inserts all assets + their signals in one shot."""

    platform: SocialPlatform
    handle: str | None = Field(
        default=None, max_length=128, description="@yourbusiness style handle"
    )
    assets: list[ManualImportAssetPayload] = Field(min_length=1, max_length=200)


class ImportResult(BaseModel):
    connection_id: uuid.UUID
    inserted_assets: int
    updated_assets: int
    inserted_signals: int


# ---------------------------------------------------------------------
#  Analyzer trigger
# ---------------------------------------------------------------------


class AnalyzeRequest(BaseModel):
    platform: SocialPlatform | None = Field(
        default=None,
        description="Limit the analysis to one platform. Omit to analyze cross-platform.",
    )


class AnalyzeResult(BaseModel):
    """What the analyzer endpoint returns. The actual rows live in
    `winning_patterns` — this is the summary for the frontend toast."""

    patterns_created: int
    audience_patterns_created: int
    assets_considered: int


# ---------------------------------------------------------------------
#  LLM-output shape (private — analyzer-only)
# ---------------------------------------------------------------------


class _AnalyzedWinningPattern(BaseModel):
    """One pattern Gemini extracted from the data. We map these into
    WinningPattern rows."""

    summary: str = Field(
        description="One-sentence English statement of the pattern. The generator inherits THIS verbatim. Must reference real numbers when possible."
    )
    hook_pattern: str | None = Field(
        default=None,
        description="Hook structure that performs (e.g. 'first-line question'). Null if no hook signal.",
    )
    visual_pattern: str | None = Field(
        default=None,
        description="Visual style that performs. Null if no visual signal.",
    )
    caption_pattern: str | None = Field(
        default=None,
        description="Caption length or structure that performs.",
    )
    cta_pattern: str | None = Field(
        default=None,
        description="CTA approach that performs.",
    )
    format_pattern: str | None = Field(
        default=None,
        description="Format that performs (reel < 15s, carousel 5 slides, etc).",
    )
    posting_time_pattern: str | None = Field(
        default=None,
        description="Posting-time pattern if signal is clear.",
    )
    performance_score: float = Field(
        ge=0.0,
        le=1.0,
        description="0.0–1.0. Higher = stronger evidence in the data.",
    )
    source_asset_indices: list[int] = Field(
        default_factory=list,
        description="Indices into the assets-given list that exemplify this pattern.",
    )


class _AnalyzedAudiencePattern(BaseModel):
    pattern_type: str = Field(
        description="One of: demographic_skew, geographic_concentration, active_time, interest_overlap, sentiment, engagement_type."
    )
    description: str
    confidence_score: float = Field(ge=0.0, le=1.0)


class _AnalysisOutput(BaseModel):
    winning_patterns: list[_AnalyzedWinningPattern] = Field(
        description="2-5 patterns. Skip a pattern if the signal is weak — better to return fewer high-confidence patterns than dilute with guesses."
    )
    audience_patterns: list[_AnalyzedAudiencePattern] = Field(
        description="0-3 audience patterns. Empty list is fine if no clear demographic / time / interest signal exists."
    )
