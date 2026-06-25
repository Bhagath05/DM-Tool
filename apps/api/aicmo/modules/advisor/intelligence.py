"""Intelligence Engine — single grounded composer for recommendations."""

from __future__ import annotations

import uuid
from datetime import UTC, datetime

import structlog
from pydantic import BaseModel, Field
from sqlalchemy.ext.asyncio import AsyncSession

from aicmo.config import get_settings
from aicmo.llm import get_llm_router
from aicmo.llm.providers.base import LLMMessage
from aicmo.modules.advisor.signals import (
    IntelligenceSignals,
    gather_intelligence_signals,
    has_minimum_evidence,
    signals_to_prompt_block,
)
from aicmo.modules.advisor.dedupe import (
    fingerprint_for_hero,
    fingerprint_for_opportunity,
    recommendation_id_from_fingerprint,
)
from aicmo.modules.advisor.schemas import (
    AdvisorEmptyPlan,
    DailyBrief,
    DataSourceRef,
    IntelligenceOpportunity,
    IntelligenceRecommendation,
    IntelligenceReport,
)
from aicmo.modules.advisor.prompts import INTELLIGENCE_SYSTEM_PROMPT
from aicmo.modules.advisor import service as advisor_service
from aicmo.modules.analytics import service as analytics_service
from aicmo.modules.onboarding.schemas import BusinessProfileResponse
from aicmo.modules.opportunities.schemas import GeneratorHint
from aicmo.tenancy.context import TenantContext

log = structlog.get_logger()


class _NarrativeRec(BaseModel):
    observation: str = Field(min_length=10)
    root_cause: str = Field(min_length=10)
    recommended_action: str = Field(min_length=10)
    expected_impact: str = Field(min_length=10)
    confidence: int = Field(ge=0, le=100)
    data_sources_used: list[DataSourceRef] = Field(min_length=1)
    impact_category: str = "lead"
    generator_hint: dict | None = None


class _NarrativeOpp(_NarrativeRec):
    kind: str = "content"
    headline: str = Field(min_length=5)


class _IntelligenceNarrative(BaseModel):
    daily_brief_what_happened: str = Field(min_length=10)
    daily_brief_why: str = Field(min_length=10)
    daily_brief_confidence: int = Field(ge=0, le=100)
    hero: _NarrativeRec
    content_opportunities: list[_NarrativeOpp] = Field(default_factory=list, max_length=5)
    ad_opportunities: list[_NarrativeOpp] = Field(default_factory=list, max_length=3)
    trend: _NarrativeRec | None = None


def _confidence_cap(
    *,
    has_outcomes: bool,
    has_connectors: bool,
    has_content_intel: bool,
    has_lead_intel: bool,
    activity_signals: int,
) -> int:
    if has_outcomes and has_connectors and has_content_intel:
        return 95
    if has_outcomes and (has_connectors or has_content_intel):
        return 85
    if has_outcomes:
        return 75
    if has_connectors and has_content_intel:
        return 70
    if has_lead_intel and activity_signals >= 1:
        return 65
    if activity_signals >= 2:
        return 60
    return 55


def _clamp_confidence(value: int, cap: int) -> int:
    return max(0, min(value, cap))


