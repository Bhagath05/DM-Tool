"""Module 7 — collectors that READ each module's already-produced output and
normalise it into FeedItems. No analysis is performed here; every collector is
guarded so a sparse or partially-broken source degrades gracefully.
"""

from __future__ import annotations

import uuid

import structlog
from sqlalchemy.ext.asyncio import AsyncSession

from aicmo.modules.insights.ranking import make_id, severity_from_confidence
from aicmo.modules.insights.schemas import FeedItem, LiveSurface, SourceStatus
from aicmo.tenancy.context import TenantContext

log = structlog.get_logger()


def _item(**kw) -> FeedItem:
    kw.setdefault("priority_score", 0.0)  # ranking fills this later
    kw["group_key"] = kw["category"]
    kw["id"] = make_id(kw["source_module"], kw["category"], kw["title"])
    return FeedItem(**kw)


async def _from_learning(
    session: AsyncSession, *, brand_id: uuid.UUID
) -> tuple[list[FeedItem], SourceStatus]:
    from aicmo.modules.learning import insights_service

    items: list[FeedItem] = []
    rows = await insights_service.list_insights(
        session, brand_id=brand_id, only_active=True, limit=30
    )
    for r in rows:
        negative = r.direction == "negative"
        items.append(
            _item(
                source_module="learning",
                source_label="Learning Engine",
                link="/learning",
                category=r.category,
                title=r.observation,
                detail=r.observation,
                why_surfaced="Learned from this brand's real results.",
                recommendation=r.recommendation,
                expected_result=r.expected_result,
                evidence=list(r.evidence),
                confidence=r.confidence,
                severity=severity_from_confidence(r.confidence, negative=negative),
            )
        )
    return items, SourceStatus(
        module="learning", label="Learning Engine", contributed=len(items)
    )


async def _from_advisor(
    session: AsyncSession, *, brand_id: uuid.UUID
) -> tuple[list[FeedItem], SourceStatus]:
    from aicmo.modules.advisor import service as advisor_service

    items: list[FeedItem] = []
    rows = await advisor_service.list_history(session, brand_id=brand_id, limit=40)
    for r in rows:
        action = getattr(r, "recommended_action", None)
        status = getattr(r, "outcome_status", None)
        # Only surface still-actionable coaching/opportunities.
        if not action or status in ("completed", "skipped"):
            continue
        score = getattr(r, "effectiveness_score", None)
        evidence = [
            x
            for x in (getattr(r, "observation", None), getattr(r, "root_cause", None))
            if x
        ]
        items.append(
            _item(
                source_module="advisor",
                source_label="AI Coach & Opportunities",
                link="/dashboard",
                category="recommendation",
                title=r.title,
                detail=getattr(r, "description", "") or r.title,
                why_surfaced="An open recommendation from your AI Coach.",
                recommendation=action,
                expected_result=getattr(r, "expected_impact", None),
                evidence=evidence,
                confidence=score,
                severity=severity_from_confidence(score),
                urgency="this_week",
            )
        )
    return items, SourceStatus(
        module="advisor", label="AI Coach & Opportunities", contributed=len(items)
    )


async def _from_performance(
    session: AsyncSession, *, tenant: TenantContext
) -> tuple[list[FeedItem], SourceStatus]:
    from aicmo.modules.performance import service as performance_service

    items: list[FeedItem] = []
    overview = await performance_service.overview(session, tenant=tenant)
    if overview.has_data:
        for d in overview.diagnostics:
            if getattr(d, "status", None) in ("dismissed", "resolved"):
                continue
            ev_extra = [str(v) for v in (d.evidence or {}).values()][:4]
            items.append(
                _item(
                    source_module="performance",
                    source_label="Performance Dashboard",
                    link="/performance",
                    category=str(d.kind),
                    title=d.what_happened,
                    detail=d.why,
                    why_surfaced="Detected in your performance data.",
                    recommendation=d.recommendation,
                    expected_result=d.expected_result,
                    evidence=[d.reason, *ev_extra],
                    confidence=d.confidence,
                    severity=severity_from_confidence(d.confidence),
                    urgency="this_week",
                    impact_category=str(d.impact_category),
                )
            )
    return items, SourceStatus(
        module="performance", label="Performance Dashboard", contributed=len(items)
    )


