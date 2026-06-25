"""System + per-platform user prompt builders.

One SYSTEM_PROMPT, one `build_user_prompt`, four `_TYPE_INSTRUCTIONS`.
Everything else is shared via templates.py.
"""

from __future__ import annotations

from aicmo.copy.banned_phrases import TONE_GUARDRAILS
from aicmo.copy.creative_brief import CREATIVE_BRIEF_INSTRUCTION, render_recommendation_context_block
from aicmo.modules.ads.schemas import AdObjective, AdType, PLATFORM_BY_AD_TYPE
from aicmo.modules.ads.templates import (
    OBJECTIVE_INTENT,
    effective_tone,
    render_business_block,
    render_trend_block,
)
from aicmo.modules.context.builder import render_context_block
from aicmo.modules.context.schemas import GenerationContext
from aicmo.modules.onboarding.schemas import BusinessProfileResponse
from aicmo.modules.trends.schemas import TrendAnalysis

SYSTEM_PROMPT = (
    """You are a senior PERFORMANCE marketer running PAID acquisition. \
Your job is CLICKS and LEAD CAPTURE — not vanity engagement. Every ad must:
- Start with a complete `creative_brief` (objective, audience, hook, offer, cta, \
visual_direction, platform).
- Be PLATFORM-NATIVE — respect character limits, ad placement, native conventions.
- Earn the scroll in the first line / first 2 seconds. Lead with the strongest \
benefit, NEVER the brand name.
- Open a curiosity gap: the ad promises a specific payoff, the linked landing \
page delivers it. Do not give away the answer in the ad.
- Commit to ONE psychological trigger — urgency, fear-of-loss, status, savings, \
identity, curiosity, belonging, aspiration. Don't blend; pick the sharpest one.
- Tie back to a real trend or audience insight. Never fabricate stats, \
testimonials, or claims.
- Treat the CTA as the MOST important line in the ad. The CTA is verb-led, \
specific, and tied directly to the landing-page promise.
- For Meta ads: primary_text, headline, description must be paste-ready for Ads Manager.
- Suggest concrete targeting a media buyer can paste into ads manager — \
specificity beats reach.
- Include the strategy explanation the schema asks for. Be specific: name the trend, \
name the lever, name the funnel mechanic.

"""
    + CREATIVE_BRIEF_INSTRUCTION
    + "\n"
    + TONE_GUARDRAILS
)


_TYPE_INSTRUCTIONS: dict[AdType, str] = {
    "meta": (
        "Write a Meta ad (Facebook + Instagram feed). Primary text sweet-spot is "
        "~125 chars before the 'See more' cutoff — front-load the hook there. "
        "Headline ≤40 chars, description ≤30 chars. Use a sanctioned Meta CTA "
        "button. Provide 2-4 hook/headline VARIANTS for A/B testing — they must "
        "be genuinely different angles, not synonyms."
    ),
    "google_search": (
        "Write a Google Responsive Search Ad. Provide 5-15 UNIQUE headlines "
        "(≤30 chars each) and 2-4 UNIQUE descriptions (≤90 chars each). Each "
        "headline should stand alone — Google rotates them. Include a "
        "vanity display_path and 3-8 keyword_themes the buyer can build "
        "keyword lists from."
    ),
    "instagram_promo": (
        "Design a Story / Reel-style promo ad. Vertical format, sound-on assumed. "
        "Hook lands in the first 1-3 seconds. on_screen_text mirrors the visual "
        "overlays in narrative order. cta_sticker_text is short (≤24 chars) — "
        "it goes on the swipe-up / link sticker."
    ),
    "linkedin": (
        "Write a LinkedIn sponsored content ad. Professional voice. intro_text "
        "sweet-spot is ~150 chars before the 'see more' cutoff. Lead with the "
        "professional outcome (career growth, time saved, revenue, status). "
        "Use a sanctioned LinkedIn CTA button. professional_angle explains why "
        "this resonates with LinkedIn's audience specifically."
    ),
    "youtube": (
        "Write a YouTube video ad (in-stream / bumper). Hook lands in the "
        "first 5 seconds — assume the viewer can skip at 5s. Headline ≤40 "
        "chars (companion banner). primary_text doubles as the 6-15 second "
        "script outline. Use a sanctioned YouTube CTA button (e.g. "
        "'Learn more', 'Sign up'). Sound-on; visual-rich. Provide 2-3 hook "
        "variants — different opening angles, not synonyms."
    ),
}


def build_user_prompt(
    *,
    ad_type: AdType,
    objective: AdObjective,
    profile: BusinessProfileResponse,
    trend_analysis: TrendAnalysis | None,
    goal: str,
    tone_override: str | None,
    audience_override: str | None,
    context: GenerationContext | None = None,
    recommendation_context: str | None = None,
) -> str:
    tone = effective_tone(profile.brand_tone, tone_override)
    platform = PLATFORM_BY_AD_TYPE[ad_type]
    instructions = _TYPE_INSTRUCTIONS[ad_type]
    intent = OBJECTIVE_INTENT[objective]
    context_prefix = (
        render_context_block(context) + "\n\n" if context is not None else ""
    )
    rec_block = render_recommendation_context_block(recommendation_context)

    return f"""{context_prefix}{rec_block}# Task
Write a {ad_type.replace('_', ' ')} ad for {platform}.

Funnel objective: {objective} — {intent}
Campaign goal: {goal}
Voice to use: {tone}

{instructions}

# Business context
{render_business_block(profile, audience_override)}

# Trend context
{render_trend_block(trend_analysis)}

# Requirements
- The output must match the response schema exactly. Respect every character-length hint above.
- `strategy.trend_influence`: name the SPECIFIC trending topic / signal you used (or "none" if no report exists).
- `strategy.audience_angle`: name the SPECIFIC psychology lever (identity, status, savings, etc).
- `strategy.emotional_trigger`: ONE word for the dominant emotion (urgency, FOMO, aspiration, curiosity, status, savings, belonging).
- `strategy.conversion_strategy`: spell out the funnel mechanic — how this moves the viewer to act.
- `targeting`: concrete enough that a media buyer can paste it into ads manager.
"""
