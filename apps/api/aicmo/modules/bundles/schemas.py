"""Bundle schemas — request, response, persistence shape."""

from __future__ import annotations

import uuid
from datetime import datetime
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field

from aicmo.modules.ads.schemas import AdObjective

BundlePieceKind = Literal["campaign", "content", "ad", "visual"]


class BundlePiece(BaseModel):
    """One asset produced as part of a bundle.

    `id` is the UUID of the row in the asset's own table (generated_content,
    generated_ads, etc.). When `is_error` is true the asset failed to
    generate — the frontend renders this slot as a "regenerate" placeholder
    so the rest of the bundle still ships.
    """

    kind: BundlePieceKind
    id: uuid.UUID | None = None
    label: str = Field(
        description="Human-readable label, e.g. 'Instagram reel', 'Meta ad', 'Carousel design brief'."
    )
    platform: str | None = None
    subtype: str | None = Field(
        default=None,
        description="content_type / ad_type / visual_type / campaign_type — for routing to the right studio.",
    )
    is_error: bool = False
    error_message: str | None = None


class GenerateBundleRequest(BaseModel):
    theme: str = Field(
        min_length=2,
        max_length=255,
        description="One-line campaign theme — e.g. 'May launch of chocolate Brookie bar'.",
    )
    objective: AdObjective = Field(
        description="Funnel objective shared across paid assets in the bundle."
    )
    duration_days: Literal[7, 14, 30] = Field(default=14)
    landing_page_id: uuid.UUID | None = Field(
        default=None,
        description="Lead page to attribute every asset to. Falls back to the context-suggested page when omitted.",
    )


class BundleResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    user_id: str
    business_profile_id: uuid.UUID
    theme: str
    objective: str
    duration_days: int
    landing_page_id: uuid.UUID | None
    pieces: list[BundlePiece]
    created_at: datetime


class BundleList(BaseModel):
    items: list[BundleResponse]
