"""Opportunity Center orchestrator — Phase 6.

Single read-only entry point. Pulls every relevant signal
deterministically, hands them to the LLM which writes the strategist
narrative + per-card recommendations, then wraps the result with
derived ids + signals.

Failure policy: identical to Reality Engine / Weekly Plan / Lead
Intelligence — the founder ALWAYS gets a usable report. A failing LLM
falls back to a deterministic plan tied to the same signals so the page
never 5xx's.
"""

from __future__ import annotations

import uuid
from datetime import UTC, datetime, timedelta

import structlog
from sqlalchemy import desc, select
from sqlalchemy.ext.asyncio import AsyncSession

from aicmo.llm import get_llm_router
from aicmo.llm.providers.base import LLMMessage
from aicmo.modules.ads.models import GeneratedAd
from aicmo.modules.analytics import service as analytics_service
from aicmo.modules.content.models import GeneratedContent
from aicmo.modules.leads.models import Lead
from aicmo.modules.onboarding.schemas import BusinessAnalysis, BusinessProfileResponse
from aicmo.tenancy.context import TenantContext
from aicmo.modules.opportunities.prompts import (
    OPPORTUNITY_SYSTEM_PROMPT,
    build_opportunity_user_prompt,
)
from aicmo.modules.opportunities.schemas import (
    GeneratorHint,
    Opportunity,
    OpportunityCenterReport,
    OpportunityHeroRecommendation,
    _NarrativeOpportunity,
    _OpportunityCenterNarrative,
    derive_opportunity_id,
)
from aicmo.modules.advisor.dedupe import fingerprint_for_opportunity, should_suppress
from aicmo.modules.advisor.models import AdvisorRecommendation
from aicmo.modules.trends import service as trends_service

log = structlog.get_logger()

# Cap on opportunities the LLM can emit per surface — mirrored in prompt.
MAX_CONTENT_OPPS = 5
MAX_AD_OPPS = 3

# Window for "recent" activity used by the dedupe summary.
_RECENT_DAYS = 30


# ---------------------------------------------------------------------
#  Public entry point
# ---------------------------------------------------------------------


async def build_opportunity_center(
    session: AsyncSession,
    *,
    profile: BusinessProfileResponse,
    tenant: TenantContext | None = None,
) -> OpportunityCenterReport:
    """Single async entry point. Uses unified intelligence when enabled."""
    from aicmo.config import get_settings

    settings = get_settings()
    if settings.advisor_intelligence_enabled and tenant is not None:
        from aicmo.modules.advisor.intelligence import compose_intelligence
        from aicmo.modules.advisor.intelligence_adapter import (
            intelligence_to_opportunity_report,
        )

        intel = await compose_intelligence(session, profile=profile, tenant=tenant)
        return intelligence_to_opportunity_report(intel)

    from aicmo.modules.advisor.empty import build_empty_opportunity_report
    from aicmo.modules.advisor.memory import build_memory_context_block, load_brand_memory
    from aicmo.modules.advisor.readiness import assess_readiness
    from aicmo.modules.advisor.service import persist_opportunity_report

    settings = get_settings()
    composed = await _compose(session, profile=profile)

    if settings.advisor_engine_enabled:
        ready, setup_steps, message = await assess_readiness(
            session,
            profile=profile,
            signal_count=len(composed["signals"]),
        )
        if not ready and message:
            return build_empty_opportunity_report(
                message=message,
                setup_steps=setup_steps,
                signals=composed["signals"],
            )

    memory_rows: list = []
    memory_block: str | None = None
    if settings.advisor_engine_enabled:
        memory_rows = await load_brand_memory(session, brand_id=profile.brand_id)
        memory_block = build_memory_context_block(memory_rows)

    narrative = await _generate_narrative(
        profile=profile,
        composed=composed,
        memory_block=memory_block,
        memory_rows=memory_rows if settings.advisor_engine_enabled else None,
    )
    report = _assemble_report(narrative=narrative, composed=composed)

    if settings.advisor_engine_enabled and tenant is not None:
        report = await persist_opportunity_report(
            session,
            tenant=tenant,
            report=report,
            signals=composed["signals"],
        )
    return report


