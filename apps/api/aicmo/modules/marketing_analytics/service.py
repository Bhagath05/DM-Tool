"""Marketing-analytics service — the DB glue over ConnectorMetric.

Read-only projection: loads the brand's `ConnectorMetric` snapshots, normalizes
them, and produces the platform summary, cross-platform comparison, trends, and
the Performance Marketer report. Writes nothing, publishes nothing, spends
nothing (autonomy-safe). Reuses `ConnectorMetric` — adds no table.
"""

from __future__ import annotations

import uuid
from collections import defaultdict
from datetime import UTC, datetime, timedelta

import structlog
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from aicmo.modules.advisor.connectors_models import ConnectorMetric
from aicmo.modules.integrations.models import IntegrationConnection
from aicmo.modules.marketing_analytics import content as content_analytics
from aicmo.modules.marketing_analytics import normalize
from aicmo.modules.marketing_analytics.normalize import CanonicalMetric
from aicmo.modules.marketing_analytics.rules import (
    MetricState,
    confidence_band,
    generate_insights,
)
from aicmo.modules.marketing_analytics.schemas import (
    AdvisorAnalyticsSignal,
    AdvisorPlatformEvidence,
    CrossPlatformEntry,
    CrossPlatformRow,
    DataSufficiency,
    Insight,
    InsightsResponse,
    MetricEvidence,
    MetricTrend,
    PerformanceMarketerReport,
    PeriodComparison,
    PlatformMetric,
    PlatformsResponse,
    PlatformSummary,
    TrendPoint,
    TrendsResponse,
)
from aicmo.modules.marketing_analytics.sufficiency import (
    Sufficiency,
    SufficiencyLevel,
    assess,
    can_claim_comparison,
)
from aicmo.modules.marketing_analytics.timeseries import (
    Observation,
    bucket_series,
    period_over_period,
)

log = structlog.get_logger()

# How far back to load snapshots. 90 days is enough for the strong (multi-week)
# sufficiency tier and monthly trend buckets without unbounded scans.
_LOOKBACK_DAYS = 90
_DEFAULT_WINDOW_DAYS = 7

# Generic family labels for the cross-platform comparison surface (independent
# of any one provider's wording, so an "audience" row reads cleanly whether it
# mixes followers and subscribers).
_FAMILY_LABELS: dict[str, str] = {
    normalize.AUDIENCE: "Audience size",
    normalize.ENGAGEMENT_RATE: "Engagement rate",
    normalize.REACH: "Reach",
    normalize.IMPRESSIONS: "Impressions",
    normalize.WEBSITE_CLICKS: "Website clicks",
}


def _now() -> datetime:
    return datetime.now(UTC)


def _latest_value(observations: list[Observation]) -> float:
    return max(observations, key=lambda o: o.observed_at).value


async def _load_groups(
    session: AsyncSession, *, brand_id: uuid.UUID
) -> tuple[dict[tuple[str, str], list[Observation]], datetime | None]:
    """Load snapshots grouped by (provider_slug, raw_metric_key).

    Observation time is ``period_end`` when the provider set it, else the sync
    time — both are reliable clocks for ordering snapshots.
    """
    since = _now() - timedelta(days=_LOOKBACK_DAYS)
    stmt = (
        select(ConnectorMetric)
        .where(
            ConnectorMetric.brand_id == brand_id,
            ConnectorMetric.synced_at >= since,
        )
        .order_by(ConnectorMetric.synced_at)
    )
    rows = (await session.execute(stmt)).scalars().all()
    groups: dict[tuple[str, str], list[Observation]] = defaultdict(list)
    last_sync: datetime | None = None
    for m in rows:
        observed_at = m.period_end or m.synced_at
        groups[(m.provider_slug, m.metric_key)].append(
            Observation(value=float(m.metric_value), observed_at=observed_at)
        )
        if last_sync is None or m.synced_at > last_sync:
            last_sync = m.synced_at
    return groups, last_sync


def _collapse_to_canonical(
    groups: dict[tuple[str, str], list[Observation]],
) -> dict[tuple[str, str], tuple[CanonicalMetric, list[Observation]]]:
    """Collapse raw keys onto one representative per (provider, canonical family).

    When a provider reports two raw keys in the same family (e.g. Facebook
    ``page_followers`` and ``page_fans`` both audience), the richer series wins
    (more snapshots; then higher latest value) so a family is never
    double-counted in comparisons.
    """
    by_pc: dict[tuple[str, str], tuple[CanonicalMetric, list[Observation]]] = {}
    for (provider, key), obs in groups.items():
        canon = normalize.normalize_metric(key)
        pc = (provider, canon.canonical)
        existing = by_pc.get(pc)
        if existing is None:
            by_pc[pc] = (canon, obs)
            continue
        _, ex_obs = existing
        if len(obs) > len(ex_obs) or (
            len(obs) == len(ex_obs) and _latest_value(obs) > _latest_value(ex_obs)
        ):
            by_pc[pc] = (canon, obs)
    return by_pc


