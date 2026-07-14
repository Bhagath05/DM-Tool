from __future__ import annotations

import re
import uuid
from datetime import datetime
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, HttpUrl, field_validator

from aicmo.security.prompt_safety import sanitize_prompt_input

# ---------- LLM analysis result (also persisted to the profile row) ----------


class GrowthMilestone(BaseModel):
    """One phase of the Realistic Growth Path."""

    phase: str = Field(
        description="Time horizon, e.g. 'Weeks 1-4', 'Month 2-3', 'Quarter 2'."
    )
    goal: str = Field(
        description="The single most important outcome for this phase. Concrete and measurable."
    )
    actions: list[str] = Field(
        description="2-4 concrete actions that produce the goal. Verb-led, not generic."
    )
    success_metric: str = Field(
        description="One metric NAME to watch (e.g. 'qualified leads / week') — never a fabricated number."
    )


class ChannelRecommendation(BaseModel):
    """One acquisition channel call with rationale."""

    channel: str = Field(
        description="Specific channel, e.g. 'Instagram organic', 'Google Search ads', 'LinkedIn outreach', 'Local SEO'."
    )
    why_now: str = Field(
        description="One-sentence reason this channel fits the business's stage and budget RIGHT NOW."
    )
    expected_outcome: str = Field(
        description="Realistic 30-60 day outcome in plain English. No fake numbers."
    )


class BusinessAnalysis(BaseModel):
    """Structured AI output. Persisted as JSONB on `business_profiles.analysis`.

    Phase 2.1 — Intelligence Engine v2 adds the strategist-deliverable
    sections (current_state, desired_future_state, gap_analysis,
    growth_bottlenecks, competitor_signals, realistic_growth_path,
    recommended_acquisition_channels). They are all optional so analyses
    persisted under v1 still parse cleanly when the frontend reads them.

    The prompt requests every field — Gemini fills the new ones for fresh
    onboarding submissions; the renderer gracefully falls back to the v1
    surface when reading legacy rows.
    """

    # ---- v1 fields (kept required so existing DB rows still validate) ----

    business_summary: str = Field(
        description="2-3 sentence positioning statement for this business."
    )
    audience_insights: list[str] = Field(
        description="Distinct insights about the target audience — psychographics or behaviours, never just demographics."
    )
    marketing_opportunities: list[str] = Field(
        description="Specific marketing opportunities to pursue. Concrete, not generic."
    )
    content_directions: list[str] = Field(
        description="Recommended content angles or themes mapped to the user's platforms."
    )
    strategy_recommendation: str = Field(
        description="One-paragraph recommended marketing strategy sequencing the next 30-60 days."
    )

    # ---- v2 fields (Phase 2.1 — optional for back-compat) ----

    current_state: str | None = Field(
        default=None,
        description="2-3 sentences on where the business is today — traction, brand maturity, channel mix. Honest, not flattering.",
    )
    desired_future_state: str | None = Field(
        default=None,
        description="2-3 sentences on the destination implied by the user's primary goal — what 'success' looks like in concrete terms.",
    )
    gap_analysis: str | None = Field(
        default=None,
        description="One short paragraph naming the biggest 2-3 gaps between current and desired state.",
    )
    growth_bottlenecks: list[str] | None = Field(
        default=None,
        description="Specific blockers — not vague (e.g. 'no repeat-purchase flow', 'IG bio doesn't promise a payoff'). 3-5 items.",
    )
    competitor_signals: list[str] | None = Field(
        default=None,
        description="3-5 plausible competitor moves to watch or learn from, inferred from the industry + audience. No fabricated names or stats.",
    )
    realistic_growth_path: list[GrowthMilestone] | None = Field(
        default=None,
        description="A phased plan — typically 3 phases. Calibrated to the user's stated budget band and current traction band. NEVER over-promise.",
    )
    recommended_acquisition_channels: list[ChannelRecommendation] | None = Field(
        default=None,
        description="Top 3 channels for THIS business at THIS stage and budget. Ranked by where to put effort first.",
    )


# ---------- API request/response ----------

# Where the business is in its lifecycle — calibrates every AI recommendation.
GrowthStage = Literal["idea", "launching", "growing", "established", "scaling"]