async def _from_strategy(
    session: AsyncSession, *, brand_id: uuid.UUID
) -> tuple[list[FeedItem], SourceStatus]:
    from aicmo.modules.strategist import service as strategist_service
    from aicmo.modules.strategist.schemas import MarketingStrategy

    items: list[FeedItem] = []
    record = await strategist_service.latest(session, brand_id=brand_id)
    if record is not None and record.status == "completed" and record.strategy:
        strat = MarketingStrategy.model_validate(record.strategy)
        items.append(
            _item(
                source_module="strategy",
                source_label="Marketing Strategy",
                link="/strategy",
                category="strategy",
                title="Your strategy's highest-leverage move",
                detail=strat.recommendation,
                why_surfaced="The top move from your current marketing strategy.",
                recommendation=strat.recommendation,
                expected_result=strat.expected_result,
                evidence=[strat.reason] if strat.reason else [],
                confidence=strat.confidence,
                severity=severity_from_confidence(strat.confidence),
                urgency="this_month",
            )
        )
        # Surface up to two high-priority pillars as their own items.
        pillars = [
            ("content", strat.content),
            ("seo", strat.seo),
            ("local_seo", strat.local_seo),
            ("paid_ads", strat.paid_ads),
            ("organic_social", strat.organic_social),
            ("email", strat.email),
            ("influencer", strat.influencer),
        ]
        high = [(n, p) for n, p in pillars if p.priority == "high"][:2]
        for name, p in high:
            items.append(
                _item(
                    source_module="strategy",
                    source_label="Marketing Strategy",
                    link="/strategy",
                    category="strategy",
                    title=f"Priority channel: {name.replace('_', ' ')}",
                    detail=p.focus,
                    why_surfaced="A high-priority pillar in your strategy.",
                    recommendation=p.actions[0] if p.actions else p.focus,
                    expected_result=None,
                    evidence=[p.why] if p.why else [],
                    confidence=None,
                    severity="medium",
                    urgency="this_month",
                    channels=[name],
                )
            )
    return items, SourceStatus(
        module="strategy", label="Marketing Strategy", contributed=len(items)
    )


async def _from_business(
    session: AsyncSession, *, brand_id: uuid.UUID
) -> tuple[list[FeedItem], SourceStatus]:
    from aicmo.modules.onboarding import service as onboarding_service
    from aicmo.modules.onboarding.schemas import BusinessProfileResponse

    items: list[FeedItem] = []
    profile_row = await onboarding_service.get_profile_or_none(session, brand_id)
    if profile_row is not None:
        p = BusinessProfileResponse.model_validate(profile_row)
        analysis = p.analysis
        if analysis is not None:
            for opp in list(analysis.marketing_opportunities or [])[:3]:
                items.append(
                    _item(
                        source_module="business_understanding",
                        source_label="Business Understanding",
                        link="/dashboard",
                        category="opportunity",
                        title=opp,
                        detail=opp,
                        why_surfaced="A marketing opportunity from your business analysis.",
                        recommendation=opp,
                        expected_result=None,
                        evidence=[],
                        confidence=None,
                        severity="low",
                        urgency="monitor",
                    )
                )
            for block in list(getattr(analysis, "growth_bottlenecks", None) or [])[:2]:
                items.append(
                    _item(
                        source_module="business_understanding",
                        source_label="Business Understanding",
                        link="/dashboard",
                        category="bottleneck",
                        title=block,
                        detail=block,
                        why_surfaced="A growth bottleneck flagged in your analysis.",
                        recommendation="Address this bottleneck before scaling spend.",
                        expected_result=None,
                        evidence=[],
                        confidence=None,
                        severity="high",
                        urgency="this_month",
                    )
                )
    return items, SourceStatus(
        module="business_understanding",
        label="Business Understanding",
        contributed=len(items),
    )


def _live_surfaces() -> list[LiveSurface]:
    """Generative modules we deliberately do NOT re-run (no new intelligence).
    The user opens them to generate fresh output on demand."""
    return [
        LiveSurface(
            module="planner",
            label="Task Planner",
            description="Generate today's concrete task plan on demand.",
            link="/planner",
        ),
        LiveSurface(
            module="decision",
            label="Decision Engine",
            description="Generate fresh, evidence-grounded decisions on demand.",
            link="/decisions",
        ),
        LiveSurface(
            module="competitors",
            label="Competitor Watch",
            description="Run a live competitor scan on demand.",
            link="/competitors",
        ),
    ]


_COLLECTORS_BRAND = (_from_learning, _from_advisor, _from_strategy, _from_business)


async def collect_all(
    session: AsyncSession, *, tenant: TenantContext
) -> tuple[list[FeedItem], list[SourceStatus], list[LiveSurface]]:
    """Run every collector, guarded — one failing source never sinks the feed."""
    items: list[FeedItem] = []
    sources: list[SourceStatus] = []

    for collector in _COLLECTORS_BRAND:
        try:
            got, status = await collector(session, brand_id=tenant.brand_id)
            items.extend(got)
            sources.append(status)
        except Exception as e:
            name = collector.__name__.replace("_from_", "")
            log.warning("insights.collect_failed", source=name, error=str(e)[:120])
            sources.append(
                SourceStatus(module=name, label=name, contributed=0, ok=False, note="unavailable")
            )

    try:
        got, status = await _from_performance(session, tenant=tenant)
        items.extend(got)
        sources.append(status)
    except Exception as e:
        log.warning("insights.collect_failed", source="performance", error=str(e)[:120])
        sources.append(
            SourceStatus(
                module="performance",
                label="Performance Dashboard",
                contributed=0,
                ok=False,
                note="unavailable",
            )
        )

    return items, sources, _live_surfaces()