# ---------------------------------------------------------------------
#  Composer
# ---------------------------------------------------------------------


async def _compose(
    session: AsyncSession, *, profile: BusinessProfileResponse
) -> dict:
    """Pull every signal needed to write the report."""
    now = datetime.now(UTC)
    signals: list[str] = []

    # 1) Inbox snapshot — drives the "what's happening" framing.
    counts = await _load_lead_counts(session, brand_id=profile.brand_id, now=now)
    if counts["total"] == 0:
        signals.append("Inbox is empty — pre-traction. Every opportunity should target getting the first lead.")
    else:
        signals.append(
            f"{counts['total']} leads in the inbox · {counts['last_7d']} in the last 7 days · "
            f"{counts['hot']} marked hot."
        )

    counts_block = (
        f"- Total leads: {counts['total']}\n"
        f"- Hot leads: {counts['hot']}\n"
        f"- Last 7 days: {counts['last_7d']}\n"
        f"- Last 24h: {counts['last_24h']}"
    )

    # 2) Top channel — the "double down" signal.
    top_source_summary: str | None = None
    try:
        sources = await analytics_service.by_source(
            session, brand_id=profile.brand_id, limit=1
        )
        if sources.items:
            top = sources.items[0]
            label = (
                top.utm_campaign
                or top.utm_source
                or top.source_asset_type
                or "(unknown)"
            )
            top_source_summary = (
                f"{label} — {top.leads} leads, {top.hot_leads} hot."
            )
            signals.append(f"Winning channel so far: {top_source_summary}")
    except Exception as e:
        log.warning("opportunities.sources_lookup_failed", error=str(e))

    # 3) Top asset — the "clone the playbook" signal.
    top_asset_summary: str | None = None
    try:
        top_assets = await analytics_service.top_assets(
            session, brand_id=profile.brand_id, limit=1
        )
        if top_assets.items:
            t = top_assets.items[0]
            top_asset_summary = (
                f"'{t.goal}' ({t.source_asset_type} / {t.subtype}"
                + (f" on {t.platform}" if t.platform else "")
                + f") has driven {t.leads} leads."
            )
            signals.append(f"Top-performing asset: {top_asset_summary}")
    except Exception as e:
        log.warning("opportunities.top_assets_lookup_failed", error=str(e))

    # 4) Trends — what's hot the founder can ride.
    trends_summary: str | None = None
    trending_topics: list[str] = []
    try:
        report = await trends_service.get_report(session, profile.brand_id)
        if (
            report
            and report.status == "completed"
            and report.analysis is not None
        ):
            topics = (report.analysis or {}).get("trending_topics") or []
            trending_topics = [
                t.get("topic", "") for t in topics[:3] if t.get("topic")
            ]
            if trending_topics:
                trends_summary = " · ".join(trending_topics)
                signals.append(f"Live trends to ride: {trends_summary}")
        else:
            signals.append("No trends report has been run recently.")
    except Exception as e:
        log.warning("opportunities.trends_lookup_failed", error=str(e))

    # 5) Recent content + ads — for dedupe + "what's already shipped".
    recent_content_summary = await _summarise_recent_content(
        session, brand_id=profile.brand_id, now=now
    )
    recent_ads_summary = await _summarise_recent_ads(
        session, brand_id=profile.brand_id, now=now
    )
    if recent_content_summary:
        signals.append("Recent content already shipped (don't duplicate).")
    if recent_ads_summary:
        signals.append("Recent ads already drafted (don't duplicate).")

    # 6) Analysis prior — current phase + recommended channels.
    analysis: BusinessAnalysis | None = None
    if profile.analysis:
        try:
            analysis = (
                profile.analysis
                if isinstance(profile.analysis, BusinessAnalysis)
                else BusinessAnalysis.model_validate(profile.analysis)
            )
        except Exception:
            analysis = None
    if analysis and analysis.realistic_growth_path:
        first = analysis.realistic_growth_path[0]
        signals.append(
            f"Current growth-path phase: {first.phase} — {first.goal}"
        )
    if analysis and analysis.recommended_acquisition_channels:
        channels = [c.channel for c in analysis.recommended_acquisition_channels]
        signals.append(f"Strategist-recommended channels: {', '.join(channels)}.")

    return {
        "profile": profile,
        "counts": counts,
        "counts_block": counts_block,
        "top_source_summary": top_source_summary,
        "top_asset_summary": top_asset_summary,
        "trends_summary": trends_summary,
        "trending_topics": trending_topics,
        "recent_content_summary": recent_content_summary,
        "recent_ads_summary": recent_ads_summary,
        "signals": signals,
        "analysis": analysis,
    }


