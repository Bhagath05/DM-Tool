"""Campaign-planner prompts.

System prompt frames the model as a senior growth strategist building a
plan that humans will execute — NOT a list of pre-baked posts. The
calendar entries are briefs, not generated assets.
"""

from __future__ import annotations

from aicmo.copy.banned_phrases import TONE_GUARDRAILS
from aicmo.modules.campaigns.schemas import (
    CAMPAIGN_INTENT,
    CONTENT_TYPES,
    CampaignType,
)
from aicmo.modules.campaigns.templates import (
    effective_tone,
    render_business_block,
    render_trend_block,
)
from aicmo.modules.context.builder import render_context_block
from aicmo.modules.context.schemas import GenerationContext
from aicmo.modules.onboarding.schemas import BusinessProfileResponse
from aicmo.modules.trends.schemas import TrendAnalysis

SYSTEM_PROMPT = (
    """You are a senior growth marketing strategist + performance \
marketer building a campaign plan a real human team will execute. Your north star \
is LEADS captured and revenue moved — not vanity engagement.

Discipline:
- The calendar is a BRIEF, not a list of finished posts. Each day's `hook`, \
`cta`, and `visual_direction_summary` are starting points the team will refine.
- Sequence days into clear funnel phases — name them, justify them, attach \
metrics. Random posting is not a plan.
- Ground every recommendation in either a real trend signal or the business \
profile. Never invent statistics, customer counts, or marketing benchmarks.
- Posting cadence must be realistic — most teams cannot ship a polished reel \
daily. Match cadence to team capacity implied by the goal.
- Paid-media recommendations are optional. If a day doesn't warrant ad support, \
write 'none' in `recommended_ad_support` — do not pad.

CTA + conversion rules (apply to every day's `cta` and to `cta_progression`):
- CTAs are verb-led, specific, tied to a concrete payoff the audience earns by \
clicking. The audience is going to a LANDING PAGE that captures their info — \
the CTA must promise something the landing page can credibly deliver.
- Use concrete outcome language ("Grab the playbook", "Reserve your tasting", \
"Get the 7-day plan").
- `cta_progression` must escalate intent across phases: early-phase soft asks \
(saves, follows, comments) → mid-phase value reveals (free guide, waitlist) → \
late-phase hard asks (book, buy, claim).
- Every day's `hook` must open a CURIOSITY GAP: the post promises a payoff, \
the landing page delivers it. Don't give the answer away in the post.

"""
    + TONE_GUARDRAILS
)


def build_user_prompt(
    *,
    campaign_type: CampaignType,
    duration_days: int,
    platforms: list[str],
    goal: str,
    tone_override: str | None,
    audience_override: str | None,
    profile: BusinessProfileResponse,
    trend_analysis: TrendAnalysis | None,
    context: GenerationContext | None = None,
) -> str:
    tone = effective_tone(profile.brand_tone, tone_override)
    intent = CAMPAIGN_INTENT[campaign_type]
    platforms_str = ", ".join(platforms)
    content_types_str = ", ".join(CONTENT_TYPES)
    context_prefix = (
        render_context_block(context) + "\n\n" if context is not None else ""
    )

    return f"""{context_prefix}# Task
Build a {duration_days}-day {campaign_type.replace('_', ' ')} campaign plan.

Campaign intent: {intent}
Top-level goal: {goal}
Voice across the campaign: {tone}
Platforms to use (only these): {platforms_str}

# Hard constraints
- `days` array MUST contain EXACTLY {duration_days} entries, day numbers 1..{duration_days}, in order.
- Each day's `platform` MUST be one of: {platforms_str}.
- Each day's `content_type` MUST be one of: {content_types_str}.
- `sequence` MUST cover the full {duration_days} days via its `day_range` fields, with 3-5 phases.
- `recommended_ad_support` is the literal string 'none' unless a paid recommendation genuinely makes sense.

# Business context
{render_business_block(profile, audience_override)}

# Trend context
{render_trend_block(trend_analysis)}

# Quality bar
- Distinctive `campaign_theme` — not a category label.
- Funnel phases progress logically (awareness → consideration → conversion is one shape; pick what fits the campaign type).
- Visual direction is brand-coherent across the campaign — same aesthetic, same palette direction.
- Each day's `rationale` explains why this slot exists in this phase. Not generic.
"""