def _build_states(
    by_pc: dict[tuple[str, str], tuple[CanonicalMetric, list[Observation]]],
    *,
    window_days: int,
    now: datetime,
) -> tuple[list[MetricState], dict[str, list[PlatformMetric]]]:
    states: list[MetricState] = []
    platform_metrics: dict[str, list[PlatformMetric]] = defaultdict(list)
    window = f"{window_days}d"
    for (provider, _canonical), (canon, obs) in sorted(by_pc.items()):
        obs_sorted = sorted(obs, key=lambda o: o.observed_at)
        latest = obs_sorted[-1].value
        comp = period_over_period(obs_sorted, window_days=window_days, now=now)
        platform = normalize.provider_label(provider)
        platform_metrics[provider].append(
            PlatformMetric(
                metric=canon.canonical,
                label=canon.label,
                kind=canon.kind.value,
                value=latest,
                unit=canon.unit,
                comparable=canon.comparable_across_platforms,
                trend=comp.trend,
                change_percent=comp.change_percent,
                window=window,
            )
        )
        states.append(
            MetricState(
                provider_slug=provider,
                platform=platform,
                canonical=canon.canonical,
                label=canon.label,
                kind=canon.kind.value,
                unit=canon.unit,
                comparable=canon.comparable_across_platforms,
                current=latest,
                comparison=comp,
            )
        )
    return states, platform_metrics


def _cross_platform_rows(states: list[MetricState]) -> list[CrossPlatformRow]:
    by_family: dict[str, list[MetricState]] = defaultdict(list)
    for s in states:
        if s.comparable:
            by_family[s.canonical].append(s)
    rows: list[CrossPlatformRow] = []
    for family, members in sorted(by_family.items()):
        if len({m.provider_slug for m in members}) < 2:
            continue  # a single platform is not a cross-platform comparison
        ranked = sorted(members, key=lambda m: m.current, reverse=True)
        entries = [
            CrossPlatformEntry(
                provider_slug=m.provider_slug,
                platform=m.platform,
                value=m.current,
                change_percent=m.comparison.change_percent,
                trend=m.comparison.trend,
            )
            for m in ranked
        ]
        leader = ranked[0]
        rows.append(
            CrossPlatformRow(
                metric=family,
                label=_FAMILY_LABELS.get(family, members[0].label),
                kind=members[0].kind,
                unit=members[0].unit,
                entries=entries,
                leader_provider=leader.provider_slug,
                leader_platform=leader.platform,
            )
        )
    return rows


def _sufficiency_model(s: Sufficiency) -> DataSufficiency:
    return DataSufficiency(
        level=s.level.value,
        days_covered=s.days_covered,
        observations=s.observations,
        message=s.message,
    )


def _all_observations(
    groups: dict[tuple[str, str], list[Observation]],
) -> list[Observation]:
    return [o for obs in groups.values() for o in obs]


# ---------------- endpoint services ----------------


async def get_platforms(
    session: AsyncSession, *, brand_id: uuid.UUID, window_days: int = _DEFAULT_WINDOW_DAYS
) -> PlatformsResponse:
    groups, last_sync = await _load_groups(session, brand_id=brand_id)
    sufficiency = assess(_all_observations(groups))
    if not groups:
        return PlatformsResponse(
            platforms=[],
            comparison=[],
            sufficiency=_sufficiency_model(sufficiency),
            last_sync_at=None,
            has_data=False,
        )
    by_pc = _collapse_to_canonical(groups)
    states, platform_metrics = _build_states(by_pc, window_days=window_days, now=_now())
    platforms = [
        PlatformSummary(
            provider_slug=provider,
            platform=normalize.provider_label(provider),
            metrics=sorted(metrics, key=lambda m: m.label),
            has_data=bool(metrics),
        )
        for provider, metrics in sorted(platform_metrics.items())
    ]
    return PlatformsResponse(
        platforms=platforms,
        comparison=_cross_platform_rows(states),
        sufficiency=_sufficiency_model(sufficiency),
        last_sync_at=last_sync.isoformat() if last_sync else None,
        has_data=True,
    )


