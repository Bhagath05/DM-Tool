"""Shared marketing creative brief — every generator fills this first."""

from __future__ import annotations

from pydantic import BaseModel, Field, field_validator

# The CTA length the brief contract targets. OpenAI structured outputs ignore
# string maxLength, so an over-length CTA is fitted to this deterministically
# (see MarketingCreativeBrief._fit_cta_to_max) rather than failing validation.
_CTA_MAX_LEN = 80


class MarketingCreativeBrief(BaseModel):
    """Agency-style brief. Required on every production asset generation."""

    objective: str = Field(
        min_length=10,
        max_length=300,
        description="What this asset must achieve — one measurable marketing outcome.",
    )
    audience: str = Field(
        min_length=10,
        max_length=400,
        description="Who this is for — role, location, mindset, buying stage.",
    )
    hook: str = Field(
        min_length=5,
        max_length=160,
        description="Scroll-stop opening line or visual hook.",
    )
    offer: str = Field(
        min_length=5,
        max_length=200,
        description="What the viewer gets — specific, not vague 'great service'.",
    )
    cta: str = Field(
        min_length=2,
        max_length=_CTA_MAX_LEN,
        description="Primary call to action — verb-led, landing-page aligned.",
    )
    visual_direction: str = Field(
        min_length=10,
        max_length=500,
        description="Art direction: scene, mood, composition, what to show/avoid.",
    )
    platform: str = Field(
        min_length=2,
        max_length=64,
        description="Target platform and placement, e.g. 'Instagram feed 4:5'.",
    )

    @field_validator("cta", mode="before")
    @classmethod
    def _fit_cta_to_max(cls, v: object) -> object:
        """Fit an over-length CTA to the brief contract instead of failing.

        OpenAI structured outputs ignore string maxLength, so GPT can return a
        CTA longer than `_CTA_MAX_LEN`. Trim to <=80 at a word boundary so the
        brief stays valid without cutting mid-word. The published post CTA
        (`SocialPostFull.cta`) is a separate, unconstrained field and is
        untouched."""
        if not isinstance(v, str) or len(v) <= _CTA_MAX_LEN:
            return v
        head = v[:_CTA_MAX_LEN].rstrip()
        boundary = head.rfind(" ")
        if boundary >= 60:  # keep a clean word boundary unless it over-trims
            head = head[:boundary]
        # Strip trailing ASCII + unicode dash punctuation after the cut.
        return head.rstrip(" ,.;:!-").rstrip("\u2013\u2014")


CREATIVE_BRIEF_INSTRUCTION = """\
# Creative brief (REQUIRED — fill `creative_brief` FIRST)
Every output MUST include a complete `creative_brief` with ALL seven fields:
objective, audience, hook, offer, cta, visual_direction, platform.
Write like an agency strategist briefing a designer and copywriter.
The brief drives every headline, slide, scene, and image prompt below it.

# Agency quality bar
- Specific to THIS business and audience — never generic SaaS/marketing speak.
- Copy is publish-ready: a media buyer could paste primary text / headlines today.
- Image prompts are copy-paste ready for GPT Image, Midjourney, Flux, Ideogram, or Veo.
- No placeholder brackets like [Business Name] or [Insert offer].
"""


def render_recommendation_context_block(context: str | None) -> str:
    """Optional intelligence/recommendation context injected into prompts."""
    if not context or not context.strip():
        return ""
    return f"""# Recommendation context (ground the brief in this)
{context.strip()[:600]}

"""
