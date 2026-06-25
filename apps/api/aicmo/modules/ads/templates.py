"""Reusable prompt fragments for the ads module.

Kept separate from prompts.py so per-platform prompts can compose business +
trend context without duplication.

Note: this duplicates a few helpers from `modules/content/templates.py` on
purpose — feature modules should be self-contained per CLAUDE.md. If a
third generation module lands, the right move is to lift these into a
shared `aicmo/llm/context.py` rather than chain imports across features.
"""

from __future__ import annotations

from aicmo.modules.onboarding.schemas import BusinessProfileResponse
from aicmo.modules.trends.schemas import TrendAnalysis


def render_business_block(
    profile: BusinessProfileResponse, audience_override: str | None
) -> str:
    competitors = ", ".join(profile.competitors) or "(none provided)"
    goals = "; ".join(profile.goals)
    audience = (
        audience_override.strip()
        if audience_override and audience_override.strip()
        else profile.target_audience
    )
    return (
        f"Business: {profile.business_name}\n"
        f"Industry: {profile.industry}\n"
        f"Brand tone (baseline): {profile.brand_tone}\n"
        f"Competitors: {competitors}\n"
        f"Business goals: {goals}\n\n"
        f"Audience for this ad:\n{audience}"
    )


def render_trend_block(analysis: TrendAnalysis | None) -> str:
    if analysis is None:
        return "(No trend report yet — ground this ad in the business profile only.)"

    topics = "\n".join(
        f"- {t.topic} (relevance {t.relevance_score}): {t.why_it_matters}"
        for t in analysis.trending_topics[:5]
    )
    angles = "\n".join(f"- {a}" for a in analysis.marketing_angles[:4])
    return (
        f"Trend landscape: {analysis.summary}\n\n"
        f"Top trending topics:\n{topics}\n\n"
        f"Marketing angles to lean into:\n{angles}"
    )


def effective_tone(profile_tone: str, override: str | None) -> str:
    return override.strip() if override and override.strip() else profile_tone


# Human-readable copy for each objective. Keeps the prompt grounded in funnel intent.
OBJECTIVE_INTENT: dict[str, str] = {
    "awareness": "Maximise top-of-funnel reach and recall. Memorability over clicks.",
    "traffic": "Drive clicks to a destination. Curiosity hooks beat hard sells.",
    "engagement": "Earn comments, saves, shares. Conversation starters.",
    "leads": "Capture a name + email / phone. Promise the value exchange clearly.",
    "app_installs": "Drive store installs. Show the in-app payoff in the first second.",
    "conversions": "Trigger a specific on-site action (signup, demo, free trial).",
    "sales": "Direct revenue. Lead with offer, social proof, urgency.",
}
