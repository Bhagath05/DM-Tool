from __future__ import annotations

import uuid
from datetime import datetime
from typing import Annotated, Any, Literal

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator

from aicmo.copy.creative_brief import MarketingCreativeBrief
from aicmo.security.prompt_safety import sanitize_prompt_input

ContentType = Literal["social_post", "reel", "carousel", "ad_copy", "landing_page_copy"]

CONTENT_TYPES: tuple[ContentType, ...] = (
    "social_post",
    "reel",
    "carousel",
    "ad_copy",
    "landing_page_copy",
)


# ---------- Shared "why-it-works" envelope ----------


class ContentStrategy(BaseModel):
    """The strategist explanation that ships with every generated piece.

    This is what makes the engine feel like an AI marketing strategist rather
    than a generic writer. Every type-specific schema below includes this.
    """

    trend_influence: str = Field(
        description="Which specific trend / signal from the report this leans on, "
        "or 'none — grounded in profile only' if no trends were available.",
    )
    audience_angle: str = Field(
        description="Which audience psychology lever this targets (FOMO, status, "
        "curiosity, identity, savings, belonging, etc.) and why it fits.",
    )
    strategy_note: str = Field(
        description="One short paragraph explaining why this piece will work for "
        "this business on this platform right now.",
    )


# ---------- Per-content-type AI output schemas ----------
# Each one nests ContentStrategy so we get strategy + content in ONE Gemini call.


class SocialPostFull(BaseModel):
    creative_brief: MarketingCreativeBrief
    strategy: ContentStrategy
    hook: str = Field(description="First line / opening that earns the scroll.")
    body: str = Field(description="Main post body, platform-native length.")
    hashtags: list[str] = Field(min_length=3, max_length=12)
    cta: str = Field(description="Primary CTA — verb-led, specific, ties to the landing-page promise.")
    cta_variants: list[str] = Field(
        default_factory=list,
        description="2-3 alternative CTA phrasings. Same intent as primary, different angles "
        "(curiosity / urgency / social proof / value reveal). For A/B testing.",
    )


class ReelBeat(BaseModel):
    label: str = Field(description="Beat label, e.g. 'Hook', 'Reveal', 'Payoff'.")
    description: str = Field(description="What happens visually in 1-2 sentences.")


class ReelFull(BaseModel):
    creative_brief: MarketingCreativeBrief
    strategy: ContentStrategy
    hook: str = Field(description="0-2 second hook script + visual.")
    beats: list[ReelBeat] = Field(min_length=3, max_length=6)
    voiceover_script: str = Field(
        min_length=20,
        description="Full voiceover narration — publish-ready for editor/TTS.",
    )
    on_screen_text: list[str] = Field(
        min_length=2, max_length=8, description="Captions/overlays in order."
    )
    caption: str
    hashtags: list[str] = Field(min_length=3, max_length=12)
    cta: str = Field(description="Primary CTA — verb-led, conversion-focused.")
    cta_variants: list[str] = Field(
        default_factory=list,
        description="2-3 alternative CTA phrasings for A/B testing.",
    )
    veo_prompt: str | None = Field(
        default=None,
        max_length=2000,
        description="Optional copy-paste video prompt for Veo / Runway-style tools.",
    )

    @model_validator(mode="before")
    @classmethod
    def _coerce_reel(cls, data: object) -> object:
        from aicmo.modules.content.normalize import normalize_content_payload

        if isinstance(data, dict):
            return normalize_content_payload("reel", data)
        return data


class CarouselSlide(BaseModel):
    title: str = Field(description="Slide headline — required on every slide.")
    body: str = Field(description="Slide body, max ~40 words.")
    image_prompt: str | None = Field(
        default=None,
        max_length=1500,
        description="Copy-paste image prompt for this slide (Flux, Midjourney, GPT Image).",
    )


class CarouselFull(BaseModel):
    creative_brief: MarketingCreativeBrief
    strategy: ContentStrategy
    cover_title: str = Field(description="Slide-1 cover that earns a swipe.")
    slides: list[CarouselSlide] = Field(min_length=4, max_length=10)
    cta_slide: CarouselSlide = Field(
        description="Final slide — dedicated CTA with headline + action copy."
    )
    caption: str
    hashtags: list[str] = Field(min_length=3, max_length=12)
    cta: str = Field(description="Primary CTA — verb-led, conversion-focused.")
    cta_variants: list[str] = Field(
        default_factory=list,
        description="2-3 alternative CTA phrasings for A/B testing.",
    )

    @model_validator(mode="before")
    @classmethod
    def _coerce_carousel(cls, data: object) -> object:
        from aicmo.modules.content.normalize import normalize_content_payload

        if isinstance(data, dict):
            return normalize_content_payload("carousel", data)
        return data