async def get_trends(
    session: AsyncSession,
    *,
    brand_id: uuid.UUID,
    window_days: int = _DEFAULT_WINDOW_DAYS,
    granularity: str = "day",
) -> TrendsResponse:
    if granularity not in ("day", "week", "month"):
        granularity = "day"
    groups, _ = await _load_groups(session, brand_id=brand_id)
    sufficiency = assess(_all_observations(groups))
    if not groups:
        return TrendsResponse(
            trends=[],
            sufficiency=_sufficiency_model(sufficiency),
            window_days=window_days,
            granularity=granularity,
            has_data=False,
        )
    by_pc = _collapse_to_canonical(groups)
    now = _now()
    trends: list[MetricTrend] = []
    for (provider, _canonical), (canon, obs) in sorted(by_pc.items()):
        obs_sorted = sorted(obs, key=lambda o: o.observed_at)
        buckets = bucket_series(obs_sorted, granularity=granularity)
        comp = period_over_period(obs_sorted, window_days=window_days, now=now)
        trends.append(
            MetricTrend(
                provider_slug=provider,
                platform=normalize.provider_label(provider),
                metric=canon.canonical,
                label=canon.label,
                kind=canon.kind.value,
                granularity=granularity,
                points=[TrendPoint(bucket=b.bucket, value=b.value) for b in buckets],
                comparison=PeriodComparison(
                    current=comp.current,
                    previous=comp.previous,
                    absolute_change=comp.absolute_change,
                    change_percent=comp.change_percent,
                    trend=comp.trend,
                    window_days=window_days,
                ),
            )
        )
    return TrendsResponse(
        trends=trends,
        sufficiency=_sufficiency_model(sufficiency),
        window_days=window_days,
        granularity=granularity,
        has_data=True,
    )


async def get_insights(
    session: AsyncSession,
    *,
    brand_id: uuid.UUID,
    window_days: int = _DEFAULT_WINDOW_DAYS,
) -> InsightsResponse:
    groups, _ = await _load_groups(session, brand_id=brand_id)
    sufficiency = assess(_all_observations(groups))
    if not groups:
        return InsightsResponse(
            insights=[], sufficiency=_sufficiency_model(sufficiency), has_data=False
        )
    by_pc = _collapse_to_canonical(groups)
    states, _ = _build_states(by_pc, window_days=window_days, now=_now())
    insights = generate_insights(states, sufficiency=sufficiency, window_days=window_days)
    return InsightsResponse(
        insights=insights,
        sufficiency=_sufficiency_model(sufficiency),
        has_data=True,
    )


async def performance_report(
    session: AsyncSession,
    *,
    brand_id: uuid.UUID,
    window_days: int = _DEFAULT_WINDOW_DAYS,
    business_name: str | None = None,
    narrate: bool = False,
) -> PerformanceMarketerReport:
    groups, _ = await _load_groups(session, brand_id=brand_id)
    sufficiency = assess(_all_observations(groups))
    generated_at = _now().isoformat()

    if not groups:
        return PerformanceMarketerReport(
            headline="Not enough data yet",
            sufficiency=_sufficiency_model(sufficiency),
            whats_working=[],
            whats_not_working=[],
            recommendations=[],
            platform_comparison=[],
            narrated=False,
            has_data=False,
            generated_at=generated_at,
        )

    by_pc = _collapse_to_canonical(groups)
    states, _ = _build_states(by_pc, window_days=window_days, now=_now())
    insights = generate_insights(states, sufficiency=sufficiency, window_days=window_days)
    comparison = _cross_platform_rows(states)

    # Phase 5 — fold per-content wins into the Performance Marketer's findings.
    content_insights, _ = await _safe_content_signal(session, brand_id=brand_id)
    insights = insights + content_insights

    narrated = False
    if narrate and insights:
        narrated_insights = await _narrate(insights, business_name=business_name)
        if narrated_insights is not None:
            insights = narrated_insights
            narrated = True

    working = [i for i in insights if i.severity == "good"]
    attention = [i for i in insights if i.severity == "attention"]
    recommendations = [i for i in insights if i.severity == "neutral"]

    headline = _headline(
        working=len(working),
        attention=len(attention),
        sufficiency_msg=sufficiency.message,
        has_insights=bool(insights),
    )
    return PerformanceMarketerReport(
        headline=headline,
        sufficiency=_sufficiency_model(sufficiency),
        whats_working=working,
        whats_not_working=attention,
        recommendations=recommendations,
        platform_comparison=comparison,
        narrated=narrated,
        has_data=True,
        generated_at=generated_at,
    )