async def _load_lead_counts(
    session: AsyncSession, *, brand_id: uuid.UUID, now: datetime
) -> dict[str, int]:
    """Tiny one-shot counts query — same shape as Lead Intelligence."""
    from sqlalchemy import func

    week_ago = now - timedelta(days=7)
    day_ago = now - timedelta(hours=24)
    stmt = select(
        func.count().label("total"),
        func.count().filter(Lead.status == "hot").label("hot"),
        func.count().filter(Lead.created_at >= week_ago).label("w7"),
        func.count().filter(Lead.created_at >= day_ago).label("d1"),
    ).where(Lead.brand_id == brand_id)
    row = (await session.execute(stmt)).one()
    return {
        "total": int(row.total),
        "hot": int(row.hot),
        "last_7d": int(row.w7),
        "last_24h": int(row.d1),
    }


async def _summarise_recent_content(
    session: AsyncSession, *, brand_id: uuid.UUID, now: datetime
) -> str | None:
    """Up to 5 recent generated-content rows as a one-line summary each."""
    cutoff = now - timedelta(days=_RECENT_DAYS)
    stmt = (
        select(GeneratedContent)
        .where(
            GeneratedContent.brand_id == brand_id,
            GeneratedContent.created_at >= cutoff,
        )
        .order_by(desc(GeneratedContent.created_at))
        .limit(5)
    )
    rows = (await session.execute(stmt)).scalars().all()
    if not rows:
        return None
    lines: list[str] = []
    for r in rows:
        lines.append(
            f"- {r.content_type}"
            + (f" on {r.platform}" if r.platform else "")
            + (f" — goal: {r.goal}" if r.goal else "")
        )
    return "\n".join(lines)


async def _summarise_recent_ads(
    session: AsyncSession, *, brand_id: uuid.UUID, now: datetime
) -> str | None:
    cutoff = now - timedelta(days=_RECENT_DAYS)
    stmt = (
        select(GeneratedAd)
        .where(
            GeneratedAd.brand_id == brand_id,
            GeneratedAd.created_at >= cutoff,
        )
        .order_by(desc(GeneratedAd.created_at))
        .limit(5)
    )
    rows = (await session.execute(stmt)).scalars().all()
    if not rows:
        return None
    lines: list[str] = []
    for r in rows:
        lines.append(
            f"- {r.ad_type}"
            + (f" objective={r.objective}" if r.objective else "")
            + (f" — goal: {r.goal}" if r.goal else "")
        )
    return "\n".join(lines)


# ---------------------------------------------------------------------
#  LLM call — single invocation, fallback on error.
# ---------------------------------------------------------------------