async def compose_intelligence(
    session: AsyncSession,
    *,
    profile: BusinessProfileResponse,
    tenant: TenantContext,
) -> IntelligenceReport:
    settings = get_settings()
    now = datetime.now(UTC)
    generated_at = now.isoformat()

    ctx = await gather_intelligence_signals(
        session, profile=profile, brand_id=tenant.brand_id
    )

    if not ctx.brain_complete:
        return IntelligenceReport(
            ready=False,
            empty=AdvisorEmptyPlan(
                headline="Complete your Business Brain",
                message="We need your industry and target audience before generating recommendations.",
                suggested_setup_steps=ctx.setup_steps or ["Complete business onboarding"],
                signals_used=["business_brain"],
                generated_at=generated_at,
            ),
            generated_at=generated_at,
        )

    cap = _confidence_cap(
        has_outcomes=ctx.has_outcomes,
        has_connectors=ctx.has_connectors,
        has_content_intel=ctx.has_content_intel,
        has_lead_intel=ctx.has_lead_intel,
        activity_signals=ctx.activity_signals,
    )

    if not has_minimum_evidence(ctx):
        steps = list(ctx.setup_steps)
        providers = ctx.connector_context.get("connected_providers") or []
        if not any(p.startswith("instagram") for p in providers):
            steps.append("Connect Instagram")
        if "google_business_profile" not in providers:
            steps.append("Connect Google Business Profile")
        if ctx.activity_signals == 0:
            steps.append("Publish a lead page and share its link")
        if not ctx.has_content_intel:
            steps.append("Generate and publish your first piece of content")
        # Deduplicate while preserving order
        seen: set[str] = set()
        unique_steps: list[str] = []
        for s in steps:
            if s not in seen:
                seen.add(s)
                unique_steps.append(s)
        steps = unique_steps
        return IntelligenceReport(
            ready=False,
            empty=AdvisorEmptyPlan(
                headline="Not enough activity data yet",
                message="We have your business profile but no measurable marketing activity to analyze.",
                suggested_setup_steps=steps,
                signals_used=ctx.analytics_signals,
                generated_at=generated_at,
            ),
            generated_at=generated_at,
            confidence_cap=cap,
        )

    if not settings.advisor_intelligence_enabled:
        return IntelligenceReport(
            ready=False,
            empty=AdvisorEmptyPlan(
                headline="Intelligence engine disabled",
                message="The intelligence engine is not enabled in this environment.",
                suggested_setup_steps=[],
                signals_used=ctx.analytics_signals,
                generated_at=generated_at,
            ),
            generated_at=generated_at,
        )

    user_prompt = signals_to_prompt_block(ctx, confidence_cap=cap)

    try:
        router = get_llm_router()
        result = await router.generate(
            response_schema=_IntelligenceNarrative,
            system=INTELLIGENCE_SYSTEM_PROMPT,
            messages=[LLMMessage(role="user", content=user_prompt)],
            temperature=0.5,
            max_tokens=5000,
        )
        narrative = result.data
    except Exception as e:
        log.warning("advisor.intelligence_llm_failed", error=str(e))
        overview = await analytics_service.overview(session, brand_id=tenant.brand_id)
        return _deterministic_report(
            ctx=ctx,
            overview=overview,
            cap=cap,
            generated_at=generated_at,
        )

    daily_brief = DailyBrief(
        what_happened=narrative.daily_brief_what_happened,
        why_it_happened=narrative.daily_brief_why,
        confidence=_clamp_confidence(narrative.daily_brief_confidence, cap),
        data_sources_used=_merge_data_sources(
            narrative.hero.data_sources_used,
            ctx.data_sources,
        ),
    )

    hero = _to_intelligence_rec(narrative.hero, cap=cap)
    content = [
        _to_intelligence_opp(o, cap=cap, default_kind="content")
        for o in narrative.content_opportunities[:5]
    ]
    ads = [
        _to_intelligence_opp(o, cap=cap, default_kind="ad")
        for o in narrative.ad_opportunities[:3]
    ]
    trend = _to_intelligence_rec(narrative.trend, cap=cap) if narrative.trend else None

    if tenant and settings.advisor_engine_enabled:
        hero, content, ads = await _persist_intelligence(
            session,
            tenant=tenant,
            hero=hero,
            content=content,
            ads=ads,
            trend=trend,
        )

    return IntelligenceReport(
        ready=True,
        hero=hero,
        content_opportunities=content,
        ad_opportunities=ads,
        trend=trend,
        daily_brief=daily_brief,
        signals_used=ctx.analytics_signals,
        confidence_cap=cap,
        generated_at=generated_at,
    )


def _normalize_generator_hint(
    raw: dict | GeneratorHint | None,
    *,
    default_target: str = "content",
    default_format: str | None = None,
) -> dict:
    """Fill required GeneratorHint fields when the LLM omits them."""
    if raw is None:
        hint: dict = {}
    elif isinstance(raw, GeneratorHint):
        return raw.model_dump(mode="json")
    else:
        hint = dict(raw)
    target = hint.get("target") or default_target
    hint["target"] = target
    if not hint.get("format"):
        if default_format:
            hint["format"] = default_format
        elif target == "visual":
            hint["format"] = "ad_creative"
        elif target == "content":
            hint["format"] = "carousel"
        else:
            hint["format"] = "instagram_promo"
    if not hint.get("goal"):
        hint["goal"] = "Drive qualified leads"
    return hint