def _headline(*, working: int, attention: int, sufficiency_msg: str, has_insights: bool) -> str:
    if not has_insights:
        return f"Still gathering signal — {sufficiency_msg.lower()}"
    if attention and working:
        return "Some wins to build on, and a couple of things to fix."
    if working:
        return "Here's what's working — let's do more of it."
    if attention:
        return "A few things need your attention this week."
    return "Here's your latest read on performance."


async def _narrate(insights: list[Insight], *, business_name: str | None) -> list[Insight] | None:
    """Ask the LLM to rephrase prose only; evidence/confidence stay authoritative.

    Returns None on any failure so the caller keeps the deterministic insights.
    """
    from pydantic import BaseModel, Field

    from aicmo.llm import get_llm_router
    from aicmo.llm.providers.base import LLMMessage
    from aicmo.modules.marketing_analytics.prompts import (
        PERFORMANCE_MARKETER_SYSTEM,
        build_narration_prompt,
    )

    class _Rewrite(BaseModel):
        id: str
        observation: str = Field(min_length=4)
        interpretation: str = Field(min_length=4)
        recommendation: str = Field(min_length=4)
        expected_result: str = Field(min_length=4)

    class _Narration(BaseModel):
        rewrites: list[_Rewrite]

    lines: list[str] = []
    for i in insights:
        ev = "; ".join(
            f"{e.label} {e.change_percent:+.0f}%" if e.change_percent is not None else e.label
            for e in i.evidence
        )
        lines.append(
            f"- id={i.id} | metric={i.evidence[0].metric if i.evidence else ''} | "
            f"evidence=[{ev}]\n  observation: {i.observation}\n  interpretation: {i.interpretation}\n"
            f"  recommendation: {i.recommendation}\n  expected_result: {i.expected_result}"
        )
    prompt = build_narration_prompt(business_name, "\n".join(lines))

    try:
        router = get_llm_router()
        result = await router.generate(
            response_schema=_Narration,
            system=PERFORMANCE_MARKETER_SYSTEM,
            messages=[LLMMessage(role="user", content=prompt)],
            temperature=0.4,
            max_tokens=2500,
        )
    except Exception as e:  # narration is optional — never break the report
        log.warning("marketing_analytics.narration_failed", error=str(e)[:200])
        return None

    by_id = {r.id: r for r in result.data.rewrites}
    out: list[Insight] = []
    for i in insights:
        r = by_id.get(i.id)
        if r is None:
            out.append(i)
            continue
        # Rephrase prose only. evidence, confidence, reason, impact, window untouched.
        out.append(
            i.model_copy(
                update={
                    "observation": r.observation,
                    "interpretation": r.interpretation,
                    "recommendation": r.recommendation,
                    "expected_result": r.expected_result,
                }
            )
        )
    return out


# ==================================================================
#  Advisor integration signal (Phase 4) — read-only, one-directional
# ==================================================================

# User-facing empty-state copy (Constitution §12). Plain language, no jargon.
_EMPTY_MESSAGES: dict[str, str] = {
    "no_connection": "Connect a marketing account to start receiving performance insights.",
    "no_metrics": "Your account is connected, but we don't have enough performance data yet.",
    "short_history": (
        "We're still collecting data. Short-term observations are available, but reliable "
        "weekly trends aren't ready yet."
    ),
}

# Low-signal families we omit from the compact advisor evidence (kept out of the
# prompt to stay terse — they are still available on the full analytics surface).
_SIGNAL_SKIP_FAMILIES = frozenset({normalize.FOLLOWING, normalize.CONTENT_COUNT})


async def _has_active_connection(session: AsyncSession, *, brand_id: uuid.UUID) -> bool:
    """True if the brand has at least one ACTIVE integration connection.

    Lets the signal distinguish 'no account connected' from 'connected but no
    metrics yet' for honest empty states. Tenant-scoped by brand_id.
    """
    stmt = (
        select(IntegrationConnection.id)
        .where(
            IntegrationConnection.brand_id == brand_id,
            IntegrationConnection.state == "ACTIVE",
        )
        .limit(1)
    )
    return (await session.execute(stmt)).first() is not None


def _metric_evidence(state: MetricState, window: str) -> MetricEvidence:
    c = state.comparison
    return MetricEvidence(
        metric=state.canonical,
        label=state.label,
        provider=state.provider_slug,
        platform=state.platform,
        current=c.current,
        previous=c.previous,
        absolute_change=c.absolute_change,
        change_percent=c.change_percent,
        window=window,
    )