async def _generate_narrative(
    *,
    profile: BusinessProfileResponse,
    composed: dict,
    memory_block: str | None = None,
    memory_rows: list[AdvisorRecommendation] | None = None,
) -> _OpportunityCenterNarrative:
    from aicmo.config import get_settings

    router = get_llm_router()
    user_prompt = build_opportunity_user_prompt(
        profile=profile,
        counts_block=composed["counts_block"],
        top_source_summary=composed["top_source_summary"],
        top_asset_summary=composed["top_asset_summary"],
        trends_summary=composed["trends_summary"],
        recent_content_summary=composed["recent_content_summary"],
        recent_ads_summary=composed["recent_ads_summary"],
        signals=composed["signals"],
        memory_block=memory_block,
    )
    try:
        result = await router.generate(
            response_schema=_OpportunityCenterNarrative,
            system=OPPORTUNITY_SYSTEM_PROMPT,
            messages=[LLMMessage(role="user", content=user_prompt)],
            temperature=0.55,
            max_tokens=6000,
        )
        narrative = result.data
        if memory_rows:
            narrative = _filter_suppressed_narrative(narrative, memory_rows)
        return narrative
    except Exception as e:
        log.warning("opportunities.narrative_failed", error=str(e))
        if get_settings().advisor_engine_enabled:
            return _honest_failure_narrative(composed)
        return _fallback_narrative(composed)


def _filter_suppressed_narrative(
    narrative: _OpportunityCenterNarrative,
    memory_rows: list[AdvisorRecommendation],
) -> _OpportunityCenterNarrative:
    def keep(opp: _NarrativeOpportunity) -> bool:
        fp = fingerprint_for_opportunity(
            kind=opp.kind,
            generator=opp.generator,
            recommended_action=opp.recommended_action,
        )
        return not should_suppress(fp, memory_rows)

    return narrative.model_copy(
        update={
            "content_opportunities": [
                o for o in narrative.content_opportunities if keep(o)
            ],
            "ad_opportunities": [o for o in narrative.ad_opportunities if keep(o)],
        }
    )


def _honest_failure_narrative(composed: dict) -> _OpportunityCenterNarrative:
    """No generic template fallback when advisor engine is active."""
    return _OpportunityCenterNarrative(
        headline="Not enough business activity data yet.",
        hero_recommendation=OpportunityHeroRecommendation(
            what_is_happening=(
                "We couldn't generate a fresh recommendation from your current signals."
            ),
            impact_category="lead",
            recommendation=(
                "Connect a channel or create your first campaign to unlock personalized advice."
            ),
            expected_result=(
                "Once activity data exists, recommendations will cite your real metrics."
            ),
            confidence=0,
            reason="Insufficient or unavailable signal data for this refresh.",
        ),
        content_opportunities=[],
        ad_opportunities=[],
        skip_for_now=[
            "Connect Instagram",
            "Connect Facebook",
            "Create your first campaign",
        ],
    )


# ---------------------------------------------------------------------
#  Assemble — derive ids, cap counts
# ---------------------------------------------------------------------


def _assemble_report(
    *,
    narrative: _OpportunityCenterNarrative,
    composed: dict,
) -> OpportunityCenterReport:
    content_opps = _build_opportunities(
        narrative.content_opportunities[:MAX_CONTENT_OPPS], expected_kind="content"
    )
    ad_opps = _build_opportunities(
        narrative.ad_opportunities[:MAX_AD_OPPS], expected_kind="ad"
    )

    return OpportunityCenterReport(
        headline=narrative.headline,
        hero_recommendation=narrative.hero_recommendation,
        content_opportunities=content_opps,
        ad_opportunities=ad_opps,
        skip_for_now=list(narrative.skip_for_now),
        signals_used=composed["signals"],
        generated_at=datetime.now(UTC).isoformat(),
    )


