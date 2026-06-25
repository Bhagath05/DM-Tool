"""Autonomous Marketing Agent — evidence-backed reports."""

from __future__ import annotations

import uuid
from datetime import UTC, datetime, timedelta

import structlog
from pydantic import BaseModel, Field
from sqlalchemy import desc, func, select
from sqlalchemy.ext.asyncio import AsyncSession

from aicmo.llm import get_llm_router
from aicmo.llm.providers.base import LLMMessage
from aicmo.modules.advisor.brain import brain_has_minimum, brain_to_prompt_block, load_business_brain
from aicmo.modules.advisor.connectors import load_connector_context
from aicmo.modules.advisor.outcomes import load_outcome_context
from aicmo.modules.advisor.prompts import INTELLIGENCE_SYSTEM_PROMPT
from aicmo.modules.advisor.schemas import (
    AgentReport,
    AgentReportRecommendation,
    AgentReportSection,
    AgentReportType,
    DataSourceRef,
)
from aicmo.modules.ads.models import GeneratedAd
from aicmo.modules.analytics import service as analytics_service
from aicmo.modules.content.models import GeneratedContent
from aicmo.modules.onboarding.schemas import BusinessProfileResponse
from aicmo.tenancy.context import TenantContext

log = structlog.get_logger()


class _AgentNarrative(BaseModel):
    summary: str = Field(min_length=10)
    sections: list[AgentReportSection] = Field(default_factory=list)
    recommendations: list[AgentReportRecommendation] = Field(default_factory=list)
    confidence: int = Field(ge=0, le=100)


def _period_for(report_type: AgentReportType) -> tuple[datetime, datetime]:
    now = datetime.now(UTC)
    if report_type == "daily":
        return now - timedelta(days=1), now
    if report_type == "weekly":
        return now - timedelta(days=7), now
    if report_type == "monthly":
        return now - timedelta(days=30), now
    if report_type == "lead_trends":
        return now - timedelta(days=30), now
    if report_type == "campaign_performance":
        return now - timedelta(days=30), now
    return now - timedelta(days=30), now


async def generate_agent_report(
    session: AsyncSession,
    *,
    profile: BusinessProfileResponse,
    tenant: TenantContext,
    report_type: AgentReportType,
) -> AgentReport:
    now = datetime.now(UTC)
    period_start, period_end = _period_for(report_type)
    generated_at = now.isoformat()

    brain = load_business_brain(profile)
    if not brain_has_minimum(brain):
        return AgentReport(
            report_type=report_type,
            ready=False,
            summary="Complete your Business Brain before generating reports.",
            setup_steps=["Complete business onboarding", "Set industry and target audience"],
            period_start=period_start.isoformat(),
            period_end=period_end.isoformat(),
            generated_at=generated_at,
        )

    overview = await analytics_service.overview(session, brand_id=tenant.brand_id)
    timeline = await analytics_service.timeline(
        session, brand_id=tenant.brand_id, window_days=30
    )
    outcome_ctx = await load_outcome_context(session, brand_id=tenant.brand_id)
    connector_ctx = await load_connector_context(session, brand_id=tenant.brand_id)

    data_sources: list[DataSourceRef] = [
        DataSourceRef(key="leads_7d", label="Leads (7 days)", value=str(overview.leads_7d)),
        DataSourceRef(
            key="leads_30d", label="Leads (30 days)", value=str(overview.leads_30d)
        ),
        DataSourceRef(key="hot_leads", label="Hot leads", value=str(overview.hot_leads)),
    ]
    data_sources.extend(connector_ctx.get("data_sources", [])[:5])

    signals = await _gather_report_signals(
        session,
        brand_id=tenant.brand_id,
        report_type=report_type,
        overview=overview,
        timeline=timeline,
        period_start=period_start,
    )

    has_evidence = (
        overview.total_leads > 0
        or overview.leads_7d > 0
        or bool(connector_ctx.get("has_data"))
        or bool(outcome_ctx.get("recent_outcomes"))
        or len(signals) > 3
    )

    if not has_evidence:
        steps = ["Publish a lead page and share its link"]
        if not connector_ctx.get("connected_providers"):
            steps.insert(0, "Connect Instagram or Facebook for platform metrics")
        return AgentReport(
            report_type=report_type,
            ready=False,
            summary="Not enough data to produce an evidence-backed report.",
            setup_steps=steps,
            data_sources_used=data_sources,
            period_start=period_start.isoformat(),
            period_end=period_end.isoformat(),
            generated_at=generated_at,
        )

    cap = 75 if outcome_ctx.get("recent_outcomes") else 60
    if connector_ctx.get("has_data"):
        cap = min(95, cap + 15)

    user_prompt = _build_agent_prompt(
        report_type=report_type,
        brain_block=brain_to_prompt_block(brain),
        signals=signals,
        outcome_ctx=outcome_ctx,
        connector_ctx=connector_ctx,
        confidence_cap=cap,
        period_start=period_start,
        period_end=period_end,
    )

    try:
        router = get_llm_router()
        result = await router.generate(
            response_schema=_AgentNarrative,
            system=INTELLIGENCE_SYSTEM_PROMPT,
            messages=[LLMMessage(role="user", content=user_prompt)],
            temperature=0.45,
            max_tokens=4000,
        )
        narrative = result.data
        confidence = min(narrative.confidence, cap)
        recs = [
            r.model_copy(update={"confidence": min(r.confidence, cap)})
            for r in narrative.recommendations
        ]
        return AgentReport(
            report_type=report_type,
            ready=True,
            summary=narrative.summary,
            sections=narrative.sections,
            recommendations=recs,
            confidence=confidence,
            data_sources_used=data_sources,
            period_start=period_start.isoformat(),
            period_end=period_end.isoformat(),
            generated_at=generated_at,
        )
    except Exception as e:
        log.warning("advisor.agent_report_failed", report_type=report_type, error=str(e))
        return _deterministic_agent_report(
            report_type=report_type,
            overview=overview,
            signals=signals,
            data_sources=data_sources,
            period_start=period_start,
            period_end=period_end,
            generated_at=generated_at,
            cap=cap,
        )