def _overall_band(insights: list[Insight], sufficiency: Sufficiency) -> str:
    if insights:
        return confidence_band(max(i.confidence for i in insights))
    if sufficiency.level == SufficiencyLevel.STRONG:
        return "medium"
    if sufficiency.level == SufficiencyLevel.WEEKLY:
        return "low"
    return "speculative"


def _signal_headline(
    insights: list[Insight], sufficiency: Sufficiency, empty_message: str | None
) -> str:
    if empty_message:
        return empty_message
    if insights:
        # Prefer a positive win, else the first thing needing attention.
        for i in insights:
            if i.severity == "good":
                return i.observation
        return insights[0].observation
    return "Your platforms are being tracked — here's the latest read."


async def advisor_signal(
    session: AsyncSession,
    *,
    brand_id: uuid.UUID,
    window_days: int = _DEFAULT_WINDOW_DAYS,
) -> AdvisorAnalyticsSignal:
    """Build the read-only analytics signal the advisor consumes.

    COMPUTED values only. Tenant-scoped by brand_id. Never writes, never touches
    ConnectorMetric / connections / collection jobs — a pure read projection.
    """
    groups, last_sync = await _load_groups(session, brand_id=brand_id)
    sufficiency = assess(_all_observations(groups))
    window = f"{window_days}d"
    # Per-content evidence (Phase 5) — independent of account-level metrics, so
    # attached in every branch. Failure-isolated (never breaks the signal).
    content_insights, top_content = await _safe_content_signal(session, brand_id=brand_id)

    if not groups:
        connected = await _has_active_connection(session, brand_id=brand_id)
        reason = "no_metrics" if connected else "no_connection"
        message = _EMPTY_MESSAGES[reason]
        return AdvisorAnalyticsSignal(
            has_data=False,
            connected=connected,
            data_sufficiency=sufficiency.level.value,
            window=window,
            headline=message,
            empty_reason=reason,
            empty_message=message,
            confidence_band="speculative",
            last_sync_at=last_sync.isoformat() if last_sync else None,
            content_insights=content_insights,
            top_content=top_content,
        )

    by_pc = _collapse_to_canonical(groups)
    states, _ = _build_states(by_pc, window_days=window_days, now=_now())
    insights = generate_insights(states, sufficiency=sufficiency, window_days=window_days)

    # Compact per-platform evidence (skip low-signal families).
    platforms: list[AdvisorPlatformEvidence] = []
    evidence: list[MetricEvidence] = []
    by_provider: dict[str, list[MetricState]] = defaultdict(list)
    for s in states:
        if s.canonical in _SIGNAL_SKIP_FAMILIES:
            continue
        by_provider[s.provider_slug].append(s)
    for provider in sorted(by_provider):
        members = by_provider[provider]
        metrics = [_metric_evidence(s, window) for s in members]
        platforms.append(
            AdvisorPlatformEvidence(
                provider_slug=provider,
                platform=normalize.provider_label(provider),
                metrics=metrics,
            )
        )
        # Traceable claims = metrics with a real period comparison.
        evidence.extend(
            m for m, s in zip(metrics, members, strict=True) if s.comparison.trend != "insufficient"
        )

    # has_data but too little history for a weekly trend → short-history state.
    can_trend = can_claim_comparison(sufficiency.level, window_days=window_days)
    empty_reason = None if can_trend else "short_history"
    empty_message = None if can_trend else _EMPTY_MESSAGES["short_history"]

    return AdvisorAnalyticsSignal(
        has_data=True,
        connected=True,
        data_sufficiency=sufficiency.level.value,
        window=window,
        headline=_signal_headline(insights, sufficiency, empty_message),
        empty_reason=empty_reason,  # type: ignore[arg-type]
        empty_message=empty_message,
        platforms=platforms,
        insights=insights,
        evidence=evidence,
        confidence_band=_overall_band(insights, sufficiency),  # type: ignore[arg-type]
        last_sync_at=last_sync.isoformat() if last_sync else None,
        content_insights=content_insights,
        top_content=top_content,
    )


async def _safe_content_signal(session: AsyncSession, *, brand_id: uuid.UUID):
    """content_analytics.content_signal wrapped so a content read can never
    break the advisor signal."""
    try:
        return await content_analytics.content_signal(session, brand_id=brand_id)
    except Exception as e:  # degrade — content evidence is additive
        log.warning("marketing_analytics.content_signal_failed", error=str(e)[:200])
        return [], []