class BusinessProfileBase(BaseModel):
    business_name: str = Field(min_length=2, max_length=255)
    website: HttpUrl | None = None
    industry: str = Field(min_length=2, max_length=128)
    business_type: str | None = Field(default=None, max_length=64)
    target_audience: str = Field(min_length=10, max_length=2000)
    brand_tone: str = Field(min_length=2, max_length=64)
    competitors: list[str] = Field(default_factory=list, max_length=30)
    goals: list[str] = Field(min_length=1, max_length=30)
    preferred_platforms: list[str] = Field(min_length=1, max_length=15)

    # Phase 2.0 — conversational onboarding additions. All optional so the
    # legacy wizard's payloads validate unchanged.
    business_location: str | None = Field(default=None, max_length=255)
    current_monthly_leads_band: str | None = Field(default=None, max_length=32)
    monthly_budget_band: str | None = Field(default=None, max_length=32)
    primary_goal_text: str | None = Field(default=None, max_length=500)

    # Phase 3.1 — AI business understanding. Optional so legacy payloads
    # validate unchanged; the autonomous strategist reasons over them.
    products: list[str] = Field(default_factory=list, max_length=50)
    services: list[str] = Field(default_factory=list, max_length=50)
    unique_selling_points: list[str] = Field(default_factory=list, max_length=20)
    pricing: str | None = Field(default=None, max_length=1000)
    growth_stage: GrowthStage | None = None

    # ---- Phase 8 Brand Brain — brand identity ----
    brand_colors: list[str] = Field(default_factory=list, max_length=24)
    fonts: list[str] = Field(default_factory=list, max_length=12)
    keywords: list[str] = Field(default_factory=list, max_length=60)
    brand_rules: list[str] = Field(default_factory=list, max_length=40)
    writing_style: str | None = Field(default=None, max_length=2000)


class BusinessProfileCreate(BusinessProfileBase):
    """Onboarding/replace payload. Trust upgrade T3 — strict input
    validators run here ONLY (not on Base, because Base is also the
    Response, and we don't want existing legacy rows to 500 just because
    their `target_audience` is junk from earlier test data)."""

    # Phase S2.5 — sanitize prompt-bound fields BEFORE the gibberish
    # checks below see them. `mode="before"` runs first per Pydantic v2.
    @field_validator(
        "business_name",
        "target_audience",
        "primary_goal_text",
        mode="before",
    )
    @classmethod
    def _strip_prompt_injection(cls, v):
        return sanitize_prompt_input(v, field_name="business_profile")

    @field_validator("business_name")
    @classmethod
    def _business_name_must_be_real(cls, v: str) -> str:
        if _looks_like_gibberish(v):
            raise ValueError(
                "That doesn't look like a business name yet — give us what you actually call it."
            )
        return v

    @field_validator("industry")
    @classmethod
    def _industry_must_be_specific(cls, v: str) -> str:
        if _looks_like_gibberish(v):
            raise ValueError(
                "That doesn't look like an industry yet — try something like 'Cafe' or 'SaaS' or 'Yoga studio'."
            )
        if v.strip().lower() in _GENERIC_TERMS:
            raise ValueError(
                f"'{v}' is too generic — what KIND of business? e.g. 'Cafe', 'B2B SaaS', 'Local plumber'."
            )
        return v

    @field_validator("target_audience")
    @classmethod
    def _audience_must_describe_humans(cls, v: str) -> str:
        if _looks_like_gibberish(v):
            raise ValueError(
                "Try being more specific about who buys from you most — a sentence about the actual people works."
            )
        if _is_ultra_generic_audience(v):
            raise ValueError(
                "'Everyone' isn't an audience — describe the type of person who actually buys from you (age, role, what they care about)."
            )
        return v


