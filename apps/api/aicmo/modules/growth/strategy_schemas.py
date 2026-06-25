"""Strategy Engine I/O — the campaign plan (objective → asset plan).

This is the bridge between the outcome (Law 1) and the Creative Studio: the
LLM (or the deterministic fallback) turns a Growth Objective into a campaign
strategy + an ASSET PLAN — the list of creatives that should be made. The
Studio composes + edits each one. Industry never appears here; only the
outcome + free-text context.
"""

from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, Field

CreativeType = Literal["poster", "carousel", "ad", "reel", "video"]
Aspect = Literal["1:1", "4:5", "9:16", "16:9"]


class Slide(BaseModel):
    """One slide/scene of a multi-part creative (carousel page or reel scene)."""

    headline: str = Field(min_length=1, max_length=140)
    body: str | None = Field(default=None, max_length=300)


class AssetSpec(BaseModel):
    """One creative the campaign needs. The Studio composes this into an
    editable design; `creative_type` chooses the recipe, never an industry."""

    creative_type: CreativeType
    aspect: Aspect = "4:5"
    headline: str = Field(min_length=1, max_length=140)
    subhead: str | None = Field(default=None, max_length=200)
    cta: str = Field(min_length=1, max_length=60)
    slides: list[Slide] = Field(default_factory=list, max_length=8)
    variant_label: str | None = Field(default=None, max_length=16)
    rationale: str | None = Field(default=None, max_length=240)


class CampaignStrategy(BaseModel):
    """The full plan. `asset_plan` is what gets built; the rest is the
    why (surfaced to the user per the Constitution's recommendation contract)."""

    objective_summary: str = Field(min_length=1, max_length=300)
    audience: str = Field(min_length=1, max_length=300)
    hook: str = Field(min_length=1, max_length=200)
    value_prop: str = Field(min_length=1, max_length=300)
    proof_point: str | None = Field(default=None, max_length=240)
    cta_angle: str = Field(min_length=1, max_length=120)
    channels: list[str] = Field(default_factory=list, max_length=8)
    asset_plan: list[AssetSpec] = Field(default_factory=list, max_length=12)
