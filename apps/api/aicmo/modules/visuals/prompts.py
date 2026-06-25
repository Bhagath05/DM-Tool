"""Visual-brief prompts.

The system prompt frames the model as a creative director writing a brief for
a designer — NOT as an image generator. Per-type instructions encode the
craft-specific concerns (mobile legibility for thumbnails, swipe-rhythm for
carousels, sound-on assumptions for reels, etc.).
"""

from __future__ import annotations

from aicmo.copy.banned_phrases import TONE_GUARDRAILS
from aicmo.copy.creative_brief import CREATIVE_BRIEF_INSTRUCTION, render_recommendation_context_block
from aicmo.modules.context.builder import render_context_block
from aicmo.modules.context.schemas import GenerationContext
from aicmo.modules.onboarding.schemas import BusinessProfileResponse
from aicmo.modules.trends.schemas import TrendAnalysis
from aicmo.modules.visuals.schemas import VisualType
from aicmo.modules.visuals.templates import (
    effective_tone,
    render_business_block,
    render_trend_block,
)

SYSTEM_PROMPT = (
    """You are a senior creative director PLUS performance marketer. \
You write tight, actionable visual briefs that an in-house designer (or a marketer \
in Canva / Figma) can execute without further questions — AND every brief is built \
to drive CLICKS and LEAD CAPTURE, not just look pretty.

Discipline:
- Start with a complete `creative_brief` — it drives headline, benefits, CTA, and image prompts.
- Every choice (colour, type, composition, CTA placement) is justified by audience \
psychology, brand tone, or a real trend signal. Never decorative.
- The visual earns the scroll in <2 seconds. Hero element, contrast, and motion \
do the heavy lifting before any text is read.
- Open a curiosity gap — the visual hints at the payoff that the linked landing \
page delivers. Don't reveal the whole story on the asset.
- Colours are concrete: name + 6-character hex code + the role that colour plays.
- Typography is concrete: a style description PLUS 2-4 real font names a designer \
can actually pick (Inter, IBM Plex Sans, Playfair Display, Söhne, etc).
- Composition principle is named explicitly (rule of thirds, leading lines, \
golden ratio, frame within frame, negative space, symmetry, etc).
- CTA treatment is THE most important visual decision. For ad creative / poster: \
fill headline, subheadline, benefits[], cta_copy, AND ai_image_prompt.
- `ai_image_prompt` must be copy-paste ready for GPT Image, Midjourney, Flux, or Ideogram. \
Describe subject, scene, lighting, lens, mood — explicitly NO text/letters in the image.
- For `cta_placement`, describe ONLY the visual ZONE and TREATMENT — never embed literal overlay text.
- Tie the visual back to the funnel goal in `conversion_rationale` — be specific \
about how the layout earns the click / save / purchase.

"""
    + CREATIVE_BRIEF_INSTRUCTION
    + "\n"
    + TONE_GUARDRAILS
)


_TYPE_INSTRUCTIONS: dict[VisualType, str] = {
    "ad_creative": (
        "Brief a POSTER / static ad creative for paid or organic placement. "
        "Required copy fields: headline, subheadline, benefits (3-5 bullets), cta_copy. "
        "Required: ai_image_prompt — full generative image prompt, NO text in image. "
        "Pick platform-native aspect (1:1, 4:5, or 1.91:1). "
        "Fill mobile_readability_note, overlay_text_max_words, safe_text_margin."
    ),
    "carousel": (
        "Brief an Instagram / LinkedIn carousel. Cover must earn the swipe in <1s. "
        "Define a DESIGN SYSTEM (palette + typography) that all slides share, then "
        "per-slide visuals that hold visual continuity. Number of slide_designs "
        "should match the narrative — 4-10 slides. Transitions describe how each "
        "slide visually leads to the next."
    ),
    "reel": (
        "Brief a vertical short-form video (Reel / Short / TikTok). Aspect 9:16, "
        "sound-on assumed but design for sound-off legibility too. Scenes are "
        "timestamped. shot_type / framing / motion give the editor concrete "
        "direction. color_grading sets the overall mood; music_visual_sync says "
        "how visuals match audio beats / drops."
    ),
    "thumbnail": (
        "Brief a single thumbnail (YouTube 16:9 typical, podcast 1:1). It must "
        "pop in a feed of competitors. contrast_strategy is the lever — colour, "
        "scale, light, isolation, face-expression. text_overlay max 3-5 words "
        "(or 'none' if visual carries it). End with a mobile_legibility_note "
        "confirming readability at thumb-size."
    ),
}


def build_user_prompt(
    *,
    visual_type: VisualType,
    profile: BusinessProfileResponse,
    trend_analysis: TrendAnalysis | None,
    platform: str,
    goal: str,
    tone_override: str | None,
    context: GenerationContext | None = None,
    recommendation_context: str | None = None,
) -> str:
    tone = effective_tone(profile.brand_tone, tone_override)
    instructions = _TYPE_INSTRUCTIONS[visual_type]
    context_prefix = (
        render_context_block(context) + "\n\n" if context is not None else ""
    )
    rec_block = render_recommendation_context_block(recommendation_context)

    return f"""{context_prefix}{rec_block}# Task
Write a {visual_type.replace('_', ' ')} brief for {platform}.

Funnel goal: {goal}
Voice to use: {tone}

{instructions}

# Business context
{render_business_block(profile)}

# Trend context
{render_trend_block(trend_analysis)}

# Requirements
- Output must match the response schema exactly.
- Hex codes for every colour. Real font names for typography.
- `strategy.composition_principle`: name a SPECIFIC compositional rule.
- `strategy.conversion_rationale`: tie the visual to the goal "{goal}" — be specific.
- `strategy.trend_influence`: name the SPECIFIC trend/signal that informs the aesthetic, or "none".
- Mood keywords and aesthetic references should be vivid and concrete — never "modern, clean, professional".
"""
