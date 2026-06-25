"""Reusable prompt fragments for the campaigns module.

Duplicated from sibling modules per the self-contained-module convention.
If a 5th generation module adds this same trio, lift to a shared
aicmo/llm/context.py.
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
        f"Audience for this campaign:\n{audience}"
    )


def render_trend_block(analysis: TrendAnalysis | None) -> str:
    if analysis is None:
        return "(No trend report yet — ground the campaign in the business profile only.)"

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