def _build_opportunities(
    items: list[_NarrativeOpportunity],
    *,
    expected_kind: str,
) -> list[Opportunity]:
    """Wrap LLM opportunities with derived ids. Drop entries that landed
    in the wrong bucket (e.g. LLM put a content opp under ads) so the
    surface stays clean."""
    out: list[Opportunity] = []
    seen_ids: set[uuid.UUID] = set()
    for n in items:
        if n.kind != expected_kind:
            log.warning(
                "opportunities.misbucketed",
                expected=expected_kind,
                got=n.kind,
                headline=n.headline,
            )
            continue
        opp_id = derive_opportunity_id(
            kind=n.kind,
            generator=n.generator,
            recommended_action=n.recommended_action,
        )
        if opp_id in seen_ids:
            # Same recommendation twice in one report — drop the duplicate.
            continue
        seen_ids.add(opp_id)
        out.append(
            Opportunity(
                id=opp_id,
                kind=n.kind,
                headline=n.headline,
                what_is_happening=n.what_is_happening,
                why_it_matters=n.why_it_matters,
                recommended_action=n.recommended_action,
                expected_result=n.expected_result,
                confidence=n.confidence,
                reason=n.reason,
                impact_category=n.impact_category,
                evidence=list(n.evidence),
                generator=n.generator,
            )
        )
    return out


# ---------------------------------------------------------------------
#  Deterministic fallback (LLM unavailable or invalid response)
# ---------------------------------------------------------------------


def _fallback_narrative(composed: dict) -> _OpportunityCenterNarrative:
    """Built from the same composer signals. Every contract field is
    filled so even a complete LLM outage gives the founder a
    Constitution-valid report."""
    counts = composed["counts"]
    profile: BusinessProfileResponse = composed["profile"]
    trending_topics: list[str] = composed["trending_topics"]
    top_source_summary: str | None = composed["top_source_summary"]
    top_asset_summary: str | None = composed["top_asset_summary"]
    winning_platform = _detect_winning_platform(top_source_summary, profile)

    if counts["total"] == 0:
        return _fallback_zero_state(profile, trending_topics)

    return _fallback_with_traction(
        profile=profile,
        counts=counts,
        trending_topics=trending_topics,
        top_source_summary=top_source_summary,
        top_asset_summary=top_asset_summary,
        winning_platform=winning_platform,
    )


def _detect_winning_platform(
    top_source_summary: str | None, profile: BusinessProfileResponse
) -> str:
    """Pick the platform to recommend in the fallback. Prefer:
    1. The platform mentioned in the top-source summary (if any).
    2. The first preferred_platforms entry.
    3. Generic 'Instagram' as last resort — common SMB default."""
    if top_source_summary:
        lowered = top_source_summary.lower()
        for plat in (
            "instagram",
            "linkedin",
            "facebook",
            "tiktok",
            "youtube",
            "twitter",
        ):
            if plat in lowered:
                return plat.capitalize()
    if profile.preferred_platforms:
        return profile.preferred_platforms[0]
    return "Instagram"


def _fallback_zero_state(
    profile: BusinessProfileResponse, trending_topics: list[str]
) -> _OpportunityCenterNarrative:
    platform = (
        profile.preferred_platforms[0] if profile.preferred_platforms else "Instagram"
    )
    content_opps: list[_NarrativeOpportunity] = [
        _NarrativeOpportunity(
            kind="content",
            headline="Get your first lead online",
            what_is_happening=(
                "You don't have any captured leads yet — the pipeline starts empty."
            ),
            why_it_matters=(
                "Until one piece of content points at a published lead page, "
                "you can't measure or improve anything."
            ),
            recommended_action=(
                f"Publish one {platform.lower()} post that introduces your offer "
                "and ends with a link to your lead page."
            ),
            expected_result="Even 30-50 visits typically produces your first 1-3 leads.",
            confidence=65,
            reason="Based on the empty inbox — the funnel needs a first asset.",
            impact_category="lead",
            evidence=[f"Preferred platform: {platform}"],
            generator=GeneratorHint(
                target="content",
                format="social_post",
                platform=platform,
                goal="Grow email list",
            ),
        )
    ]
    if trending_topics:
        first_trend = trending_topics[0]
        content_opps.append(
            _NarrativeOpportunity(
                kind="content",
                headline=f"Ride the '{first_trend}' trend",
                what_is_happening=(
                    f"'{first_trend}' is trending right now in your industry."
                ),
                why_it_matters=(
                    "Trends are the cheapest way to grab attention without paying for it."
                ),
                recommended_action=(
                    f"Create one short-form video for {platform} on '{first_trend}', "
                    "ending with your lead-page CTA."
                ),
                expected_result="Likely 50-200 extra views and 1-3 new followers.",
                confidence=55,
                reason=f"Based on trending topic: {first_trend}.",
                impact_category="lead",
                evidence=[f"Trending: {first_trend}"],
                generator=GeneratorHint(
                    target="content",
                    format="reel",
                    platform=platform,
                    goal="Build brand awareness",
                ),
            )
        )

    return _OpportunityCenterNarrative(
        headline="No leads yet — this week is about getting your first one in.",
        hero_recommendation=OpportunityHeroRecommendation(
            what_is_happening="Your lead inbox is empty and no content has shipped recently.",
            impact_category="lead",
            recommendation=(
                f"Publish one {platform} post pointing at your lead page today."
            ),
            expected_result="A first round of 30-50 visits and possibly 1-3 leads in the following week.",
            confidence=65,
            reason="Based on the empty inbox + at least one preferred platform configured.",
        ),
        content_opportunities=content_opps,
        ad_opportunities=[],  # don't recommend paid until there's organic signal
        skip_for_now=[
            "Don't run paid ads yet — get an organic baseline first so you know which message works.",
        ],
    )