def _metric_value(ctx: IntelligenceSignals, provider: str, key: str) -> float | None:
    for m in ctx.connector_context.get("metrics") or []:
        if m.get("provider") == provider and m.get("key") == key:
            return float(m["value"])
    return None


def _deterministic_report(
    *,
    ctx: IntelligenceSignals,
    overview,
    cap: int,
    generated_at: str,
) -> IntelligenceReport:
    """Honest fallback from real metrics only — no LLM."""
    brain = ctx.brain
    data_sources = list(ctx.data_sources[:8]) or [
        DataSourceRef(key="leads_7d", label="Leads (7 days)", value=str(overview.leads_7d)),
    ]

    ig_reach = _metric_value(ctx, "instagram_organic", "reach_28d")
    ig_engagement = _metric_value(ctx, "instagram_organic", "engagement_rate")
    gbp_calls = _metric_value(ctx, "google_business_profile", "call_clicks")
    gbp_directions = _metric_value(ctx, "google_business_profile", "direction_requests")

    success = (ctx.outcome_context.get("recent_outcomes") or [])[:1]
    success_title = success[0]["title"] if success else None
    success_delta = success[0].get("delta_summary") if success else None

    content_insights = ctx.content_intelligence.get("insights") or []
    winning_line = content_insights[0] if content_insights else None

    hot = overview.hot_leads
    what_parts = [
        f"{overview.total_leads} leads in pipeline ({hot} hot, {overview.leads_7d} in last 7 days)",
    ]
    if ig_reach is not None:
        what_parts.append(f"Instagram reach {int(ig_reach):,} (28d)")
    if gbp_calls is not None:
        what_parts.append(f"GBP phone clicks {int(gbp_calls)}")
    if gbp_directions is not None:
        what_parts.append(f"GBP direction requests {int(gbp_directions)}")
    what = ". ".join(what_parts) + "."

    why_parts: list[str] = []
    if success_delta and success_title:
        why_parts.append(
            f"Historical outcome: '{success_title}' — {success_delta}"
        )
    if winning_line:
        why_parts.append(winning_line)
    if ig_engagement is not None and ig_reach:
        why_parts.append(
            f"Instagram engagement rate is {ig_engagement:.1%} on {int(ig_reach):,} reach — "
            f"content is reaching {brain.target_audience[:80]} but pipeline needs action."
        )
    if gbp_calls and gbp_directions and gbp_calls < gbp_directions / 2:
        why_parts.append(
            "Google Business Profile shows strong walk-in intent (direction requests) "
            "but fewer phone calls — local prospects research before calling."
        )
    if not why_parts:
        why_parts.append(
            "Lead volume reflects current marketing activity for "
            f"{brain.business_name or 'this business'} in {brain.location or 'your market'}."
        )
    why = " ".join(why_parts)

    follow_up = ctx.lead_context.get("follow_up_priority")
    if hot > 0 and success_title:
        hero_action = (
            f"{follow_up or f'Call {hot} hot lead(s) today'}. "
            f"Then repeat the proven '{success_title}' format while "
            f"{brain.growth_goal or 'intake deadlines'} are active."
        )
    elif hot > 0:
        hero_action = follow_up or f"Contact {hot} hot lead(s) before launching new campaigns."
    elif ig_reach and ig_reach > 3000:
        hero_action = (
            "Publish a deadline-driven Instagram carousel targeting your top destination "
            f"({', '.join(brain.preferred_platforms[:1]) or 'Instagram'}) — "
            "historical saves outperform single-image posts."
        )
    else:
        hero_action = "Publish and share your lead capture page to start converting local search interest."

    hero = IntelligenceRecommendation(
        observation=what,
        root_cause=why,
        recommended_action=hero_action,
        expected_impact=(
            "Convert existing hot pipeline and repeat a historically successful content format "
            "rather than generic posting."
            if success_title
            else "Move highest-intent prospects forward using channels already producing reach."
        ),
        confidence=min(65 if ctx.has_outcomes and ctx.has_connectors else 50, cap),
        data_sources_used=data_sources,
        impact_category="lead",
        generator_hint=_normalize_generator_hint(
            {
                "target": "content",
                "format": "carousel",
                "platform": "Instagram",
                "goal": brain.growth_goal or "Drive qualified counselling bookings",
            }
        ),
    )

    content_opps: list[IntelligenceOpportunity] = []
    if ctx.has_content_intel or ig_reach:
        content_opps.append(
            IntelligenceOpportunity(
                kind="content",
                headline="Repeat winning carousel format",
                observation=what,
                root_cause=why,
                recommended_action=(
                    "Create a UK/Canada intake checklist carousel using the hook pattern "
                    "from your top-performing historical post."
                ),
                expected_impact="Higher saves and counselling DMs based on prior +8 lead window.",
                confidence=min(60, cap),
                data_sources_used=data_sources[:5],
                impact_category="lead",
                generator_hint=_normalize_generator_hint(
                    {
                        "target": "content",
                        "format": "carousel",
                        "platform": "Instagram",
                        "goal": "UK intake checklist — drive counselling DMs",
                    }
                ),
            )
        )
        content_opps.append(
            IntelligenceOpportunity(
                kind="content",
                headline="Canada PNP explainer reel",
                observation=what,
                root_cause=why,
                recommended_action=(
                    "Produce a short reel comparing PNP vs Express Entry for 6.5 IELTS profiles — "
                    "your second-highest reach format historically."
                ),
                expected_impact="Reach warm leads researching Canada pathways.",
                confidence=min(55, cap),
                data_sources_used=data_sources[:5],
                impact_category="lead",
                generator_hint=_normalize_generator_hint(
                    {
                        "target": "content",
                        "format": "reel",
                        "platform": "Instagram",
                        "goal": "Canada PNP vs Express Entry explainer",
                    }
                ),
            )
        )

    ad_opps: list[IntelligenceOpportunity] = []
    if overview.hot_leads > 0 or gbp_calls:
        ad_opps.append(
            IntelligenceOpportunity(
                kind="ad",
                headline="Retarget hot leads + local search",
                observation=what,
                root_cause=why,
                recommended_action=(
                    "Run an Instagram lead ad promoting a free counselling slot, "
                    "geo-targeted to Hyderabad, while GBP call clicks are active."
                ),
                expected_impact="Convert hot pipeline and local search intent into booked sessions.",
                confidence=min(58, cap),
                data_sources_used=data_sources[:5],
                impact_category="lead",
                generator_hint=_normalize_generator_hint(
                    {
                        "target": "ad",
                        "format": "instagram_promo",
                        "objective": "leads",
                        "goal": "Book free UK/Canada counselling session",
                    },
                    default_target="ad",
                ),
            )
        )

    return IntelligenceReport(
        ready=True,
        hero=hero,
        content_opportunities=content_opps,
        ad_opportunities=ad_opps,
        daily_brief=DailyBrief(
            what_happened=what,
            why_it_happened=why,
            confidence=min(60 if ctx.has_outcomes else 45, cap),
            data_sources_used=data_sources,
        ),
        signals_used=ctx.analytics_signals,
        confidence_cap=cap,
        generated_at=generated_at,
    )


