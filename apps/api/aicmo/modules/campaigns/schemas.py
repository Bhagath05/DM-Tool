from __future__ import annotations

import uuid
from datetime import datetime
from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field, field_validator

from aicmo.security.prompt_safety import sanitize_prompt_input

# ---------- enums + constants ----------

CampaignType = Literal[
    "product_launch",
    "brand_awareness",
    "lead_generation",
    "seasonal",
    "engagement_growth",
    "retargeting",
]

CAMPAIGN_TYPES: tuple[CampaignType, ...] = (
    "product_launch",
    "brand_awareness",
    "lead_generation",
    "seasonal",
    "engagement_growth",
    "retargeting",
)

DURATION_DAYS: tuple[int, ...] = (7, 14, 30)

# Funnel-intent guidance the prompt builder injects per campaign type.
CAMPAIGN_INTENT: dict[CampaignType, str] = {
    "product_launch": (
        "Build anticipation pre-launch, hit critical mass on launch day, then "
        "sustain momentum post-launch with social proof and FAQ-style posts."
    ),
    "brand_awareness": (
        "Maximise top-of-funnel reach + recall. Memorable hooks, distinctive "
        "format choices, value-first posts. Conversions are not the metric."
    ),
    "lead_generation": (
        "Drive opt-ins. Front-load value, gate the high-intent assets, escalate "
        "specificity of CTAs as the campaign progresses."
    ),
    "seasonal": (
        "Tie the campaign to a time-bound moment. Build into peak day, then "
        "extend with thank-you / recap posts."
    ),
    "engagement_growth": (
        "Maximise comments, saves, shares. Conversation starters, opinions, "
        "save-worthy reference posts."
    ),
    "retargeting": (
        "Re-warm existing customers / leads. Lean on familiarity, address "
        "objections, present incremental offers."
    ),
}

CONTENT_TYPES: tuple[str, ...] = (
    "social_post",
    "reel",
    "carousel",
    "story",
    "live",
    "email",
    "ad_creative",
)


# ---------- nested schema parts ----------


class CampaignStrategy(BaseModel):
    """Top-level strategic envelope — the 'why' of the plan."""

    campaign_theme: str = Field(
        description="One-line distinctive angle the campaign hangs on."
    )
    audience_focus: str = Field(
        description="Who this campaign targets — may narrow the profile audience."
    )
    funnel_strategy: str = Field(
        description="Short paragraph on how the funnel moves people from "
        "awareness → consideration → conversion (or whatever applies to this type)."
    )
    posting_cadence: str = Field(
        description="Concrete cadence rule, e.g. 'every other day on IG, daily on X'."
    )
    cta_progression: str = Field(
        description="How CTAs escalate across the campaign — soft asks → hard ask."
    )
    success_signals: list[str] = Field(
        description="3-6 metric NAMES to watch (not fabricated numbers) — e.g. "
        "'reach', 'save rate', 'comment-to-like ratio'.",
    )


class PlatformRecommendation(BaseModel):
    platform: str = Field(description="Must be one of the user's selected platforms.")
    role: Literal["primary", "secondary", "amplifier"] = Field(
        description="primary = main lift, secondary = supporting, amplifier = paid/cross-post."
    )
    rationale: str = Field(description="One sentence on why this platform earns this role.")


class VisualDirectionHint(BaseModel):
    """High-level aesthetic direction in words — no hex codes (that's the
    Visuals module's job per calendar day)."""

    aesthetic: str = Field(description="One-line aesthetic descriptor.")
    palette_direction: str = Field(
        description="Words, not hex: e.g. 'warm muted earth tones with a single accent pop'."
    )
    typography_direction: str = Field(
        description="Words: e.g. 'editorial serif headlines with utilitarian sans body'."
    )


class CampaignSequence(BaseModel):
    """A funnel phase mapped to a day range. 3-5 phases per campaign."""

    phase_name: str = Field(description="E.g. 'Awareness build', 'Social proof drop', 'Last call'.")
    day_range: str = Field(description="E.g. 'Days 1-3' or 'Day 14'.")
    objective: str = Field(description="What this phase accomplishes in the funnel.")
    primary_metric: str = Field(description="Single metric NAME to watch for this phase.")


