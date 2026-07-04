"""Executive CRM Dashboard service (Phase 6.5, Slice 6).

A read-only aggregation layer. Pipeline KPIs come from the EXISTING
crm.service.analytics (no duplicated math); email rates from
email_service.email_stats; AI insights from assistant_service.list_insights.
Only the genuinely-missing executive aggregations (velocity, cycle, per-rep,
stalled, risk, forecast-by-period, activity counts) are computed here — each a
grounded query over real rows, returning null where the data doesn't exist.
"""

from __future__ import annotations

import csv
import io
from datetime import UTC, datetime, timedelta

from sqlalchemy import case, func, select
from sqlalchemy.ext.asyncio import AsyncSession

from aicmo.modules.crm import assistant_service, email_service
from aicmo.modules.crm import service as crm_service
from aicmo.modules.crm.assistant_schemas import InsightResponse
from aicmo.modules.crm.dashboard_schemas import (
    ActivityCounts,
    ExecutiveDashboard,
    ExecutiveKPIs,
    Forecast,
    ForecastPeriod,
    LostReason,
    PipelineDashboard,
    RepPerformance,
    RiskBand,
    StageFunnel,
    StalledDeal,
)
from aicmo.modules.crm.email_models import Email
from aicmo.modules.crm.models import Activity, Deal, Task
from aicmo.modules.leads.models import Lead
from aicmo.tenancy.context import TenantContext

_QUALIFIED_LEAD_STATUSES = ("hot", "warm")  # this taxonomy has no "qualified" status
_STALLED_DAYS = 14


async def _scalar(session, stmt, default=0):
    return (await session.execute(stmt)).scalar_one() or default


def _deal_conds(tenant, pipeline_id, owner_user_id):
    conds = [Deal.brand_id == tenant.brand_id]
    if pipeline_id is not None:
        conds.append(Deal.pipeline_id == pipeline_id)
    if owner_user_id is not None:
        conds.append(Deal.owner_user_id == owner_user_id)
    return conds


async def _kpis(session, *, tenant, pa, es, deal_conds) -> ExecutiveKPIs:
    total_leads = await _scalar(session, select(func.count()).select_from(Lead).where(Lead.brand_id == tenant.brand_id))
    qualified = await _scalar(session, select(func.count()).select_from(Lead).where(
        Lead.brand_id == tenant.brand_id, Lead.status.in_(_QUALIFIED_LEAD_STATUSES)))

    # Average sales cycle (won deals) — seconds → days. Null when no won deals.
    cycle_seconds = await _scalar(session, select(
        func.avg(func.extract("epoch", Deal.won_at - Deal.created_at))
    ).where(*deal_conds, Deal.status == "won", Deal.won_at.isnot(None)), default=None)
    cycle_days = round(cycle_seconds / 86400, 1) if cycle_seconds else None

    velocity = 0.0
    if cycle_days:
        velocity = round((pa.open_deals * pa.avg_deal_size * pa.win_rate) / max(cycle_days, 1), 2)

    meetings_completed = await _scalar(session, select(func.count()).select_from(Task).where(
        Task.brand_id == tenant.brand_id, Task.activity_type.in_(("meeting", "demo")), Task.status == "completed"))
    tasks_completed = await _scalar(session, select(func.count()).select_from(Task).where(
        Task.brand_id == tenant.brand_id, Task.status == "completed"))

    # Follow-up compliance — completed on/before due date. Null when nothing due.
    due_completed = await _scalar(session, select(func.count()).select_from(Task).where(
        Task.brand_id == tenant.brand_id, Task.status == "completed", Task.due_at.isnot(None)))
    on_time = await _scalar(session, select(func.count()).select_from(Task).where(
        Task.brand_id == tenant.brand_id, Task.status == "completed", Task.due_at.isnot(None),
        Task.completed_at <= Task.due_at))
    compliance = round(on_time / due_completed, 4) if due_completed else None

    return ExecutiveKPIs(
        total_leads=int(total_leads), qualified_leads=int(qualified),
        active_opportunities=pa.open_deals, won_deals=pa.won_deals, lost_deals=pa.lost_deals,
        revenue=pa.won_value, pipeline_value=pa.pipeline_value, avg_deal_size=pa.avg_deal_size,
        win_rate=pa.win_rate, conversion_rate=pa.conversion_rate, sales_velocity=velocity,
        avg_sales_cycle_days=cycle_days,
        lead_response_time_hours=None,  # no lead↔activity link exists — reported honestly as null
        email_open_rate=es["open_rate"], email_reply_rate=es["reply_rate"],
        meetings_completed=int(meetings_completed), tasks_completed=int(tasks_completed),
        follow_up_compliance=compliance,
    )


