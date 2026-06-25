"""Render-specific request/response schemas.

Kept separate from visuals/schemas.py to keep Phase 4-A's surface small
and removable without disturbing the existing brief schemas.
"""

from __future__ import annotations

import uuid
from datetime import datetime
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field


class RenderRequest(BaseModel):
    quality: Literal["standard", "hd"] = Field(
        default="standard",
        description="Standard ≈ $0.04/render · HD ≈ $0.16/render.",
    )


class RenderedVisualResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    visual_id: uuid.UUID
    provider: str
    width: int
    height: int
    mime_type: str
    cost_cents: int
    latency_ms: int
    created_at: datetime
    # Signed URL the frontend should embed in <img>. Expires per
    # MEDIA_URL_TTL_SECONDS — typically 30 days, signed with HMAC.
    signed_url: str
    slide_index: int | None = None


class RenderedVisualList(BaseModel):
    items: list[RenderedVisualResponse]


class RenderQuotaStatus(BaseModel):
    """Returned alongside render responses + queryable on its own so the
    UI can grey out the render button once the user is close to the cap."""

    used_today: int
    daily_cap: int
    remaining: int
