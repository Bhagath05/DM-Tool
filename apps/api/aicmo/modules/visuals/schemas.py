from __future__ import annotations

import uuid
from datetime import datetime
from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator

from aicmo.copy.creative_brief import MarketingCreativeBrief
from aicmo.modules.visuals.render_schemas import RenderedVisualResponse
from aicmo.security.prompt_safety import sanitize_prompt_input

# ---------- enums ----------

VisualType = Literal["ad_creative", "carousel", "reel", "thumbnail"]

VISUAL_TYPES: tuple[VisualType, ...] = (
    "ad_creative",
    "carousel",
    "reel",
    "thumbnail",
)

PRESET_GOALS: tuple[str, ...] = (
    "Drive engagement",
    "Build brand awareness",
    "Drive conversions / sales",
    "Educate the audience",
    "Promote a launch",
    "Grow email list",
    "Establish thought leadership",
)


# ---------- shared building blocks (reused across all 4 schemas) ----------


class ColorSwatch(BaseModel):
    """A single color a designer can drop straight into Figma / Canva."""

    name: str = Field(description="Descriptive name, e.g. 'warm terracotta'.")
    hex: str = Field(
        pattern=r"^#[0-9a-fA-F]{6}$",
        description="6-character hex code with leading #.",
    )
    role: str = Field(description="primary | accent | background | text | highlight")


class TypographyHint(BaseModel):
    style: str = Field(
        description="Voice in one phrase, e.g. 'editorial serif', 'geometric sans'."
    )
    headline_treatment: str = Field(
        description="How headlines should be set — weight, tracking, case, scale."
    )
    body_treatment: str = Field(
        description="How body copy should be set."
    )
    suggested_fonts: list[str] = Field(
        min_length=2,
        max_length=4,
        description="Concrete font names (free or common — Inter, IBM Plex, Playfair, etc).",
    )


class VisualStrategy(BaseModel):
    """The strategist explanation that ships with every visual brief.

    Two extra fields versus ads' AdStrategy: `composition_principle` and
    `conversion_rationale` — visual-specific levers.
    """

    visual_concept: str = Field(
        description="One sentence summarising the overall visual idea."
    )
    emotional_trigger: str = Field(
        description="The dominant emotion the visual targets — calm, urgency, "
        "aspiration, identity, status, curiosity."
    )
    audience_angle: str = Field(
        description="Which audience psychology lever the visual targets and why."
    )
    trend_influence: str = Field(
        description="Specific trend / signal that informs the aesthetic, or 'none'."
    )
    composition_principle: str = Field(
        description="Compositional rule applied — rule of thirds, leading lines, "
        "golden ratio, frame within frame, negative space, symmetry."
    )
    conversion_rationale: str = Field(
        description="Short paragraph on how the visual choices drive the funnel goal."
    )


_STRATEGY_FIELD_DEFAULTS: dict[str, str] = {
    "emotional_trigger": "Not recorded",
    "audience_angle": "Not recorded",
    "trend_influence": "none",
    "composition_principle": "Not recorded",
    "conversion_rationale": "Not recorded",
}


def normalize_visual_strategy(strategy: dict[str, Any] | None) -> dict[str, Any]:
    """Back-fill legacy/partial strategy JSONB so list endpoints never 500.

    Companion visuals created by ad auto-render only stored
    `visual_concept`; older rows may be missing any subset of fields.
    """
    raw = dict(strategy or {})
    concept = raw.get("visual_concept") or "Generated visual"
    merged = {**_STRATEGY_FIELD_DEFAULTS, "visual_concept": concept, **raw}
    return merged


def ad_strategy_to_visual_strategy(
    ad_strategy: dict[str, Any],
    *,
    visual_concept: str,
) -> dict[str, Any]:
    """Map ad strategy fields onto the visual strategy shape for companion rows."""
    return {
        "visual_concept": visual_concept,
        "emotional_trigger": ad_strategy.get("emotional_trigger") or "Not recorded",
        "audience_angle": ad_strategy.get("audience_angle") or "Not recorded",
        "trend_influence": ad_strategy.get("trend_influence") or "none",
        "composition_principle": "centered commercial composition",
        "conversion_rationale": (
            ad_strategy.get("conversion_strategy")
            or ad_strategy.get("why_it_works")
            or "Supports the ad creative render."
        ),
    }