async def _pipeline(session, *, tenant, pa, deal_conds) -> PipelineDashboard:
    now = datetime.now(UTC)
    # avg days in CURRENT stage (open deals) per stage — grounded proxy.
    stage_age_rows = (await session.execute(
        select(Deal.stage_id, func.avg(func.extract("epoch", now - Deal.updated_at)))
        .where(*deal_conds, Deal.status == "open").group_by(Deal.stage_id)
    )).all()
    age_by_stage = {sid: (secs / 86400 if secs else None) for sid, secs in stage_age_rows}
    funnel = [
        StageFunnel(stage_id=b.stage_id, stage_name=b.stage_name, count=b.count, value=b.value,
                    avg_days_in_stage=round(age_by_stage[b.stage_id], 1) if age_by_stage.get(b.stage_id) else None)
        for b in pa.by_stage
    ]

    lost_rows = (await session.execute(
        select(Deal.lost_reason, func.count()).where(*deal_conds, Deal.status == "lost", Deal.lost_reason.isnot(None))
        .group_by(Deal.lost_reason).order_by(func.count().desc()).limit(10)
    )).all()
    lost_reasons = [LostReason(reason=r or "Unspecified", count=int(c)) for r, c in lost_rows]

    async def _band(lo, hi):
        cnt, val = (await session.execute(
            select(func.count(), func.coalesce(func.sum(Deal.value), 0)).where(
                *deal_conds, Deal.status == "open",
                func.coalesce(Deal.probability, 0) >= lo, func.coalesce(Deal.probability, 0) < hi)
        )).one()
        return int(cnt), float(val)
    risk = []
    for band, lo, hi in (("high", 70, 101), ("medium", 40, 70), ("low", 0, 40)):
        c, v = await _band(lo, hi)
        risk.append(RiskBand(band=band, count=c, value=v))

    stalled_cutoff = now - timedelta(days=_STALLED_DAYS)
    stalled_rows = (await session.execute(
        select(Deal).where(*deal_conds, Deal.status == "open", Deal.updated_at < stalled_cutoff)
        .order_by(Deal.value.desc()).limit(10)
    )).scalars().all()
    stalled = [
        StalledDeal(id=d.id, title=d.title, value=float(d.value),
                    days_inactive=(now - d.updated_at).days if d.updated_at else 0,
                    owner_user_id=d.owner_user_id)
        for d in stalled_rows
    ]
    return PipelineDashboard(analytics=pa, funnel=funnel, lost_reasons=lost_reasons,
                             risk_distribution=risk, stalled_deals=stalled)


async def _reps(session, *, tenant, deal_conds) -> list[RepPerformance]:
    # Money metrics per owner — one grouped query. Postgres can't cast bool→float,
    # so use CASE to sum conditionally.
    def _when(status, expr):
        return func.coalesce(func.sum(case((Deal.status == status, expr), else_=0)), 0)

    deal_rows = (await session.execute(
        select(
            Deal.owner_user_id,
            _when("won", Deal.value), _when("won", 1), _when("open", 1),
            _when("open", Deal.value), _when("lost", 1),
        ).where(*deal_conds, Deal.owner_user_id.isnot(None)).group_by(Deal.owner_user_id)
    )).all()

    async def _grouped_count(col, model, *extra):
        return dict((await session.execute(
            select(col, func.count()).where(model.brand_id == tenant.brand_id, col.isnot(None), *extra).group_by(col)
        )).all())

    acts = await _grouped_count(Activity.actor_user_id, Activity)
    meetings = await _grouped_count(Task.assignee_user_id, Task, Task.activity_type.in_(("meeting", "demo")))
    calls = await _grouped_count(Task.assignee_user_id, Task, Task.activity_type == "call")
    tasks_done = await _grouped_count(Task.assignee_user_id, Task, Task.status == "completed")
    emails = await _grouped_count(Email.sent_by_user_id, Email)

    reps = []
    for owner, won_val, won_n, open_n, open_val, lost_n in deal_rows:
        won_n, lost_n = int(won_n or 0), int(lost_n or 0)
        reps.append(RepPerformance(
            owner_user_id=owner, revenue=round(float(won_val or 0), 2), won_deals=won_n,
            open_deals=int(open_n or 0), pipeline_value=round(float(open_val or 0), 2),
            win_rate=round(won_n / (won_n + lost_n), 4) if (won_n + lost_n) else 0.0,
            activities=int(acts.get(owner, 0)), meetings=int(meetings.get(owner, 0)),
            calls=int(calls.get(owner, 0)), emails=int(emails.get(owner, 0)),
            tasks_completed=int(tasks_done.get(owner, 0)),
        ))
    reps.sort(key=lambda r: r.revenue, reverse=True)
    return reps


