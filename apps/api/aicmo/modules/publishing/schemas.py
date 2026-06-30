from __future__ import annotations

import uuid
from datetime import datetime
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field

AssetType = Literal[
    "poster",
    "carousel",
    "story",
    "reel_script",
    "ad_creative",
    "caption",
]
AssetStatus = Literal["draft", "ready", "scheduled", "published", "failed"]
PublishPlatform = Literal[
    "instagram",
    "facebook",
    "linkedin",
    "youtube",
    "pinterest",
    "google_business_profile",
]
PublishStatus = Literal["draft", "scheduled", "published", "failed"]


class ContentAssetResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    recommendation_id: uuid.UUID | None
    asset_type: AssetType
    source_table: str
    source_id: uuid.UUID
    status: AssetStatus
    payload: dict
    created_at: datetime
    updated_at: datetime


class SchedulePostRequest(BaseModel):
    content_asset_id: uuid.UUID
    platform: PublishPlatform
    scheduled_at: datetime


class ScheduleFromRecommendationRequest(BaseModel):
    recommendation_id: uuid.UUID
    platform: PublishPlatform
    scheduled_at: datetime


class ScheduledPostResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    content_asset_id: uuid.UUID
    recommendation_id: uuid.UUID | None
    platform: PublishPlatform
    scheduled_at: datetime
    publish_status: PublishStatus
    platform_post_id: str | None
    published_at: datetime | None
    error_message: str | None
    attempt_count: int
    created_at: datetime
    updated_at: datetime


class ScheduledPostList(BaseModel):
    items: list[ScheduledPostResponse]


class PublishEventResponse(BaseModel):
    """One entry in a scheduled post's audit trail (scheduled / publish_attempt
    / published / failed), with structured detail."""

    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    event_type: str
    detail: dict
    created_at: datetime


class PublishEventList(BaseModel):
    items: list[PublishEventResponse]


class PublishPerformanceMetrics(BaseModel):
    recommendation_id: uuid.UUID | None
    platform: str
    platform_post_id: str | None
    reach: int = 0
    impressions: int = 0
    engagement: int = 0
    likes: int = 0
    comments: int = 0
    leads_in_window: int = 0


class AssetPerformanceResponse(BaseModel):
    content_asset_id: uuid.UUID
    recommendation_id: uuid.UUID | None
    metrics: PublishPerformanceMetrics | None
    scheduled_posts: list[ScheduledPostResponse] = Field(default_factory=list)