class BusinessProfileUpdate(BaseModel):
    business_name: str | None = Field(default=None, min_length=2, max_length=255)
    website: HttpUrl | None = None
    industry: str | None = Field(default=None, min_length=2, max_length=128)
    business_type: str | None = Field(default=None, max_length=64)
    target_audience: str | None = Field(default=None, min_length=10, max_length=2000)
    brand_tone: str | None = Field(default=None, min_length=2, max_length=64)
    competitors: list[str] | None = Field(default=None, max_length=30)
    goals: list[str] | None = Field(default=None, min_length=1, max_length=30)
    preferred_platforms: list[str] | None = Field(
        default=None, min_length=1, max_length=15
    )
    business_location: str | None = Field(default=None, max_length=255)
    current_monthly_leads_band: str | None = Field(default=None, max_length=32)
    monthly_budget_band: str | None = Field(default=None, max_length=32)
    primary_goal_text: str | None = Field(default=None, max_length=500)
    products: list[str] | None = Field(default=None, max_length=50)
    services: list[str] | None = Field(default=None, max_length=50)
    unique_selling_points: list[str] | None = Field(default=None, max_length=20)
    pricing: str | None = Field(default=None, max_length=1000)
    # ---- Phase 8 Brand Brain — brand identity ----
    brand_colors: list[str] | None = Field(default=None, max_length=24)
    fonts: list[str] | None = Field(default=None, max_length=12)
    keywords: list[str] | None = Field(default=None, max_length=60)
    brand_rules: list[str] | None = Field(default=None, max_length=40)
    writing_style: str | None = Field(default=None, max_length=2000)
    growth_stage: GrowthStage | None = None

    # Same trust gates on partial updates — but only when the user sent
    # the field. Pydantic skips validators when the value is None and the
    # field is Optional, so this stays a no-op on omitted fields.

    # Phase S2.5 — prompt-safety pass on the partial-update path too.
    @field_validator(
        "business_name",
        "target_audience",
        "primary_goal_text",
        mode="before",
    )
    @classmethod
    def _strip_prompt_injection(cls, v):
        return sanitize_prompt_input(v, field_name="business_profile_update")

    @field_validator("business_name")
    @classmethod
    def _business_name_must_be_real(cls, v: str | None) -> str | None:
        if v is None:
            return v
        if _looks_like_gibberish(v):
            raise ValueError(
                "That doesn't look like a business name — give us what you actually call it."
            )
        return v

    @field_validator("industry")
    @classmethod
    def _industry_must_be_specific(cls, v: str | None) -> str | None:
        if v is None:
            return v
        if _looks_like_gibberish(v) or v.strip().lower() in _GENERIC_TERMS:
            raise ValueError(
                f"'{v}' is too generic — what KIND of business? e.g. 'Cafe', 'B2B SaaS', 'Local plumber'."
            )
        return v

    @field_validator("target_audience")
    @classmethod
    def _audience_must_describe_humans(cls, v: str | None) -> str | None:
        if v is None:
            return v
        if _looks_like_gibberish(v):
            raise ValueError(
                "Try being more specific about who buys from you most."
            )
        if _is_ultra_generic_audience(v):
            raise ValueError(
                "'Everyone' isn't an audience — describe who actually buys from you."
            )
        return v


# ----- gibberish / generic detectors --------------------------------------

#: Anything that resolves to one of these is treated as "you haven't actually
#: described an audience yet." Case-insensitive. Whole-string match only.
_GENERIC_AUDIENCE_PHRASES: set[str] = {
    "everyone",
    "anyone",
    "all",
    "all audience",
    "all audiences",
    "all ages",
    "all people",
    "general public",
    "the public",
    "customers",
    "people",
    "humans",
    "viral",
    "viral audience",
    "mass market",
    "the world",
    "global",
    "n/a",
    "none",
    "tbd",
}

#: Strings that are valid English words but too vague to be an industry.
_GENERIC_TERMS: set[str] = {
    "business",
    "company",
    "startup",
    "thing",
    "stuff",
    "n/a",
    "none",
    "tbd",
    "other",
    "general",
}


def _looks_like_gibberish(text: str) -> bool:
    """Heuristic: does this look like a real human-typed phrase?

    Trips when ANY of:
    - No whitespace AND length > 8 AND zero vowels in first 8 chars
      (catches "jnnjnjkhjhn", "qwertyuiop")
    - Same character repeats >= 5 times in a row ("aaaaa", "hahahaha")
    - Mostly non-letter characters
    """
    if not text:
        return True
    t = text.strip().lower()
    if len(t) < 2:
        return True

    # Repeated-character runs
    if re.search(r"(.)\1{4,}", t):
        return True

    # Mostly non-letter — e.g. "1234567" or "@#$%^&"
    letter_count = sum(1 for c in t if c.isalpha())
    if letter_count < max(2, len(t) // 2):
        return True

    # Long single-token strings with no vowels in the first chunk
    if " " not in t and "-" not in t and len(t) > 8:
        first_chunk = t[:8]
        if not re.search(r"[aeiouy]", first_chunk):
            return True

    return False


def _is_ultra_generic_audience(text: str) -> bool:
    """Reject single-word or whole-phrase generic audience claims."""
    t = text.strip().lower().rstrip(".!")
    if t in _GENERIC_AUDIENCE_PHRASES:
        return True
    # Single-word audiences are almost always too generic.
    if " " not in t and len(t) < 16:
        return True
    return False


class BusinessProfileResponse(BusinessProfileBase):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    user_id: str
    # Tenant ids — surfaced so downstream modules (coach composer, etc.)
    # can scope brand-level lookups without re-querying the row.
    # Without these, four coach composer signals would silently fail with
    # `AttributeError: 'BusinessProfileResponse' object has no attribute 'brand_id'`.
    organization_id: uuid.UUID
    brand_id: uuid.UUID
    analysis_status: Literal["pending", "completed", "failed"]
    analysis: BusinessAnalysis | None
    analysis_error: str | None
    created_at: datetime
    updated_at: datetime