class LandingBenefit(BaseModel):
    title: str = Field(min_length=2, max_length=120)
    body: str = Field(min_length=10, max_length=400)


class LandingPageCopyFull(BaseModel):
    creative_brief: MarketingCreativeBrief
    strategy: ContentStrategy
    headline: str = Field(min_length=4, max_length=160)
    subheadline: str = Field(min_length=10, max_length=400)
    hero_paragraph: str = Field(
        min_length=20,
        max_length=800,
        description="Above-the-fold body copy — benefit-led, scannable.",
    )
    benefits: list[LandingBenefit] = Field(min_length=3, max_length=6)
    cta_text: str = Field(min_length=2, max_length=40)
    form_intro: str = Field(
        min_length=10,
        max_length=200,
        description="One line above the lead form.",
    )
    social_proof_line: str | None = Field(default=None, max_length=200)
    privacy_blurb: str | None = Field(default=None, max_length=200)

    @model_validator(mode="before")
    @classmethod
    def _coerce_landing(cls, data: object) -> object:
        from aicmo.modules.content.normalize import normalize_content_payload

        if isinstance(data, dict):
            return normalize_content_payload("landing_page_copy", data)
        return data


class AdCopyFull(BaseModel):
    creative_brief: MarketingCreativeBrief
    strategy: ContentStrategy
    headline: str = Field(description="Ad headline, ≤40 chars where possible.")
    primary_text: str = Field(description="Main ad body, conversion-focused.")
    description: str = Field(description="Short supporting line, ≤90 chars.")
    cta_button: str = Field(
        description="One of: Learn More, Shop Now, Sign Up, Get Quote, Book Now, "
        "Download, Subscribe, Contact Us, Get Offer."
    )
    targeting_note: str = Field(
        description="Who this ad should be targeted to (1-2 sentences)."
    )


# ---------- API request / response ----------

PRESET_GOALS: tuple[str, ...] = (
    "Drive engagement",
    "Build brand awareness",
    "Drive conversions / sales",
    "Educate the audience",
    "Promote a launch",
    "Grow email list",
    "Establish thought leadership",
)


class GenerateRequest(BaseModel):
    content_type: ContentType
    platform: str = Field(min_length=2, max_length=64)
    goal: str = Field(min_length=2, max_length=255)
    tone: str | None = Field(
        default=None,
        max_length=64,
        description="Override of the brand tone for this single piece.",
    )
    recommendation_context: str | None = Field(
        default=None,
        max_length=600,
        description="Optional intelligence recommendation observation + action.",
    )
    landing_page_id: uuid.UUID | None = Field(
        default=None,
        description="Attach this asset to a published lead page — the generated "
        "CTAs and share URL will point there with full attribution.",
    )

    # Phase S2.5 — sanitise free-text fields before the prompt composer.
    @field_validator("goal", "recommendation_context", mode="before")
    @classmethod
    def _scrub_prompt_inputs(cls, v):
        return sanitize_prompt_input(v, field_name="content_request")


class UpdateRequest(BaseModel):
    is_saved: bool


class GeneratedContentResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    user_id: str
    business_profile_id: uuid.UUID
    trend_report_id: uuid.UUID | None
    landing_page_id: uuid.UUID | None
    content_type: ContentType
    platform: str
    goal: str
    tone: str
    strategy: ContentStrategy
    # Free-form dict because the shape depends on content_type. The frontend
    # branches on content_type to render the right component.
    output: dict[str, Any]
    # Computed at response time — landing-page URL with UTM + attribution.
    # None if no landing page is attached.
    share_url: str | None = None
    is_saved: bool
    created_at: datetime
    updated_at: datetime


class GeneratedContentList(BaseModel):
    items: list[GeneratedContentResponse]


# Dispatch table consumed by generator.py — keeps content_type → schema in one place.
SCHEMA_BY_TYPE: dict[ContentType, type[BaseModel]] = {
    "social_post": SocialPostFull,
    "reel": ReelFull,
    "carousel": CarouselFull,
    "ad_copy": AdCopyFull,
    "landing_page_copy": LandingPageCopyFull,
}


# Used to split the AI's nested response into strategy + output for storage.
def split_strategy(
    content_type: ContentType, payload: BaseModel
) -> tuple[ContentStrategy, dict[str, Any]]:
    dumped = payload.model_dump(mode="json")
    strategy = ContentStrategy.model_validate(dumped.pop("strategy"))
    return strategy, dumped


# Re-export so the router can use the alias in OpenAPI.
GeneratedAt = Annotated[datetime, Field(description="Server-assigned timestamp.")]
