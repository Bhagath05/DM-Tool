"""Analytics Explanation Layer orchestrator.

Pulls every analytics signal once, flattens them into a single prompt,
asks Gemini for per-section narration. The composer is deterministic;
only the narration is LLM-generated. Failures degrade to a calm
"data-only" fallback so the analytics dashboard never breaks.
"""

from __future__ import annotations

from datetime import UTC, datetime

import structlog
from sqlalchemy.ext.asyncio import AsyncSession

from aicmo.llm import get_llm_router
from aicmo.llm.providers.base import LLMMessage
from aicmo.modules.analytics import service as analytics_service
from aicmo.modules.coach.prompts import (
    ANALYTICS_SUMMARY_SYSTEM_PROMPT,
    build_analytics_summary_user_prompt,
)
from aicmo.modules.coach.schemas import AnalyticsSummary
from aicmo.modules.onboarding.schemas import BusinessProfileResponse

log = structlog.get_logger()

# Uses platform-default LLM provider (see config.llm_default_provider).


async def build_analytics_summary(
    session: AsyncSession,
    *,
    profile: BusinessProfileResponse,
) -> AnalyticsSummary:
    """Single public entry point. Read-only — never writes to the DB."""
    composed = await _compose(session, profile=profile)
    narrative = await _narrate(profile=profile, composed=composed)
    return AnalyticsSummary(
        headline=narrative.headline,
        what_to_do_next=narrative.what_to_do_next,
        overview_blurb=narrative.overview_blurb,
        timeline_blurb=narrative.timeline_blurb,
        sources_blurb=narrative.sources_blurb,
        landing_pages_blurb=narrative.landing_pages_blurb,
        top_assets_blurb=narrative.top_assets_blurb,
        signals_used=composed["signals"],
        generated_at=datetime.now(UTC).isoformat(),
    )


# ---------------------------------------------------------------------
#  Composer — pulls facts from analytics.service (no new DB code)
# ---------------------------------------------------------------------


async def _compose(
    session: AsyncSession, *, profile: BusinessProfileResponse
) -> dict:
    """Gather the same data the analytics dashboard renders. Each lookup
    swallows its own failure so one slow query can't 5xx the summary."""
    signals: list[str] = []
    overview_dict: dict = {}
    timeline_summary = "(no daily timeline available)"
    sources_summary = "(no source data yet)"
    landing_pages_summary = "(no published landing pages yet)"
    top_assets_summary = "(no converting assets yet)"

    try:
        overview = await analytics_service.overview(
            session, brand_id=profile.brand_id
        )
        overview_dict = overview.model_dump()
        signals.append(
            f"{overview.total_leads} total leads · {overview.leads_7d} in last 7 days · "
            f"conversion {overview.conversion_rate * 100:.1f}%"
        )
    except Exception as e:  # noqa: BLE001
        log.warning("coach.summary.overview_failed", error=str(e))

    try:
        timeline = await analytics_service.timeline(
            session, brand_id=profile.brand_id, window_days=30
        )
        non_zero = [p for p in timeline.days if p.leads > 0]
        if non_zero:
            best = max(non_zero, key=lambda p: p.leads)
            timeline_summary = (
                f"Window: {timeline.window_days} days. Total: {timeline.total}. "
                f"Best day: {best.day.isoformat()} ({best.leads} leads). "
                f"Days with at least 1 lead: {len(non_zero)} / {timeline.window_days}."
            )
            signals.append(f"Best day in window: {best.day.isoformat()}")
        else:
            timeline_summary = f"Zero leads in the last {timeline.window_days} days."
    except Exception as e:  # noqa: BLE001
        log.warning("coach.summary.timeline_failed", error=str(e))

    try:
        sources = await analytics_service.by_source(
            session, brand_id=profile.brand_id, limit=10
        )
        if sources.items:
            lines = []
            for s in sources.items[:5]:
                source = s.utm_source or s.source_asset_type or "direct"
                campaign = s.utm_campaign or "(no campaign)"
                lines.append(
                    f"- {source} via {s.utm_medium or 'unknown medium'} "
                    f"({campaign}): {s.leads} leads, {s.hot_leads} hot"
                )
            sources_summary = "\n".join(lines)
            signals.append(f"{len(sources.items)} unique source rows")
    except Exception as e:  # noqa: BLE001
        log.warning("coach.summary.sources_failed", error=str(e))

    try:
        pages = await analytics_service.landing_page_performance(
            session, brand_id=profile.brand_id
        )
        if pages.items:
            lines = []
            for p in pages.items[:6]:
                lines.append(
                    f"- {p.title} ({p.status}): {p.view_count} views, "
                    f"{p.submission_count} signups "
                    f"({p.conversion_rate * 100:.1f}% conversion)"
                )
            landing_pages_summary = "\n".join(lines)
            signals.append(f"{len(pages.items)} lead page(s) tracked")
    except Exception as e:  # noqa: BLE001
        log.warning("coach.summary.pages_failed", error=str(e))

    try:
        top = await analytics_service.top_assets(
            session, brand_id=profile.brand_id, limit=5
        )
        if top.items:
            lines = []
            for t in top.items:
                platform = f" on {t.platform}" if t.platform else ""
                lines.append(
                    f"- {t.source_asset_type}/{t.subtype}{platform} "
                    f"('{t.goal}'): {t.leads} leads, {t.hot_leads} hot"
                )
            top_assets_summary = "\n".join(lines)
            signals.append(f"Top assets: {len(top.items)} ranked")
    except Exception as e:  # noqa: BLE001
        log.warning("coach.summary.top_assets_failed", error=str(e))

    return {
        "signals": signals,
        "overview_dict": overview_dict,
        "timeline_summary": timeline_summary,
        "sources_summary": sources_summary,
        "landing_pages_summary": landing_pages_summary,
        "top_assets_summary": top_assets_summary,
    }


