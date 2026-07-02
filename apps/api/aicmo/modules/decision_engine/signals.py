"""Gather the factual evidence base from existing modules — cheap queries only,
never the modules' LLM analyses. Each source is guarded so a sparse or
partially-broken workspace still yields an honest (mostly-empty) snapshot; the
Decision Engine then reasons about what little is known and says so.
"""

from __future__ import annotations

import structlog
from sqlalchemy.ext.asyncio import AsyncSession

from aicmo.modules.analytics import service as analytics_service
from aicmo.modules.decision_engine.schemas import DecisionSignals
from aicmo.modules.learning import feedback as learning_feedback
from aicmo.modules.onboarding import service as onboarding_service
from aicmo.modules.onboarding.schemas import BusinessProfileResponse
from aicmo.modules.performance import service as performance_service
from aicmo.modules.publishing import service as publishing_service
from aicmo.modules.social import service as social_service
from aicmo.modules.strategist import service as strategist_service
from aicmo.tenancy.context import TenantContext

log = structlog.get_logger()


async def gather_signals(
    session: AsyncSession, *, tenant: TenantContext
) -> DecisionSignals:
    brand_id = tenant.brand_id
    sig = DecisionSignals(has_profile=False)

    profile_row = await onboarding_service.get_profile_or_none(session, brand_id)
    if profile_row is not None:
        p = BusinessProfileResponse.model_validate(profile_row)
        sig.has_profile = True
        sig.business_name = p.business_name
        sig.industry = p.industry
        sig.growth_stage = p.growth_stage
        sig.primary_goal = p.primary_goal_text
        sig.goals = list(p.goals)
        sig.competitors = list(p.competitors)

    try:
        kpis = await analytics_service.overview(session, brand_id=brand_id)
        sig.total_leads = kpis.total_leads
        sig.leads_7d = kpis.leads_7d
        sig.leads_30d = kpis.leads_30d
        sig.hot_leads = kpis.hot_leads
        sig.total_views = kpis.total_views
        sig.conversion_rate = kpis.conversion_rate
        sig.landing_pages_published = kpis.landing_pages_published
    except Exception as e:
        log.warning("decision.signals.analytics_failed", error=str(e)[:120])

    try:
        perf = await performance_service.overview(session, tenant=tenant)
        sig.performance_has_data = perf.has_data
        sig.performance_rows = perf.rows_ingested
        sig.creatives_tracked = perf.creatives_tracked
        sig.performance_diagnostics = len(perf.diagnostics)
    except Exception as e:
        log.warning("decision.signals.performance_failed", error=str(e)[:120])

    try:
        scheduled = await publishing_service.list_scheduled(
            session, brand_id=brand_id, limit=100
        )
        for item in scheduled.items:
            if item.publish_status == "scheduled":
                sig.scheduled_posts += 1
            elif item.publish_status == "published":
                sig.published_posts += 1
            elif item.publish_status == "failed":
                sig.failed_posts += 1
    except Exception as e:
        log.warning("decision.signals.publishing_failed", error=str(e)[:120])

    try:
        record = await strategist_service.latest(session, brand_id=brand_id)
        if record is not None and record.status == "completed" and record.strategy:
            sig.has_strategy = True
            sig.strategy_top_move = record.strategy.get("recommendation")
    except Exception as e:
        log.warning("decision.signals.strategy_failed", error=str(e)[:120])

    # Learned memory — reuse the Learning Engine's social patterns (what has
    # actually worked). Highest performance/confidence first.
    try:
        wins = await social_service.list_winning_patterns(
            session, brand_id=brand_id, limit=5
        )
        sig.winning_patterns = [w.summary for w in wins if w.summary]
        auds = await social_service.list_audience_patterns(session, brand_id=brand_id)
        sig.audience_patterns = [a.description for a in auds[:5] if a.description]
    except Exception as e:
        log.warning("decision.signals.memory_failed", error=str(e)[:120])

    # Learning Engine (Module 6) — durable cross-domain lessons already routed
    # to `decision`. These are synthesised, higher-order than the raw patterns.
    try:
        lessons = await learning_feedback.active_insights_for_module(
            session, brand_id=brand_id, module="decision", limit=5
        )
        sig.learning_insights = [
            f"{r.observation} → {r.recommendation}" for r in lessons
        ]
    except Exception as e:
        log.warning("decision.signals.lessons_failed", error=str(e)[:120])

    # Autonomous Goal Engine (Phase 4.3) — the goals this decision should serve.
    try:
        from aicmo.modules.operations import goals as ops_goals

        sig.business_goals = await ops_goals.active_goal_summaries(
            session, brand_id=brand_id, limit=6
        )
    except Exception as e:
        log.warning("decision.signals.goals_failed", error=str(e)[:120])

    return sig