async def _gather_report_signals(
    session: AsyncSession,
    *,
    brand_id: uuid.UUID,
    report_type: AgentReportType,
    overview,
    timeline,
    period_start: datetime,
) -> list[str]:
    signals = [
        f"Total leads: {overview.total_leads}",
        f"Leads (7d): {overview.leads_7d}",
        f"Leads (30d): {overview.leads_30d}",
        f"Hot leads: {overview.hot_leads}",
        f"Conversion rate: {overview.conversion_rate:.1%}",
    ]

    if report_type in ("daily", "weekly", "lead_trends"):
        recent_days = [p for p in timeline.days if p.leads > 0][-7:]
        for pt in recent_days:
            signals.append(f"Leads on {pt.day}: {pt.leads}")

    if report_type in ("weekly", "monthly", "campaign_performance"):
        content_count = (
            await session.execute(
                select(func.count())
                .select_from(GeneratedContent)
                .where(
                    GeneratedContent.brand_id == brand_id,
                    GeneratedContent.created_at >= period_start,
                )
            )
        ).scalar_one()
        ad_count = (
            await session.execute(
                select(func.count())
                .select_from(GeneratedAd)
                .where(
                    GeneratedAd.brand_id == brand_id,
                    GeneratedAd.created_at >= period_start,
                )
            )
        ).scalar_one()
        signals.append(f"Content pieces created: {content_count}")
        signals.append(f"Ads created: {ad_count}")

    if report_type == "budget":
        signals.append(
            "Budget optimization requires connected ad accounts with spend data."
        )

    top_assets = await analytics_service.top_assets(session, brand_id=brand_id, limit=3)
    for row in top_assets.items[:3]:
        label = f"{row.source_asset_type}/{row.subtype}"
        signals.append(
            f"Top asset ({label}): {row.goal} — {row.leads} leads"
        )

    return signals


def _build_agent_prompt(
    *,
    report_type: AgentReportType,
    brain_block: str,
    signals: list[str],
    outcome_ctx: dict,
    connector_ctx: dict,
    confidence_cap: int,
    period_start: datetime,
    period_end: datetime,
) -> str:
    type_instructions = {
        "daily": "Daily growth report: what happened yesterday, why, what to do today.",
        "weekly": "Weekly strategy report: patterns across the week, strategic priorities.",
        "monthly": "Monthly marketing review: month-over-month trends, strategic adjustments.",
        "lead_trends": "Lead trend analysis: lead volume patterns, sources, bottlenecks.",
        "campaign_performance": "Campaign performance analysis: content and ad output vs lead results.",
        "budget": "Budget optimization: suggest allocation based on real performance signals only. Never invent spend amounts.",
    }
    parts = [
        f"REPORT TYPE: {report_type}",
        f"INSTRUCTION: {type_instructions[report_type]}",
        f"PERIOD: {period_start.date()} to {period_end.date()}",
        f"CONFIDENCE CAP: {confidence_cap}",
        "",
        "=== BUSINESS BRAIN ===",
        brain_block,
        "",
        "=== SIGNALS ===",
    ]
    for s in signals:
        parts.append(f"- {s}")

    if outcome_ctx.get("recent_outcomes"):
        parts.extend(["", "=== HISTORICAL OUTCOMES ==="])
        for o in outcome_ctx["recent_outcomes"][:5]:
            parts.append(f"- {o['title']}: {o.get('delta_summary', '')}")

    if connector_ctx.get("has_data"):
        parts.extend(["", "=== CONNECTED DATA ==="])
        for m in connector_ctx["metrics"][:10]:
            parts.append(f"- {m['provider']}/{m['key']}: {m['value']}")

    parts.append(
        "\nProduce summary, sections, and recommendations. "
        "Never fabricate metrics. If budget data is missing, say so."
    )
    return "\n".join(parts)


def _deterministic_agent_report(
    *,
    report_type: AgentReportType,
    overview,
    signals: list[str],
    data_sources: list[DataSourceRef],
    period_start: datetime,
    period_end: datetime,
    generated_at: str,
    cap: int,
) -> AgentReport:
    summary = (
        f"Lead activity: {overview.leads_7d} in the last 7 days, "
        f"{overview.hot_leads} hot leads requiring follow-up."
    )
    sections = [
        AgentReportSection(
            title="Lead activity",
            body=summary,
            confidence=min(50, cap),
        )
    ]
    rec = AgentReportRecommendation(
        observation=summary,
        root_cause=(
            "Lead volume reflects your current marketing reach and landing page performance."
        ),
        recommended_action=(
            "Prioritize hot lead follow-ups before creating new campaigns."
            if overview.hot_leads > 0
            else "Drive traffic to your lead page to start building pipeline."
        ),
        expected_impact="Improve conversion of existing interest into customers.",
        confidence=min(45, cap),
        data_sources_used=data_sources,
    )
    return AgentReport(
        report_type=report_type,
        ready=True,
        summary=summary,
        sections=sections,
        recommendations=[rec],
        confidence=min(45, cap),
        data_sources_used=data_sources,
        period_start=period_start.isoformat(),
        period_end=period_end.isoformat(),
        generated_at=generated_at,
    )
