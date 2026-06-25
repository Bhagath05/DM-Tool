from __future__ import annotations

import uuid
from datetime import datetime
from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field, field_validator

from aicmo.copy.creative_brief import MarketingCreativeBrief
from aicmo.security.prompt_safety import sanitize_prompt_input

# ---------- type-system enums ----------

AdType = Literal["meta", "google_search", "instagram_promo", "linkedin", "youtube"]

AD_TYPES: tuple[AdType, ...] = (
    "meta",
    "google_search",
    "instagram_promo",
    "linkedin",
    "youtube",
)

# Platform shown in UI + stored in DB. Derived from ad_type.
PLATFORM_BY_AD_TYPE: dict[AdType, str] = {
    "meta": "Facebook / Instagram (Meta)",
    "google_search": "Google Search",
    "instagram_promo": "Instagram",
    "linkedin": "LinkedIn",
    "youtube": "YouTube",
}

AdObjective = Literal[
    "awareness",
    "traffic",
    "engagement",
    "leads",
    "app_installs",
    "conversions",
    "sales",
]

AD_OBJECTIVES: tuple[AdObjective, ...] = (
    "awareness",
    "traffic",
    "engagement",
    "leads",
    "app_installs",
    "conversions",
    "sales",
)

# Preset campaign-goal chips for the UI (separate from the funnel objective).
PRESET_GOALS: tuple[str, ...] = (
    "Drive sales",
    "Generate qualified leads",
    "Launch a new product",
    "Build brand awareness",
    "Drive app installs",
    "Re-engage past customers",
    "Promote a limited-time offer",
)


# ---------- shared "why-it-works" envelope ----------


class AdStrategy(BaseModel):
    """Strategist explanation that ships with every ad.

    Two extra fields versus content's ContentStrategy: `emotional_trigger`
    and `conversion_strategy`. Paid media buyers think in those terms.
    """

    trend_influence: str = Field(
        description="Specific trend / signal that informed this ad, or 'none' if no trends were available."
    )
    audience_angle: str = Field(
        description="Audience psychology lever (identity, status, savings, belonging, curiosity, etc.) and why it fits."
    )
    emotional_trigger: str = Field(
        description="The single dominant emotion this ad targets — urgency, fear-of-loss, aspiration, curiosity, status, savings, belonging."
    )
    conversion_strategy: str = Field(
        description="One short paragraph on the funnel mechanic — how this ad moves the viewer to act."
    )


# ---------- targeting ----------


class AdTargeting(BaseModel):
    """Concrete targeting hints a media buyer can paste into ads manager."""

    audience_description: str = Field(
        description="One-sentence description of WHO this ad should be put in front of."
    )
    interests: list[str] = Field(
        min_length=3,
        max_length=10,
        description="Interest categories (e.g. 'specialty coffee', 'minimalist design').",
    )
    demographics: list[str] = Field(
        min_length=2,
        max_length=6,
        description="Age range / location / income / role hints.",
    )
    behaviors: list[str] = Field(
        min_length=2,
        max_length=6,
        description="Purchase intent or behavioural signals — e.g. 'frequent online shoppers', 'small-business owners'.",
    )


# ---------- per-platform output schemas ----------
# Each one nests AdStrategy + AdTargeting so one Gemini call returns everything.


class MetaAdVariant(BaseModel):
    hook: str = Field(description="Alt opening line for A/B testing.")
    headline: str = Field(description="Alt headline (≤40 chars where possible).")


class MetaAdFull(BaseModel):
    creative_brief: MarketingCreativeBrief
    strategy: AdStrategy
    targeting: AdTargeting
    primary_text: str = Field(
        description="Main ad body. ~125-char sweet spot before 'See more' cutoff."
    )
    headline: str = Field(description="Headline (≤40 chars where possible).")
    description: str = Field(description="Short supporting line (≤30 chars where possible).")
    cta_button: str = Field(
        description=(
            "One of Meta's sanctioned CTA buttons: Learn More, Shop Now, Sign Up, "
            "Book Now, Download, Get Quote, Contact Us, Subscribe, Apply Now, "
            "Send Message, See Menu."
        )
    )
    creative_direction: str = Field(
        description="1-2 sentence brief for the designer — what the visual should show."
    )
    variants: list[MetaAdVariant] = Field(
        min_length=2,
        max_length=4,
        description="Alt hook/headline pairs for A/B testing.",
    )


class GoogleSearchAdFull(BaseModel):
    creative_brief: MarketingCreativeBrief
    strategy: AdStrategy
    targeting: AdTargeting
    headlines: list[str] = Field(
        min_length=5,
        max_length=15,
        description="Unique headlines, each ≤30 chars. Google rotates these in RSA.",
    )
    descriptions: list[str] = Field(
        min_length=2,
        max_length=4,
        description="Unique descriptions, each ≤90 chars.",
    )
    display_path: str = Field(
        description="Vanity URL path shown under the headline — e.g. 'product-launch'."
    )
    keyword_themes: list[str] = Field(
        min_length=3,
        max_length=8,
        description="Keyword themes to bid on. Don't include match-type symbols.",
    )