def _merge_data_sources(
    *source_lists: list,
) -> list[DataSourceRef]:
    seen: set[str] = set()
    out: list[DataSourceRef] = []
    for lst in source_lists:
        for item in lst or []:
            if isinstance(item, DataSourceRef):
                ref = item
            elif isinstance(item, dict):
                ref = DataSourceRef(**item)
            else:
                continue
            if ref.key not in seen:
                seen.add(ref.key)
                out.append(ref)
    return out


_VALID_IMPACT_CATEGORIES = frozenset({"revenue", "lead", "customer", "time", "cost"})


def _to_intelligence_rec(rec: _NarrativeRec, *, cap: int) -> IntelligenceRecommendation:
    hint = _normalize_generator_hint(rec.generator_hint)
    impact = rec.impact_category if rec.impact_category in _VALID_IMPACT_CATEGORIES else "lead"
    return IntelligenceRecommendation(
        observation=rec.observation,
        root_cause=rec.root_cause,
        recommended_action=rec.recommended_action,
        expected_impact=rec.expected_impact,
        confidence=_clamp_confidence(rec.confidence, cap),
        data_sources_used=rec.data_sources_used,
        impact_category=impact,  # type: ignore[arg-type]
        generator_hint=hint,
    )


def _to_intelligence_opp(
    opp: _NarrativeOpp, *, cap: int, default_kind: str = "content"
) -> IntelligenceOpportunity:
    kind = opp.kind if opp.kind in ("content", "ad") else default_kind
    hint = _normalize_generator_hint(
        opp.generator_hint,
        default_target="ad" if kind == "ad" else "content",
    )
    impact = opp.impact_category if opp.impact_category in _VALID_IMPACT_CATEGORIES else "lead"
    return IntelligenceOpportunity(
        kind=kind,  # type: ignore[arg-type]
        headline=opp.headline,
        observation=opp.observation,
        root_cause=opp.root_cause,
        recommended_action=opp.recommended_action,
        expected_impact=opp.expected_impact,
        confidence=_clamp_confidence(opp.confidence, cap),
        data_sources_used=opp.data_sources_used,
        impact_category=impact,  # type: ignore[arg-type]
        generator_hint=hint,
    )