class CalendarDay(BaseModel):
    """One publish slot. NOT a generated asset — a brief to act on.

    Constraints (ge/le on day, min/max on array fields) are deliberately
    NOT set here — Gemini's structured-output validator rejects schemas
    with too many bounded constraints ("too many states for serving").
    Validation that matters (day count == duration_days, day in 1..N) is
    enforced server-side in the generator after the response lands.
    """

    day: int
    platform: str
    content_type: str = Field(
        description="One of: social_post, reel, carousel, story, live, email, ad_creative."
    )
    objective: str = Field(description="What this single post does in the funnel.")
    hook: str = Field(description="One-sentence hook idea.")
    cta: str = Field(description="Specific CTA verb-led.")
    visual_direction_summary: str = Field(
        description="One-paragraph creative brief (NOT a full visual spec — that's "
        "the Visuals module's job if the user clicks 'design this' later)."
    )
    recommended_ad_support: str = Field(
        description="Either a paid-media recommendation like 'boost for $50 / 48h "
        "targeting cold audience' or the literal string 'none' if organic-only."
    )
    rationale: str = Field(description="Why this slot exists in this phase of the funnel.")


class CampaignCalendar(BaseModel):
    """The complete plan returned by the AI in one call.

    The router then splits this into `strategy` JSONB (everything except days)
    + `calendar` JSONB (days) for storage.

    Array length bounds are dropped from the AI-facing schema (see CalendarDay
    note). They are re-enforced post-parse in `generator.py`.
    """

    strategy: CampaignStrategy
    platforms: list[PlatformRecommendation]
    visual_direction: VisualDirectionHint
    sequence: list[CampaignSequence]
    days: list[CalendarDay]


def split_payload(payload: CampaignCalendar) -> tuple[dict[str, Any], list[dict[str, Any]]]:
    """Split the AI payload into (strategy-envelope dict, days list)."""
    dumped = payload.model_dump(mode="json")
    days = dumped.pop("days")
    return dumped, days


# ---------- API request / response ----------


class GenerateCampaignRequest(BaseModel):
    campaign_type: CampaignType
    duration_days: Literal[7, 14, 30]
    platforms: list[str] = Field(
        min_length=1,
        max_length=6,
        description="Subset of the user's preferred_platforms to use for this campaign.",
    )
    goal: str = Field(min_length=2, max_length=255)
    tone: str | None = Field(default=None, max_length=64)
    audience_override: str | None = Field(default=None, max_length=2000)
    landing_page_id: uuid.UUID | None = Field(
        default=None,
        description="Attach the whole campaign to a published lead page. Each "
        "calendar day will get its own attributed share URL "
        "(utm_content=day_N) so you can see which day drove which lead.",
    )

    # Phase S2.5 — neutralise prompt-injection markers before the
    # campaign composer splices these into the LLM prompt.
    @field_validator("goal", "audience_override", mode="before")
    @classmethod
    def _scrub_prompt_inputs(cls, v):
        return sanitize_prompt_input(v, field_name="campaign_request")


class UpdateCampaignRequest(BaseModel):
    is_saved: bool


class CampaignStrategyEnvelope(BaseModel):
    """Strategy envelope as stored — strategy + platforms + visual + sequence."""

    model_config = ConfigDict(extra="ignore")

    strategy: CampaignStrategy
    platforms: list[PlatformRecommendation]
    visual_direction: VisualDirectionHint
    sequence: list[CampaignSequence]


class CampaignPlanResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    user_id: str
    business_profile_id: uuid.UUID
    trend_report_id: uuid.UUID | None
    landing_page_id: uuid.UUID | None
    campaign_type: CampaignType
    duration_days: int
    goal: str
    tone: str
    strategy: CampaignStrategyEnvelope
    calendar: list[CalendarDay]
    # Per-day attributed share URLs, keyed by day number ("1", "7", "14").
    # Empty dict when no landing_page_id is attached.
    share_urls: dict[str, str] = Field(default_factory=dict)
    is_saved: bool
    created_at: datetime
    updated_at: datetime


class CampaignPlanList(BaseModel):
    items: list[CampaignPlanResponse]