# ---------- per-visual-type schemas ----------


class AdCreativeBriefFull(BaseModel):
    creative_brief: MarketingCreativeBrief
    strategy: VisualStrategy
    headline: str = Field(description="Poster/ad headline — bold, ≤8 words.")
    subheadline: str = Field(description="Supporting line under headline.")
    benefits: list[str] = Field(
        min_length=3,
        max_length=5,
        description="3-5 bullet benefits — specific outcomes, not generic.",
    )
    cta_copy: str = Field(description="Button/overlay CTA text.")
    aspect_ratio: str = Field(
        description="Platform-native aspect, e.g. '1:1' (feed), '4:5' (mobile feed), '1.91:1' (link)."
    )
    focal_subject: str = Field(
        description="What the hero element is — product, person, scene, abstract."
    )
    composition_layout: str = Field(
        description="Layout shape — centered, asymmetric, split-screen, full-bleed, etc."
    )
    color_palette: list[ColorSwatch] = Field(min_length=3, max_length=6)
    typography: TypographyHint
    visual_hierarchy: list[str] = Field(
        min_length=3,
        max_length=5,
        description="Ordered: what the eye sees first, second, third.",
    )
    cta_placement: str = Field(
        description="Where + how the CTA sits — corner, bar, button shape, contrast."
    )
    mood_keywords: list[str] = Field(min_length=3, max_length=6)
    reference_aesthetic: str = Field(
        description="Aesthetic comparison — 'editorial like X', 'energetic like Y'."
    )
    # Phase 4-A — performance-render hints. Optional so legacy briefs still
    # parse; the prompt asks new generations to fill them so the renderer
    # has explicit guidance on overlay zones, text caps, mobile legibility.
    mobile_readability_note: str | None = Field(
        default=None,
        description="One sentence on how the visual stays legible on a 6-inch phone in feed.",
    )
    overlay_text_max_words: int | None = Field(
        default=None,
        description="Max words for any single text overlay zone — usually 3-6 for paid social.",
    )
    safe_text_margin: str | None = Field(
        default=None,
        description="Where text MUST NOT go because of platform UI chrome (e.g. 'bottom 18% for IG story').",
    )
    ai_image_prompt: str = Field(
        min_length=50,
        max_length=2000,
        description=(
            "Complete copy-paste prompt for GPT Image, Midjourney, Flux, or Ideogram. "
            "Describe scene, lighting, subject, camera, mood — NO text in image."
        ),
    )


class CarouselSlideDesign(BaseModel):
    slide_number: int = Field(ge=1)
    visual: str = Field(description="What appears visually on this slide.")
    text_treatment: str = Field(description="How any text on the slide is set.")
    transition_to_next: str = Field(
        description="How this slide visually connects to the next."
    )


class CarouselPlanFull(BaseModel):
    creative_brief: MarketingCreativeBrief
    strategy: VisualStrategy
    aspect_ratio: str = Field(description="'1:1' or '4:5'.")
    cover_concept: str = Field(description="Visual concept for slide 1 — earns the swipe.")
    design_system_palette: list[ColorSwatch] = Field(min_length=3, max_length=6)
    design_system_typography: TypographyHint
    slide_designs: list[CarouselSlideDesign] = Field(min_length=4, max_length=10)
    cta_slide_concept: str = Field(
        description="Visual design for the final CTA slide."
    )


class ReelScene(BaseModel):
    scene_number: int = Field(ge=1)
    timestamp_range: str = Field(description="e.g. '0-2s', '2-5s'.")
    shot_type: str = Field(description="close-up, wide, POV, product hero, etc.")
    framing: str = Field(description="How the subject is framed.")
    motion: str = Field(description="Static, slow push-in, fast cuts, whip pan, etc.")
    overlay_text: str = Field(description="Text overlay shown (or 'none').")


