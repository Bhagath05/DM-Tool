"""Weekly Action Rollup orchestrator.

Composition layer over existing modules. The composer pulls deterministic
signals from analytics, trends, landing pages, and the onboarding analysis,
then hands them to the LLM which writes the narrative action plan.

Failure policy: identical to Reality Engine — the founder always gets a
usable plan. If the LLM fails, we return a heuristic fallback so the
dashboard never shows a 5xx.

The endpoint is meant to be called on demand (button) AND auto-loaded by
the dashboard. Client-side 12h cache keeps cost flat — see the
WeeklyActionsCard component.
"""

from __future__ import annotations

from datetime import UTC, datetime

import structlog
from sqlalchemy.ext.asyncio import AsyncSession

from aicmo.llm import get_llm_router
from aicmo.llm.providers.base import LLMMessage
from aicmo.modules.analytics import service as analytics_service
from aicmo.modules.coach.prompts import (
    WEEKLY_SYSTEM_PROMPT,
    build_weekly_user_prompt,
)
from aicmo.modules.coach.schemas import (
    WeeklyAction,
    WeeklyPlan,
    _WeeklyPlanNarrative,
)
from aicmo.modules.landing_pages import service as landing_pages_service
from aicmo.modules.onboarding.schemas import (
    BusinessAnalysis,
    BusinessProfileResponse,
)
from aicmo.modules.trends import service as trends_service

log = structlog.get_logger()

# Uses platform-default LLM provider (see config.llm_default_provider).


async def build_weekly_plan(
    session: AsyncSession,
    *,
    profile: BusinessProfileResponse,
) -> WeeklyPlan:
    """Single public entry point. Read-only, no DB writes."""
    composed = await _compose_signals(session, profile=profile)
    narrative = await _generate_narrative(profile=profile, composed=composed)

    return WeeklyPlan(
        headline=narrative.headline,
        week_focus=narrative.week_focus,
        actions=narrative.actions,
        skip_this_week=narrative.skip_this_week,
        signals_used=composed["signals"],
        generated_at=datetime.now(UTC).isoformat(),
    )


# ---------------------------------------------------------------------
#  Composer — pulls facts from existing services.
# ---------------------------------------------------------------------


async def _compose_signals(
    session: AsyncSession, *, profile: BusinessProfileResponse
) -> dict:
    """Gather everything the LLM needs. Each lookup is independent and
    swallows its own errors — a slow trends report can't block the plan."""
    signals: list[str] = []

    # 1) Lead-page presence — if there's no published page, that's THE
    # top constraint and the plan should say so. Inline SQL because the
    # service-layer `list_pages` takes a TenantContext we don't have
    # here; the composer is brand-scoped via profile.brand_id directly.
    has_published_page = False
    try:
        from aicmo.modules.landing_pages.models import LandingPage
        from sqlalchemy import func, select as _sel

        published_count = (
            await session.execute(
                _sel(func.count(LandingPage.id)).where(
                    LandingPage.brand_id == profile.brand_id,
                    LandingPage.status == "published",
                )
            )
        ).scalar_one()
        has_published_page = published_count > 0
        if not has_published_page:
            signals.append(
                "No published lead page yet — captured leads are impossible until one ships."
            )
        else:
            signals.append(
                f"{published_count} published lead page(s)."
            )
    except Exception as e:  # noqa: BLE001
        log.warning("coach.weekly.pages_lookup_failed", error=str(e))

    # 2–4) Analytics + top asset + trends — sequential (AsyncSession is not
    # safe for concurrent queries on the same session).
    overview_result: object | None = None
    top_result: object | None = None
    trends_result: object | None = None

    try:
        overview_result = await analytics_service.overview(
            session, brand_id=profile.brand_id
        )
    except Exception as e:  # noqa: BLE001
        log.warning("coach.weekly.overview_lookup_failed", error=str(e))

    try:
        top_result = await analytics_service.top_assets(
            session, brand_id=profile.brand_id, limit=1
        )
    except Exception as e:  # noqa: BLE001
        log.warning("coach.weekly.top_assets_lookup_failed", error=str(e))

    try:
        trends_result = await trends_service.get_report(session, profile.brand_id)
    except Exception as e:  # noqa: BLE001
        log.warning("coach.weekly.trends_lookup_failed", error=str(e))

    if overview_result is not None:
        overview = overview_result
        if overview.total_leads == 0:
            signals.append("Zero captured leads so far — pre-traction.")
        else:
            signals.append(
                f"{overview.total_leads} total leads · {overview.leads_7d} in the last 7 days · "
                f"{overview.hot_leads} marked hot."
            )
        if overview.conversion_rate > 0:
            signals.append(
                f"Lead-page conversion is {overview.conversion_rate * 100:.1f}% (sub-2% = page issue; 2-5% = healthy)."
            )

    top_asset_summary: str | None = None
    if top_result is not None and top_result.items:
        t = top_result.items[0]
        top_asset_summary = (
            f"'{t.goal}' ({t.source_asset_type} / {t.subtype}"
            + (f" on {t.platform}" if t.platform else "")
            + f") has driven {t.leads} leads."
        )
        signals.append(f"Top-performing asset: {top_asset_summary}")

    trends_summary: str | None = None
    report = trends_result
    if (
        report
        and report.status == "completed"
        and report.analysis is not None
    ):
        topics = (report.analysis or {}).get("trending_topics") or []
        picks = [t.get("topic") for t in topics[:3] if t.get("topic")]
        if picks:
            trends_summary = " · ".join(picks)
            signals.append(f"Live trends to ride: {trends_summary}")
    elif trends_result is not None:
        signals.append("No trends report run recently.")

    # 5) Onboarding analysis — surface the current growth-path phase +
    # recommended channels (the v2 fields, if present).
    analysis_phase_summary: str | None = None
    analysis_channels: list[str] = []
    analysis: BusinessAnalysis | None = None
    if profile.analysis:
        try:
            analysis = (
                profile.analysis
                if isinstance(profile.analysis, BusinessAnalysis)
                else BusinessAnalysis.model_validate(profile.analysis)
            )
        except Exception:  # noqa: BLE001
            analysis = None
    if analysis:
        path = analysis.realistic_growth_path or []
        if path:
            first = path[0]
            analysis_phase_summary = f"{first.phase} — {first.goal}"
            signals.append(
                f"Current growth-path phase: {analysis_phase_summary}"
            )
        if analysis.recommended_acquisition_channels:
            analysis_channels = [
                c.channel for c in analysis.recommended_acquisition_channels
            ]
        if analysis.growth_bottlenecks:
            signals.append(
                "Known bottlenecks: "
                + " · ".join(analysis.growth_bottlenecks[:3])
            )

    return {
        "signals": signals,
        "has_published_page": has_published_page,
        "top_asset_summary": top_asset_summary,
        "trends_summary": trends_summary,
        "analysis_phase_summary": analysis_phase_summary,
        "analysis_channels": analysis_channels,
        # Stub: future enhancement could count rows from generated_content,
        # generated_ads, etc. For now an empty map is fine — the prompt
        # already says "(none)" when empty.
        "recent_activity": {},
    }


