"""Generation context schemas.

`GenerationContext` is the shared object every generator can inherit from.
It is computed on demand, never persisted, never mutated. Fields are all
optional so partial-failure during composition (e.g. trends service is
down) doesn't break callers — the LLM and the frontend just see fewer
hints, never an error.
"""

from __future__ import annotations

import uuid
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field

# ---------- atomic fragments ----------


class WinningAsset(BaseModel):
    """One previously generated asset that captured leads. Used by both
    the prompt builder (clone the winning pattern) and the frontend
    (offer 'Make more like this' action chips)."""

    source_asset_type: Literal["content", "ad", "visual", "campaign"]
    source_asset_id: uuid.UUID
    subtype: str  # content_type / ad_type / visual_type / campaign_type
    platform: str | None
    goal: str
    leads: int


class WinningPage(BaseModel):
    """Best-converting lead page, if one exists. Pre-fills `landing_page_id`
    on every studio's form."""

    id: uuid.UUID
    title: str
    slug: str
    submission_count: int
    conversion_rate: float


class ContextPreferences(BaseModel):
    """The defaults a generator form should fall back to when the user
    hasn't explicitly chosen otherwise."""

    suggested_platform: str | None = Field(
        default=None,
        description="Platform the user uses most + that's working — pre-select on every studio.",
    )
    suggested_tone: str | None = Field(
        default=None,
        description="Brand tone the user picked, lightly adjusted by what's worked.",
    )
    suggested_goal: str | None = Field(
        default=None,
        description="Primary growth goal — usually the user's primary_goal_text.",
    )
    suggested_landing_page_id: uuid.UUID | None = Field(
        default=None,
        description="Auto-attach this lead page to every new asset.",
    )


# ---------- the snapshot ----------


class GenerationContext(BaseModel):
    """Everything the platform knows, in one object."""

    model_config = ConfigDict(from_attributes=True)

    # Identity
    user_id: str
    business_name: str
    industry: str

    # Profile-derived
    target_audience: str
    brand_tone: str
    preferred_platforms: list[str] = Field(default_factory=list)
    business_location: str | None = None
    current_monthly_leads_band: str | None = None
    monthly_budget_band: str | None = None
    primary_goal_text: str | None = None

    # Intelligence Engine (v2) highlights — collapsed to short strings the
    # LLM can pin its rationale to without re-reading the full analysis.
    current_state: str | None = None
    desired_future_state: str | None = None
    growth_bottlenecks: list[str] = Field(default_factory=list)
    recommended_channels: list[str] = Field(
        default_factory=list,
        description="Channel names from recommended_acquisition_channels, ranked.",
    )
    current_phase_summary: str | None = Field(
        default=None,
        description="`phase — goal` of realistic_growth_path[0], if present.",
    )

    # Winning patterns — feedback-loop seeds (Phase 3.5 will lean on these).
    winning_assets: list[WinningAsset] = Field(default_factory=list)
    winning_page: WinningPage | None = None

    # Social-intelligence layer — LLM-derived patterns from the user's
    # actual social performance. The generators inherit these as
    # `summary` lines, which is how the platform stops sounding generic.
    social_winning_patterns: list[str] = Field(
        default_factory=list,
        description="Top WinningPattern.summary strings. Surfaced verbatim to every generator.",
    )
    social_audience_signals: list[str] = Field(
        default_factory=list,
        description="High-confidence AudiencePattern.description strings.",
    )

    # Campaign Learning Lab — insights derived from THIS platform's own
    # generations + their downstream results. Distinct from
    # social_winning_patterns: those describe what works ORGANICALLY for
    # this user; these describe what works among the things WE generated.
    # The two layers compose — the generator inherits both verbatim.
    learning_findings: list[str] = Field(
        default_factory=list,
        description="High-confidence LearningEvent.finding strings (active only, sample_size≥3).",
    )

    # Suggested form defaults
    preferences: ContextPreferences = Field(default_factory=ContextPreferences)

    # Provenance — which sources fed this snapshot
    signals_used: list[str] = Field(default_factory=list)
    generated_at: str