class ReelPlanFull(BaseModel):
    creative_brief: MarketingCreativeBrief
    strategy: VisualStrategy
    aspect_ratio: str = Field(description="Always '9:16'.")
    visual_style: str = Field(
        description="Overall aesthetic — cinematic, lo-fi, fast cuts, soft pastel, etc."
    )
    scenes: list[ReelScene] = Field(min_length=3, max_length=6)
    text_overlay_style: TypographyHint
    music_visual_sync: str = Field(
        description="How visuals match the audio energy / beat drops."
    )
    color_grading: str = Field(
        description="Overall colour treatment — warm, desaturated, high-contrast, etc."
    )


class ThumbnailConceptFull(BaseModel):
    creative_brief: MarketingCreativeBrief
    strategy: VisualStrategy
    aspect_ratio: str = Field(description="'16:9' typical for YouTube; '1:1' for podcasts.")
    focal_subject: str = Field(description="Face (with expression), product, or scene.")
    contrast_strategy: str = Field(
        description="How the thumbnail pops in a feed — colour, light, scale, isolation."
    )
    text_overlay: str = Field(
        description="Maximum 3-5 words. Optional — say 'none' if the visual carries it."
    )
    typography: TypographyHint
    background_treatment: str = Field(
        description="Solid, gradient, blur, illustration, photo, duotone, etc."
    )
    mobile_legibility_note: str = Field(
        description="One sentence confirming legibility at thumbnail-feed size."
    )


SCHEMA_BY_TYPE: dict[VisualType, type[BaseModel]] = {
    "ad_creative": AdCreativeBriefFull,
    "carousel": CarouselPlanFull,
    "reel": ReelPlanFull,
    "thumbnail": ThumbnailConceptFull,
}


def split_payload(payload: BaseModel) -> tuple[VisualStrategy, dict[str, Any]]:
    dumped = payload.model_dump(mode="json")
    strategy = VisualStrategy.model_validate(dumped.pop("strategy"))
    return strategy, dumped


# ---------- API request / response ----------


class GenerateVisualRequest(BaseModel):
    visual_type: VisualType
    platform: str = Field(min_length=2, max_length=64)
    goal: str = Field(min_length=2, max_length=255)
    tone: str | None = Field(default=None, max_length=64)
    recommendation_context: str | None = Field(default=None, max_length=600)
    landing_page_id: uuid.UUID | None = Field(
        default=None,
        description="Attach the visual brief to a published lead page — the "
        "share URL on the response will point there with full attribution.",
    )

    # Phase S2.5 — sanitise free-text fields before the prompt composer.
    @field_validator("goal", "recommendation_context", mode="before")
    @classmethod
    def _scrub_prompt_inputs(cls, v):
        return sanitize_prompt_input(v, field_name="visual_request")


class UpdateVisualRequest(BaseModel):
    is_saved: bool


class GeneratedVisualResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    user_id: str
    business_profile_id: uuid.UUID
    trend_report_id: uuid.UUID | None
    landing_page_id: uuid.UUID | None
    visual_type: VisualType
    platform: str
    goal: str
    tone: str
    strategy: VisualStrategy
    output: dict[str, Any]
    share_url: str | None = None
    is_saved: bool
    created_at: datetime
    updated_at: datetime
    renders: list[RenderedVisualResponse] = Field(default_factory=list)
    primary_signed_url: str | None = None
    thumbnail_url: str | None = None

    @model_validator(mode="before")
    @classmethod
    def _normalize_legacy_strategy(cls, data: Any) -> Any:
        if isinstance(data, dict):
            if "strategy" in data:
                data = {**data, "strategy": normalize_visual_strategy(data["strategy"])}
            return data
        strategy = getattr(data, "strategy", None)
        if strategy is not None or hasattr(data, "visual_type"):
            # ORM row — pydantic from_attributes reads attrs; patch strategy first.
            return {
                "id": data.id,
                "user_id": data.user_id,
                "business_profile_id": data.business_profile_id,
                "trend_report_id": data.trend_report_id,
                "landing_page_id": data.landing_page_id,
                "visual_type": data.visual_type,
                "platform": data.platform,
                "goal": data.goal,
                "tone": data.tone,
                "strategy": normalize_visual_strategy(strategy),
                "output": data.output,
                "is_saved": data.is_saved,
                "created_at": data.created_at,
                "updated_at": data.updated_at,
            }
        return data


class GeneratedVisualList(BaseModel):
    items: list[GeneratedVisualResponse]
