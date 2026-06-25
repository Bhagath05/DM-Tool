"""Convert IntelligenceReport → OpportunityCenterReport (legacy UI contract)."""

from __future__ import annotations

import uuid

from aicmo.modules.advisor.schemas import (
    IntelligenceOpportunity,
    IntelligenceRecommendation,
    IntelligenceReport,
)
from aicmo.modules.opportunities.schemas import (
    GeneratorHint,
    Opportunity,
    OpportunityCenterReport,
    OpportunityHeroRecommendation,
    derive_opportunity_id,
)


def intelligence_to_opportunity_report(
    report: IntelligenceReport,
) -> OpportunityCenterReport:
    if not report.ready or not report.hero:
        empty = report.empty
        return OpportunityCenterReport(
            headline=empty.headline if empty else "Setup needed",
            hero_recommendation=OpportunityHeroRecommendation(
                what_is_happening=empty.message if empty else "Complete setup first.",
                impact_category="lead",
                recommendation=(
                    empty.suggested_setup_steps[0]
                    if empty and empty.suggested_setup_steps
                    else "Complete onboarding"
                ),
                expected_result="Unlock evidence-backed recommendations.",
                confidence=0,
                reason=empty.message if empty else "",
            ),
            content_opportunities=[],
            ad_opportunities=[],
            skip_for_now=[],
            signals_used=report.signals_used,
            generated_at=report.generated_at,
            advisor_ready=False,
            advisor_setup_steps=empty.suggested_setup_steps if empty else [],
        )

    hero = _to_hero(report.hero)
    content = [_to_opp(o, i) for i, o in enumerate(report.content_opportunities)]
    ads = [_to_opp(o, i) for i, o in enumerate(report.ad_opportunities)]

    return OpportunityCenterReport(
        headline="Your growth opportunities",
        hero_recommendation=hero,
        content_opportunities=content,
        ad_opportunities=ads,
        skip_for_now=[],
        signals_used=report.signals_used,
        generated_at=report.generated_at,
        advisor_ready=True,
        advisor_setup_steps=[],
    )


def _to_hero(rec: IntelligenceRecommendation) -> OpportunityHeroRecommendation:
    return OpportunityHeroRecommendation(
        what_is_happening=rec.observation,
        impact_category=rec.impact_category,
        recommendation=rec.recommended_action,
        expected_result=rec.expected_impact,
        confidence=rec.confidence,
        reason=rec.root_cause,
        task_status=rec.task_status,
    )


def _to_opp(opp: IntelligenceOpportunity, index: int) -> Opportunity:
    gen = _hint_from_raw(opp.generator_hint, opp.kind)
    rec_id = opp.recommendation_id or opp.id or derive_opportunity_id(
        kind=opp.kind,
        generator=gen,
        recommended_action=opp.recommended_action,
    )
    return Opportunity(
        id=rec_id if isinstance(rec_id, uuid.UUID) else uuid.UUID(str(rec_id)),
        kind=opp.kind,
        headline=opp.headline,
        what_is_happening=opp.observation,
        why_it_matters=opp.root_cause,
        recommended_action=opp.recommended_action,
        expected_result=opp.expected_impact,
        confidence=opp.confidence,
        reason=opp.root_cause,
        impact_category=opp.impact_category,
        evidence=[f"{d.label}: {d.value}" for d in opp.data_sources_used],
        generator=gen,
        task_status=opp.task_status,
    )


def _hint_from_raw(raw: dict | None, kind: str) -> GeneratorHint:
    if raw and "target" in raw:
        return GeneratorHint.model_validate(raw)
    if kind == "ad":
        return GeneratorHint(
            target="ad", format="meta", platform="Facebook", goal="Drive leads", objective="leads"
        )
    return GeneratorHint(
        target="content",
        format="social_post",
        platform="Instagram",
        goal="Drive engagement",
        objective=None,
    )