# ---------------------------------------------------------------------
#  LLM call — single Gemini invocation, fallback on error.
# ---------------------------------------------------------------------


async def _generate_narrative(
    *,
    profile: BusinessProfileResponse,
    composed: dict,
) -> _WeeklyPlanNarrative:
    router = get_llm_router()
    user_prompt = build_weekly_user_prompt(
        profile=profile,
        signals=composed["signals"],
        recent_activity=composed["recent_activity"],
        has_published_page=composed["has_published_page"],
        top_asset_summary=composed["top_asset_summary"],
        trends_summary=composed["trends_summary"],
        analysis_phase_summary=composed["analysis_phase_summary"],
        analysis_channels=composed["analysis_channels"],
    )
    try:
        result = await router.generate(
            response_schema=_WeeklyPlanNarrative,
            system=WEEKLY_SYSTEM_PROMPT,
            messages=[LLMMessage(role="user", content=user_prompt)],
            temperature=0.55,
            # Gemini 2.5 Flash burns "thinking" tokens against this budget
            # before emitting content, and the model thinks heavily on a
            # synthesis prompt like this one. 5000 covers content (~700)
            # plus reasoning headroom without truncating.
            max_tokens=5000,
        )
        return result.data
    except Exception as e:  # noqa: BLE001 — advisory must degrade gracefully
        log.warning("coach.weekly.narrative_failed", error=str(e))
        return _fallback_narrative(composed)


def _fallback_narrative(composed: dict) -> _WeeklyPlanNarrative:
    """Deterministic plan if the LLM is unreachable.

    Every field on every action is filled so the fallback satisfies the
    Constitution's recommendation contract (recommendation + reason +
    confidence + expected_result + business_impact + impact_category).
    Confidence is intentionally moderate (60-75) because this plan is
    derived from rules of thumb, not the user's actual data nuance.
    """
    has_page = composed["has_published_page"]
    actions: list[WeeklyAction] = []

    if not has_page:
        actions.append(
            WeeklyAction(
                action_title="Publish your first lead page",
                why="Without a published page, no asset can actually capture leads — every other action depends on this.",
                business_impact="First real path to capturing leads from any marketing channel.",
                impact_category="lead",
                expected_result="Once live, even 50 visitors can produce your first 1-3 leads.",
                confidence=75,
                reason="Based on the missing lead-page signal — capture is impossible without one.",
                cta_label="Build a page",
                cta_target="lead_pages",
                priority="focus",
                estimated_time="30 min",
            )
        )
    else:
        actions.append(
            WeeklyAction(
                action_title="Publish one social post and attach your lead page to it",
                why="Drives the first wave of traffic to a page that can actually capture interest.",
                business_impact="Converts attention into measurable leads through your published page.",
                impact_category="lead",
                expected_result="Likely 3-8 visitors and possibly 1-2 leads from a single post.",
                confidence=65,
                reason="Based on having a published page but no recent traffic-driving activity.",
                cta_label="Draft a post",
                cta_target="content",
                priority="focus",
                estimated_time="20 min",
            )
        )
        actions.append(
            WeeklyAction(
                action_title="Run a trends refresh to see what's hot in your industry",
                why="Trends are the cheapest way to grab attention this week without paying for it.",
                business_impact="Cheaper organic reach by riding what's already getting attention.",
                impact_category="cost",
                expected_result="Surfaces 3-5 fresh topic angles to use across this week's content.",
                confidence=70,
                reason="Based on the absence of a recent trends report in this brand's signals.",
                cta_label="Open trends",
                cta_target="trends",
                priority="important",
                estimated_time="5 min",
            )
        )

    return _WeeklyPlanNarrative(
        headline="The AI strategist is briefly unavailable — here's a sensible default plan based on what we know.",
        week_focus="Get one piece of content live with a lead page attached, so traffic becomes leads."
        if has_page
        else "Publish your first lead page so the rest of the platform can do its job.",
        actions=actions,
        skip_this_week=[],
    )
