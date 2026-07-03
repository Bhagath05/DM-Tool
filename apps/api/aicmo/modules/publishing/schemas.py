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
PublishStatus = Literal[
    "draft", "scheduled", "publishing", "published",
    "failed", "cancelled", "paused",
]
ApprovalStatus = Literal[
    "not_required", "pending", "approved", "rejected", "changes_requested",
]


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
    next_attempt_at: datetime | None = None
    approval_status: ApprovalStatus = "not_required"
    approval_required: bool = False
    reviewed_by_user_id: str | None = None
    approval_reason: str | None = None
    schedule_timezone: str | None = None
    created_at: datetime
    updated_at: datetime


class ScheduledPostList(BaseModel):
    items: list[ScheduledPostResponse]


# ---- Phase 6.4 enterprise ops ----
class RescheduleRequest(BaseModel):
    scheduled_at: datetime
    schedule_timezone: str | None = None


class BulkScheduleItem(BaseModel):
    content_asset_id: uuid.UUID
    platform: PublishPlatform
    scheduled_at: datetime
    schedule_timezone: str | None = None
    approval_required: bool = False


class BulkScheduleRequest(BaseModel):
    items: list[BulkScheduleItem] = Field(min_length=1, max_length=100)


class BulkScheduleResult(BaseModel):
    scheduled: list[ScheduledPostResponse]
    count: int


class ApprovalDecisionRequest(BaseModel):
    reason: str | None = Field(default=None, max_length=1000)


class PlatformHealth(BaseModel):
    platform: str
    published: int = 0
    failed: int = 0
    scheduled: int = 0
    success_rate: float = 0.0


class QueueAnalyticsResponse(BaseModel):
    """Queue-level stats for the publishing dashboard (spec #7)."""

    published: int = 0
    scheduled: int = 0
    publishing: int = 0
    failed: int = 0
    cancelled: int = 0
    paused: int = 0
    approval_pending: int = 0
    draft: int = 0
    queue_length: int = 0
    total_retries: int = 0
    success_rate: float = 0.0
    avg_publish_seconds: float | None = None
    platform_health: list[PlatformHealth] = Field(default_factory=list)


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