def _fallback_with_traction(
    *,
    profile: BusinessProfileResponse,
    counts: dict[str, int],
    trending_topics: list[str],
    top_source_summary: str | None,
    top_asset_summary: str | None,
    winning_platform: str,
) -> _OpportunityCenterNarrative:
    content_opps: list[_NarrativeOpportunity] = []
    ad_opps: list[_NarrativeOpportunity] = []

    # 1) Clone the winning asset if there is one.
    if top_asset_summary:
        content_opps.append(
            _NarrativeOpportunity(
                kind="content",
                headline=f"Clone the {winning_platform} winner",
                what_is_happening=f"One asset is doing the heavy lifting: {top_asset_summary}",
                why_it_matters=(
                    "When one piece breaks through, the cheapest growth is "
                    "shipping a second piece in the same shape."
                ),
                recommended_action=(
                    f"Publish a follow-up {winning_platform} post in the same format "
                    "and tone, with a fresh angle."
                ),
                expected_result="Likely 50-80% of the traction the original produced.",
                confidence=70,
                reason=f"Based on top-performing asset signal: {top_asset_summary}",
                impact_category="lead",
                evidence=[f"Top asset: {top_asset_summary}"],
                generator=GeneratorHint(
                    target="content",
                    format="social_post",
                    platform=winning_platform,
                    goal="Drive engagement",
                ),
            )
        )

    # 2) Ride the top trend.
    if trending_topics:
        first_trend = trending_topics[0]
        content_opps.append(
            _NarrativeOpportunity(
                kind="content",
                headline=f"Ride the '{first_trend}' trend",
                what_is_happening=f"'{first_trend}' is trending right now in your industry.",
                why_it_matters="Trends decay fast — first to publish wins the cheapest organic reach.",
                recommended_action=(
                    f"Create a short-form video for {winning_platform} on '{first_trend}', "
                    "ending with your lead-page CTA."
                ),
                expected_result="Likely 100-300 extra views and 1-3 new leads if the angle fits.",
                confidence=60,
                reason=f"Based on trending topic: {first_trend}",
                impact_category="lead",
                evidence=[f"Trending: {first_trend}"],
                generator=GeneratorHint(
                    target="content",
                    format="reel",
                    platform=winning_platform,
                    goal="Build brand awareness",
                ),
            )
        )

    # 3) Always ship a "ship one new piece" baseline.
    if not content_opps:
        content_opps.append(
            _NarrativeOpportunity(
                kind="content",
                headline="Ship one new post this week",
                what_is_happening=(
                    f"You have {counts['total']} leads but no fresh content this week."
                ),
                why_it_matters="Channels go quiet without consistent posting — leads dry up after 7-14 days.",
                recommended_action=(
                    f"Publish one new {winning_platform} post pointing at your lead page."
                ),
                expected_result="A small refresh in inbound traffic over the following 7-10 days.",
                confidence=55,
                reason=f"Based on existing leads ({counts['total']}) but no recent content.",
                impact_category="lead",
                evidence=[],
                generator=GeneratorHint(
                    target="content",
                    format="social_post",
                    platform=winning_platform,
                    goal="Drive engagement",
                ),
            )
        )

    # 4) Ad opportunity — only when there's an obvious channel winner.
    if top_source_summary:
        ad_opps.append(
            _NarrativeOpportunity(
                kind="ad",
                headline=f"Double down on {winning_platform} ads",
                what_is_happening=(
                    f"{top_source_summary} is producing the most leads."
                ),
                why_it_matters=(
                    "Allocating budget to the proven channel beats spreading thin across new ones."
                ),
                recommended_action=(
                    f"Run one $10-$20/day Meta ad on {winning_platform} for a week, "
                    "pointing at your top lead page."
                ),
                expected_result="A 15-30% lift in weekly leads if the offer fits.",
                confidence=60,
                reason=f"Based on top channel: {top_source_summary}",
                impact_category="lead",
                evidence=[f"Top channel: {top_source_summary}"],
                generator=GeneratorHint(
                    target="ad",
                    format="meta" if "instagram" in winning_platform.lower() or "facebook" in winning_platform.lower() else "google_search",
                    platform=None,
                    goal="Drive conversions / sales",
                    objective="leads",
                ),
            )
        )

    headline_bits = []
    if top_source_summary:
        headline_bits.append(f"{winning_platform} is your winning channel")
    if trending_topics:
        headline_bits.append(f"trends are aligning ({trending_topics[0]})")
    if not headline_bits:
        headline_bits.append("the inbox has leads to build on")
    headline = " — ".join(headline_bits) + ". This week is about doubling down."

    return _OpportunityCenterNarrative(
        headline=headline,
        hero_recommendation=_fallback_hero(
            counts=counts,
            trending_topics=trending_topics,
            top_source_summary=top_source_summary,
            winning_platform=winning_platform,
        ),
        content_opportunities=content_opps,
        ad_opportunities=ad_opps,
        skip_for_now=[],
    )


