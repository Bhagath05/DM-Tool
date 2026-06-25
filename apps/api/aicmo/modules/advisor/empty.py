"""Honest empty states — no fake template recommendations."""

from __future__ import annotations

from datetime import UTC, datetime

from aicmo.modules.opportunities.schemas import (
    OpportunityCenterReport,
    OpportunityHeroRecommendation,
)


def build_empty_opportunity_report(
    *,
    message: str,
    setup_steps: list[str],
    signals: list[str],
) -> OpportunityCenterReport:
    hero = OpportunityHeroRecommendation(
        what_is_happening=message,
        impact_category="lead",
        recommendation="Complete the setup steps below to unlock personalized recommendations.",
        expected_result="Once activity data exists, recommendations will cite your real metrics.",
        confidence=0,
        reason="Insufficient business activity data to generate specific advice.",
        task_status=None,
    )
    return OpportunityCenterReport(
        headline=message,
        hero_recommendation=hero,
        content_opportunities=[],
        ad_opportunities=[],
        skip_for_now=setup_steps[:5],
        signals_used=signals,
        generated_at=datetime.now(UTC).isoformat(),
        advisor_ready=False,
        advisor_setup_steps=setup_steps,
    )