async def _persist_intelligence(
    session: AsyncSession,
    *,
    tenant: TenantContext,
    hero: IntelligenceRecommendation,
    content: list[IntelligenceOpportunity],
    ads: list[IntelligenceOpportunity],
    trend: IntelligenceRecommendation | None,
) -> tuple[
    IntelligenceRecommendation,
    list[IntelligenceOpportunity],
    list[IntelligenceOpportunity],
]:
    hero_fp = fingerprint_for_hero(hero.recommended_action)
    hero_id = recommendation_id_from_fingerprint(hero_fp)
    hero_row = await advisor_service.upsert_intelligence_rec(
        session,
        tenant=tenant,
        rec_id=hero_id,
        fingerprint=hero_fp,
        rec=hero,
        source_surface="intelligence_hero",
        title="Today's top action",
    )
    hero = hero.model_copy(
        update={"id": hero_row.id, "recommendation_id": hero_row.id, "task_status": hero_row.status}
    )

    new_content: list[IntelligenceOpportunity] = []
    for opp in content:
        gen = GeneratorHint.model_validate(opp.generator_hint) if opp.generator_hint else GeneratorHint(
            target="content", format="social_post", goal="Drive engagement"
        )
        fp = fingerprint_for_opportunity(
            kind=opp.kind, generator=gen, recommended_action=opp.recommended_action
        )
        rec_id = recommendation_id_from_fingerprint(fp)
        hint_dict = gen.model_dump(mode="json")
        row = await advisor_service.upsert_intelligence_rec(
            session,
            tenant=tenant,
            rec_id=rec_id,
            fingerprint=fp,
            rec=opp.model_copy(update={"generator_hint": hint_dict}),
            source_surface="intelligence_content",
            title=opp.headline,
        )
        new_content.append(
            opp.model_copy(
                update={
                    "id": row.id,
                    "recommendation_id": row.id,
                    "task_status": row.status,
                    "generator_hint": hint_dict,
                }
            )
        )

    new_ads: list[IntelligenceOpportunity] = []
    for opp in ads:
        gen = GeneratorHint.model_validate(opp.generator_hint) if opp.generator_hint else GeneratorHint(
            target="ad", format="meta", goal="Drive leads", objective="leads"
        )
        fp = fingerprint_for_opportunity(
            kind=opp.kind, generator=gen, recommended_action=opp.recommended_action
        )
        rec_id = recommendation_id_from_fingerprint(fp)
        hint_dict = gen.model_dump(mode="json")
        row = await advisor_service.upsert_intelligence_rec(
            session,
            tenant=tenant,
            rec_id=rec_id,
            fingerprint=fp,
            rec=opp.model_copy(update={"generator_hint": hint_dict}),
            source_surface="intelligence_ad",
            title=opp.headline,
        )
        new_ads.append(
            opp.model_copy(
                update={
                    "id": row.id,
                    "recommendation_id": row.id,
                    "task_status": row.status,
                    "generator_hint": hint_dict,
                }
            )
        )

    if trend:
        fp = fingerprint_for_hero(f"trend:{trend.recommended_action}")
        rec_id = recommendation_id_from_fingerprint(fp)
        await advisor_service.upsert_intelligence_rec(
            session,
            tenant=tenant,
            rec_id=rec_id,
            fingerprint=fp,
            rec=trend,
            source_surface="intelligence_trend",
            title="Trend to act on",
        )

    await session.commit()
    return hero, new_content, new_ads