class InstagramPromoAdFull(BaseModel):
    creative_brief: MarketingCreativeBrief
    strategy: AdStrategy
    targeting: AdTargeting
    hook: str = Field(description="First 1-3 seconds — what stops the thumb-scroll.")
    caption: str = Field(description="Caption shown alongside the Story / Reel.")
    on_screen_text: list[str] = Field(
        min_length=2,
        max_length=6,
        description="Text overlays in narrative order.",
    )
    cta_sticker_text: str = Field(
        description="Short CTA for the sticker/swipe overlay (≤24 chars)."
    )
    cta_variants: list[str] = Field(
        default_factory=list,
        description="2-3 alternative CTA sticker phrasings for A/B testing.",
    )
    creative_direction: str = Field(
        description="Visual brief — what's on screen, pacing, transitions."
    )
    music_mood: str = Field(
        description="Music vibe to use — energy, genre, tempo."
    )


class LinkedinAdFull(BaseModel):
    creative_brief: MarketingCreativeBrief
    strategy: AdStrategy
    targeting: AdTargeting
    intro_text: str = Field(
        description="Sponsored content body. ~150 chars before 'see more' cutoff."
    )
    headline: str = Field(description="Headline beneath the image (≤70 chars).")
    description: str = Field(
        description="Short supporting line (≤100 chars). Optional on LinkedIn but improves CTR."
    )
    cta_button: str = Field(
        description=(
            "One of LinkedIn's sanctioned CTAs: Apply Now, Download, Get Quote, "
            "Learn More, Sign Up, Subscribe, Register, Attend, Request Demo."
        )
    )
    creative_direction: str = Field(
        description="Visual brief for the design team."
    )
    professional_angle: str = Field(
        description="Why this resonates with LinkedIn's professional audience specifically — role-level, career outcome, business context."
    )


class YouTubeAdHookVariant(BaseModel):
    """One opening-hook variant for the YouTube ad — A/B fodder."""

    hook: str = Field(description="0-5s opening line (assume skip at 5s).")
    angle: str = Field(description="Why this hook works for this audience.")


class YouTubeAdFull(BaseModel):
    creative_brief: MarketingCreativeBrief
    strategy: AdStrategy
    targeting: AdTargeting
    headline: str = Field(description="Companion banner headline (≤40 chars).")
    primary_text: str = Field(
        description="6-15 second script outline (the body of the ad)."
    )
    description: str = Field(description="Short supporting line (≤90 chars).")
    cta_button: str = Field(
        description=(
            "Sanctioned YouTube CTA: Learn More, Sign Up, Shop Now, Watch, "
            "Subscribe, Apply Now, Get Quote, Download, Visit Site."
        )
    )
    hook_variants: list[YouTubeAdHookVariant] = Field(
        description="2-3 distinct opening hooks. Each is a different angle, not synonyms.",
    )
    creative_direction: str = Field(
        description="Visual + motion brief for the video team."
    )
    video_format: str = Field(
        description="Format hint: in_stream / bumper / shorts."
    )


SCHEMA_BY_TYPE: dict[AdType, type[BaseModel]] = {
    "meta": MetaAdFull,
    "google_search": GoogleSearchAdFull,
    "instagram_promo": InstagramPromoAdFull,
    "linkedin": LinkedinAdFull,
    "youtube": YouTubeAdFull,
}


def split_payload(payload: BaseModel) -> tuple[AdStrategy, AdTargeting, dict[str, Any]]:
    """Split the AI's nested output into the three columns we store."""
    dumped = payload.model_dump(mode="json")
    strategy = AdStrategy.model_validate(dumped.pop("strategy"))
    targeting = AdTargeting.model_validate(dumped.pop("targeting"))
    return strategy, targeting, dumped


# ---------- API request / response ----------


class GenerateAdRequest(BaseModel):
    ad_type: AdType
    objective: AdObjective
    goal: str = Field(min_length=2, max_length=255)
    tone: str | None = Field(default=None, max_length=64)
    recommendation_context: str | None = Field(default=None, max_length=600)
    audience_override: str | None = Field(
        default=None,
        max_length=2000,
        description="Override of the audience description from the business profile.",
    )
    landing_page_id: uuid.UUID | None = Field(
        default=None,
        description="Attach this ad to a published lead page — the share URL "
        "will point there with full attribution.",
    )

    # Phase S2.5 — sanitise free-text fields before they reach the LLM
    # prompt builder. Returns None unchanged.
    @field_validator("goal", "audience_override", "recommendation_context", mode="before")
    @classmethod
    def _scrub_prompt_inputs(cls, v):
        return sanitize_prompt_input(v, field_name="ad_request")


class UpdateAdRequest(BaseModel):
    is_saved: bool


class GeneratedAdResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    user_id: str
    business_profile_id: uuid.UUID
    trend_report_id: uuid.UUID | None
    landing_page_id: uuid.UUID | None
    ad_type: AdType
    platform: str
    objective: AdObjective
    goal: str
    tone: str
    strategy: AdStrategy
    targeting: AdTargeting
    output: dict[str, Any]
    share_url: str | None = None
    is_saved: bool
    created_at: datetime
    updated_at: datetime
    rendered_visual_id: uuid.UUID | None = None
    primary_image_url: str | None = None


class GeneratedAdList(BaseModel):
    items: list[GeneratedAdResponse]