def _fallback_hero(
    *,
    counts: dict[str, int],
    trending_topics: list[str],
    top_source_summary: str | None,
    winning_platform: str,
) -> OpportunityHeroRecommendation:
    if trending_topics:
        first_trend = trending_topics[0]
        return OpportunityHeroRecommendation(
            what_is_happening=(
                f"'{first_trend}' is trending right now and you have a clear "
                f"winning channel ({winning_platform})."
            ),
            impact_category="lead",
            recommendation=(
                f"Ship one {winning_platform} reel riding the '{first_trend}' trend "
                "before Friday, ending with your lead-page CTA."
            ),
            expected_result="Likely 5-12 new visitors and 1-2 leads over the following 7 days.",
            confidence=65,
            reason=f"Based on trending topic + {winning_platform} as winning channel.",
        )
    if top_source_summary:
        return OpportunityHeroRecommendation(
            what_is_happening=(
                f"{top_source_summary} is producing most of your leads — "
                "no new content this week to keep that pipeline warm."
            ),
            impact_category="lead",
            recommendation=(
                f"Ship one new {winning_platform} post in the same shape as your top performer."
            ),
            expected_result="A small refresh in inbound traffic over the following 7-10 days.",
            confidence=60,
            reason=f"Based on top channel: {top_source_summary}",
        )
    return OpportunityHeroRecommendation(
        what_is_happening=(
            f"You have {counts['total']} leads but no obvious winning channel yet."
        ),
        impact_category="lead",
        recommendation=(
            f"Publish one {winning_platform} post pointing at your lead page this week to start a signal."
        ),
        expected_result="Either the first signs of a winning channel, or a clear 'this isn't it' signal — both useful.",
        confidence=50,
        reason="Based on existing leads but no clear top channel.",
    )
