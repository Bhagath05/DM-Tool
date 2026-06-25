"""Per-content-type prompts.

All four prompts share the same system instruction and the same context
fragments (business + trends) — only the task-specific section and the
output schema differ.
"""

from __future__ import annotations

from aicmo.copy.banned_phrases import TONE_GUARDRAILS
from aicmo.copy.creative_brief import CREATIVE_BRIEF_INSTRUCTION, render_recommendation_context_block
from aicmo.modules.content.schemas import ContentType
from aicmo.modules.content.templates import (
    effective_tone,
    render_business_block,
    render_trend_block,
)
from aicmo.modules.context.builder import render_context_block
from aicmo.modules.context.schemas import GenerationContext
from aicmo.modules.onboarding.schemas import BusinessProfileResponse
from aicmo.modules.trends.schemas import TrendAnalysis

SYSTEM_PROMPT = (
    """You are a senior PERFORMANCE marketer and agency copywriter generating \
native, platform-aware content optimised for CLICKS and LEAD CAPTURE — not vanity \
engagement. Every piece must:
- Start with a complete `creative_brief` (objective, audience, hook, offer, cta, \
visual_direction, platform) — the brief drives all copy below.
- Earn the scroll in the first line / first 2 seconds.
- Open a curiosity gap: the post promises a payoff, the linked landing page \
delivers it.
- Sound like the brand's tone, not generic AI copy.
- Tie back to a real trend or audience insight (no fabrications).
- Treat the CTA as the most important line in the piece. The CTA is verb-led, \
specific, and tied directly to the landing-page promise. Use concrete \
outcome language ("Get the 10-min playbook", "Snag the free template").
- Provide 2-3 CTA variants in `cta_variants` — same intent as the primary, \
different angles (curiosity / urgency / social proof / value reveal). For \
A/B testing.
- Include the strategy explanation the schema asks for — that's how the user \
trusts the piece, so be specific (name the trend, name the lever).

"""
    + CREATIVE_BRIEF_INSTRUCTION
    + "\n"
    + TONE_GUARDRAILS
)


_TYPE_INSTRUCTIONS: dict[ContentType, str] = {
    "social_post": (
        "Write ONE platform-native social post. Match the platform's typical "
        "length and rhythm. Hashtags should mix broad + niche; avoid spammy "
        "stacks. The CTA must be specific (not 'check the link in bio')."
    ),
    "reel": (
        "Design a short-form video (Reel / Short / TikTok). Hook in 0-2 seconds. "
        "Beats are scene-by-scene direction with label + description. "
        "`voiceover_script` is the FULL narration an editor can record or TTS. "
        "on_screen_text mirrors overlays (max 8 lines). Caption goes below the video. "
        "Optional `veo_prompt`: one copy-paste generative video prompt for Veo."
    ),
    "carousel": (
        "Design a carousel (Instagram / LinkedIn). Cover earns the swipe. "
        "Every slide MUST have `title` (headline) AND `body`. "
        "Include `image_prompt` per slide — copy-paste ready for GPT Image / Flux / Midjourney. "
        "Include a dedicated `cta_slide` as the final slide. 4-10 content slides plus CTA."
    ),
    "landing_page_copy": (
        "Write landing page copy that converts cold traffic to leads. "
        "headline + subheadline above the fold, hero_paragraph, 3-6 benefits, "
        "cta_text for the button, form_intro above the form. "
        "Align every line with the creative_brief offer and CTA."
    ),
    "ad_copy": (
        "Write paid ad copy (Meta / Google). Lead with the strongest benefit. "
        "Use a sanctioned CTA button label. targeting_note tells the marketer "
        "who to put this in front of."
    ),
}


def build_user_prompt(
    *,
    content_type: ContentType,
    profile: BusinessProfileResponse,
    trend_analysis: TrendAnalysis | None,
    platform: str,
    goal: str,
    tone_override: str | None,
    context: GenerationContext | None = None,
    recommendation_context: str | None = None,
) -> str:
    tone = effective_tone(profile.brand_tone, tone_override)
    instructions = _TYPE_INSTRUCTIONS[content_type]
    context_prefix = (
        render_context_block(context) + "\n\n" if context is not None else ""
    )
    rec_block = render_recommendation_context_block(recommendation_context)

    return f"""{context_prefix}{rec_block}# Task
Generate a {content_type.replace('_', ' ')} for {platform}.

Campaign goal: {goal}
Voice to use: {tone}

{instructions}

# Business context
{render_business_block(profile)}

# Trend context
{render_trend_block(trend_analysis)}

# Requirements
- The platform field of the request was: {platform}. Use platform-native conventions.
- Output must match the response schema exactly.
- Fill `strategy.trend_influence` with the SPECIFIC topic/signal you used (or "none" if no trends were available).
- Fill `strategy.audience_angle` with the SPECIFIC psychology lever (FOMO, status, identity, curiosity, savings, belonging, etc).
"""