# ---------------------------------------------------------------------
#  Narration — one Gemini call, graceful fallback
# ---------------------------------------------------------------------


async def _narrate(
    *,
    profile: BusinessProfileResponse,
    composed: dict,
) -> AnalyticsSummary:
    router = get_llm_router()
    profile_stage = (
        f"{profile.current_monthly_leads_band} band"
        if profile.current_monthly_leads_band
        else None
    )
    user_prompt = build_analytics_summary_user_prompt(
        profile_name=profile.business_name,
        profile_stage=profile_stage,
        overview=composed["overview_dict"],
        timeline_summary=composed["timeline_summary"],
        sources_summary=composed["sources_summary"],
        landing_pages_summary=composed["landing_pages_summary"],
        top_assets_summary=composed["top_assets_summary"],
    )
    try:
        result = await router.generate(
            response_schema=AnalyticsSummary,
            system=ANALYTICS_SUMMARY_SYSTEM_PROMPT,
            messages=[LLMMessage(role="user", content=user_prompt)],
            temperature=0.4,
            # Same Gemini-Flash thinking-budget consideration as Phase 2.4:
            # the prompt is data-heavy, the response is short, but reasoning
            # tokens count. 4500 fits both.
            max_tokens=4500,
        )
        return result.data
    except Exception as e:  # noqa: BLE001
        log.warning("coach.summary.narration_failed", error=str(e))
        return _fallback_summary(composed)


def _fallback_summary(composed: dict) -> AnalyticsSummary:
    """When Gemini is unavailable, return raw-but-honest text so the
    dashboard still shows something useful."""
    overview = composed["overview_dict"] or {}
    total_leads = overview.get("total_leads", 0)
    leads_7d = overview.get("leads_7d", 0)

    if total_leads == 0:
        headline = "No customers yet — pre-traction. Attach a lead page somewhere and ship."
    elif leads_7d == 0:
        headline = f"{total_leads} total leads, but nothing in the last week — your last campaign may have stalled."
    else:
        headline = (
            f"{total_leads} total leads, {leads_7d} in the last 7 days. Momentum is real."
        )

    return AnalyticsSummary(
        headline=headline,
        what_to_do_next=(
            "Open the top-converting assets card and re-run the playbook of whatever is winning."
            if total_leads > 0
            else "Attach a published lead page to your next generated post — that's the first lead."
        ),
        overview_blurb=(
            f"You have {total_leads} captured leads and "
            f"{overview.get('total_submissions', 0)} signups across "
            f"{overview.get('landing_pages_published', 0)} published pages."
        ),
        timeline_blurb=composed.get("timeline_summary") or "Not enough history yet.",
        sources_blurb="The AI narrator is briefly unavailable — see the channels below.",
        landing_pages_blurb="The AI narrator is briefly unavailable — see the table below.",
        top_assets_blurb="The AI narrator is briefly unavailable — see the table below.",
        signals_used=composed.get("signals", []),
        generated_at=datetime.now(UTC).isoformat(),
    )
