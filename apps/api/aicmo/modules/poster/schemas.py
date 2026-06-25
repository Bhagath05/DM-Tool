"""Pydantic schemas for the LinkedIn poster studio.

The poster is MEANING-FIRST: a business-specific hero image (generated from
`image_concept`, which describes what the business actually does) is the
canvas, and the brand copy is composed on top in one of several distinct
layouts. There is deliberately NO fixed icon-diagram template — each post
should look different and reflect the work.
"""

from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, ConfigDict, Field

# A distinct visual treatment. The model picks one to keep a feed varied.
PosterLayout = Literal["editorial", "split", "banner"]
# Palette mood — used for accents when the brand has no colours of its own.
PosterPalette = Literal["warm", "cool", "bold", "mono"]
# The model decides photo vs illustration per topic (physical biz → photo,
# software/abstract → illustration).
ImageStyle = Literal["photo", "illustration"]


# ---------------------------------------------------------------------
#  LLM output — the structured copy + art direction for ONE post
# ---------------------------------------------------------------------


class LinkedInCopy(BaseModel):
    model_config = ConfigDict(extra="ignore")

    layout: PosterLayout = Field(
        default="editorial",
        description=(
            "editorial = full-bleed hero image with copy over a scrim (great "
            "for a single strong subject); split = image on one side, a brand "
            "panel with bullets on the other (great for services/offers); "
            "banner = image on top, content card below. Pick the best fit."
        ),
    )
    palette: PosterPalette = Field(
        default="bold",
        description="warm (food/lifestyle), cool (tech/pro-services), bold (energetic), mono (premium/minimal).",
    )
    image_style: ImageStyle = Field(
        default="photo",
        description="photo for real-world/physical businesses; illustration for software/finance/abstract concepts.",
    )
    image_concept: str = Field(
        max_length=600,
        description=(
            "A vivid description of ONE hero image that SHOWS what this "
            "business does, for an image model. Concrete subject, setting, "
            "light, mood. It must contain NO text, words, letters, or logos."
        ),
    )

    eyebrow: str = Field(max_length=24, description="Tiny uppercase kicker, e.g. 'THIS WEEKEND', 'NOW LIVE'.")
    headline_lead: str = Field(max_length=30, description="First part of the headline (plain).")
    headline_accent: str = Field(max_length=30, description="Second part, shown in the brand/accent colour.")
    subheadline: str = Field(max_length=170, description="One-line value prop.")
    cta: str = Field(default="", max_length=28, description="Short button label, e.g. 'Order for pickup'.")
    bullets: list[str] = Field(
        default_factory=list, max_length=3,
        description="0-3 short value points (≤32 chars). Used by split + banner layouts.",
    )

    post_body: str = Field(
        description=(
            "The LinkedIn caption itself — a real, professional write-up of "
            "120-260 words. Strong first line, 2-4 short paragraphs, a soft "
            "CTA question. Plain text with line breaks; NO markdown, NO hashtags."
        )
    )
    hashtags: list[str] = Field(
        default_factory=list, max_length=8,
        description="5-8 relevant hashtags WITHOUT the # (added on render).",
    )


# ---------------------------------------------------------------------
#  Theme — resolved tokens handed to the HTML template
# ---------------------------------------------------------------------


class PosterTheme(BaseModel):
    """Colour + identity tokens. Accents come from the brand kit when set,
    else from the chosen palette mood."""

    bg: str = "#05070b"
    ink: str = "#f5f7fb"
    muted: str = "#aab6c8"
    c1: str = "#34d399"   # accent start
    c2: str = "#a3e635"   # accent end / highlight
    c3: str = "#fcd34d"   # spare accent
    brand_name: str = "YOUR BRAND"
    website: str = ""
    logo_data_uri: str | None = None


# ---------------------------------------------------------------------
#  HTTP surface
# ---------------------------------------------------------------------


class LinkedInComposeRequest(BaseModel):
    topic: str = Field(min_length=3, max_length=400, description="What to announce / post about.")
    goal: str | None = Field(default=None, max_length=120, description="Optional angle, e.g. 'drive demo signups'.")
    generate_image: bool = Field(
        default=True,
        description="Generate the business-meaningful hero image (recommended). "
        "False = a fast branded gradient instead (no image-model cost).",
    )


class LinkedInRenderRequest(BaseModel):
    """Re-render after the user edits copy in the UI — no LLM call. Optionally
    regenerate the hero image from an (edited) image_concept."""

    fields: LinkedInCopy
    generate_image: bool = True


class LinkedInComposeResult(BaseModel):
    image_url: str = Field(description="Signed URL to the rendered PNG.")
    width: int
    height: int
    post_body: str
    hashtags: list[str]
    fields: LinkedInCopy
    rendered_id: str | None = Field(default=None, description="Storage key for re-fetch / publish.")
    used_ai_image: bool = Field(default=False, description="True if a generated hero image was used.")
