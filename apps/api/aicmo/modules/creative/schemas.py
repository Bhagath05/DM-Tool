"""Creative Platform schemas — Creative Core V0.

Media-agnostic enums so future creative types (poster/banner/…) reuse
them. V0 only accepts `media_type=video`; the rest are reserved values.
"""

from __future__ import annotations

import uuid
from datetime import datetime
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field

from aicmo.security.prompt_safety import sanitize_prompt_input

CreativeType = Literal[
    "poster", "banner", "carousel", "thumbnail", "social_post", "reel_cover", "video"
]
MediaType = Literal["image", "carousel", "composite", "video"]
AudioMode = Literal["tts_voiceover", "veo_native", "silent"]

# Project state machine (creative_project.status).
CreativeStatus = Literal[
    "draft", "scripting", "storyboarding", "rendering", "assembling",
    "post_processing", "ready", "published",
    "blocked_budget", "canceled",
    # terminal failures carry the failing stage, e.g. "failed_rendering"
    "failed_scripting", "failed_storyboarding", "failed_rendering",
    "failed_assembling", "failed_post_processing",
]


class CreateProjectRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    title: str = Field(min_length=1, max_length=255)
    brief: str | None = Field(default=None, max_length=4000)
    creative_type: CreativeType = "video"
    format_slug: str = Field(min_length=1, max_length=48)
    goal: str | None = Field(default=None, max_length=255)
    tone: str | None = Field(default=None, max_length=64)
    objective: str | None = Field(default=None, max_length=64)
    audio_mode: AudioMode = "tts_voiceover"
    campaign_id: uuid.UUID | None = None

    def sanitized_brief(self) -> str | None:
        return sanitize_prompt_input(self.brief, field_name="creative_brief")


class CostBreakdown(BaseModel):
    stage: str
    provider: str
    cost_cents: int


class ProjectResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    title: str
    creative_type: str
    media_type: str
    format_slug: str | None
    platform: str | None
    status: str
    audio_mode: str
    estimated_cost_cents: int
    actual_cost_cents: int
    created_at: datetime
    updated_at: datetime


class ProjectList(BaseModel):
    items: list[ProjectResponse]


class CostSummary(BaseModel):
    project_id: uuid.UUID
    estimated_cost_cents: int
    actual_cost_cents: int
    breakdown: list[CostBreakdown]


class FormatDescriptor(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    slug: str
    display_name: str
    media_type: str
    platform: str
    aspect_ratio: str
    width: int
    height: int
    max_duration_s: int | None
    seeding: str