async def _activity(session, *, tenant) -> ActivityCounts:
    brand = tenant.brand_id

    async def _kind(k):
        return await _scalar(session, select(func.count()).select_from(Activity).where(
            Activity.brand_id == brand, Activity.kind == k))
    tasks_open = await _scalar(session, select(func.count()).select_from(Task).where(
        Task.brand_id == brand, Task.status.notin_(("completed", "cancelled"))))
    tasks_completed = await _scalar(session, select(func.count()).select_from(Task).where(
        Task.brand_id == brand, Task.status == "completed"))
    follow_due = await _scalar(session, select(func.count()).select_from(Task).where(
        Task.brand_id == brand, Task.activity_type == "follow_up",
        Task.status.notin_(("completed", "cancelled")), Task.due_at.isnot(None),
        Task.due_at <= datetime.now(UTC)))
    return ActivityCounts(
        calls=int(await _kind("call")), meetings=int(await _kind("meeting")),
        emails=int(await _kind("email")), notes=int(await _kind("note")),
        tasks_open=int(tasks_open), tasks_completed=int(tasks_completed), follow_ups_due=int(follow_due),
    )


async def _forecast(session, *, tenant, pa, deal_conds) -> Forecast:
    async def _by(trunc):
        rows = (await session.execute(
            select(func.to_char(func.date_trunc(trunc, Deal.won_at),
                                "YYYY-MM" if trunc == "month" else "YYYY-\"Q\"Q"),
                   func.coalesce(func.sum(Deal.value), 0), func.count())
            .where(*deal_conds, Deal.status == "won", Deal.won_at.isnot(None))
            .group_by(func.date_trunc(trunc, Deal.won_at))
            .order_by(func.date_trunc(trunc, Deal.won_at).desc()).limit(6)
        )).all()
        return [ForecastPeriod(period=p, won_revenue=round(float(v), 2), deals=int(c)) for p, v, c in rows]

    return Forecast(monthly=await _by("month"), quarterly=await _by("quarter"),
                    pipeline_weighted_forecast=pa.weighted_forecast, open_pipeline_value=pa.pipeline_value)


async def executive_dashboard(
    session: AsyncSession, *, tenant: TenantContext,
    pipeline_id=None, owner_user_id: str | None = None,
) -> ExecutiveDashboard:
    # REUSE the canonical calculators — no duplicated math.
    pa = await crm_service.analytics(session, tenant=tenant, pipeline_id=pipeline_id)
    es = await email_service.email_stats(session, tenant=tenant)
    insight_rows = await assistant_service.list_insights(session, tenant=tenant, limit=8)
    ai_insights = [InsightResponse.model_validate(i) for i in insight_rows if not i.insufficient_evidence][:5]

    deal_conds = _deal_conds(tenant, pipeline_id, owner_user_id)
    return ExecutiveDashboard(
        kpis=await _kpis(session, tenant=tenant, pa=pa, es=es, deal_conds=deal_conds),
        pipeline=await _pipeline(session, tenant=tenant, pa=pa, deal_conds=deal_conds),
        reps=await _reps(session, tenant=tenant, deal_conds=deal_conds),
        activity=await _activity(session, tenant=tenant),
        forecast=await _forecast(session, tenant=tenant, pa=pa, deal_conds=deal_conds),
        ai_insights=ai_insights,
        generated_at=datetime.now(UTC),
        filters={"pipeline_id": str(pipeline_id) if pipeline_id else None, "owner_user_id": owner_user_id},
    )


def to_csv(dash: ExecutiveDashboard) -> str:
    """Executive summary CSV (KPIs + per-rep leaderboard)."""
    buf = io.StringIO()
    w = csv.writer(buf)
    w.writerow(["Executive KPIs"])
    for k, v in dash.kpis.model_dump().items():
        w.writerow([k, v])
    w.writerow([])
    w.writerow(["Rep", "Revenue", "Won", "Open", "Pipeline", "Win rate", "Meetings", "Calls", "Emails", "Tasks done"])
    for r in dash.reps:
        w.writerow([r.owner_user_id, r.revenue, r.won_deals, r.open_deals, r.pipeline_value,
                    r.win_rate, r.meetings, r.calls, r.emails, r.tasks_completed])
    return buf.getvalue()
