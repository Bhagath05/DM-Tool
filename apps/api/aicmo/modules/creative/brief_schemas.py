"""Phase 6.3 — AI creative brief schemas.

`CreativeBriefResult` is the STRUCTURED LLM output (Constitution: no free-text
persisted). It carries the confidence + reason fields the recommendation
contract mandates, and the brief is only ever generated from real context
(see brief_prompts) — never fabricated.
"""

from __future__ import annotations

import uuid
from datetime import datetime

from pydantic import BaseModel, ConfigDict, Field


class CreativeBriefResult(BaseModel):
    """What the strategist-designer produces for the Creative Studio."""

    objective: str = Field(description="The single business outcome this creative serves.")
    audience: str = Field(description="Who it speaks to, grounded in the profile/strategy.")
    key_message: str = Field(description="The one thing the viewer must take away.")
    tone: str
    visual_direction: str = Field(description="Art direction: mood, palette feel, imagery.")
    must_include: list[str] = Field(default_factory=list, max_length=12)
    avoid: list[str] = Field(default_factory=list, max_length=12)
    deliverables: list[str] = Field(
        default_factory=list, max_length=12,
        description="Recommended creative asset types (poster, carousel, story, …).",
    )
    confidence: int = Field(ge=0, le=100)
    reason: str = Field(max_length=200, description="What real data this brief drew on.")


class GenerateBriefRequest(BaseModel):
    objective: str | None = Field(default=None, max_length=200)
    campaign_id: uuid.UUID | None = None
    content_id: uuid.UUID | None = None
    strategy_id: uuid.UUID | None = None


class CreativeBriefResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    title: str
    objective: str | None
    brief: dict
    grounded_in: list[str]
    confidence: int
    reason: str | None
    campaign_id: uuid.UUID | None
    content_id: uuid.UUID | None
    strategy_id: uuid.UUID | None
    created_at: datetime


class CreativeBriefList(BaseModel):
    items: list[CreativeBriefResponse]
