"""Phase 6.5 Slice 6 — Executive CRM Dashboard: reuse wiring, AI evidence-
contract filtering, tenant scoping, CSV export. Hermetic — the heavy SQL
aggregates are validated by the live deploy; here we pin the orchestration,
the insight filtering, and the pure helpers."""

from __future__ import annotations

import asyncio
import uuid
from datetime import UTC, datetime
from types import SimpleNamespace

from aicmo.modules.crm import dashboard_service as svc
from aicmo.modules.crm.dashboard_schemas import (
    ActivityCounts,
    ExecutiveKPIs,
    Forecast,
    PipelineDashboard,
    RepPerformance,
)
from aicmo.modules.crm.models import Deal
from aicmo.modules.crm.schemas import PipelineAnalytics

_BRAND = uuid.uuid4()
_TENANT = SimpleNamespace(
    organization_id=uuid.uuid4(), brand_id=_BRAND, user_id="rep-1", user_uuid=uuid.uuid4()
)


def _pa() -> PipelineAnalytics:
    return PipelineAnalytics(
        pipeline_id=None, open_deals=3, won_deals=2, lost_deals=1, pipeline_value=30000,
        weighted_forecast=12000, won_value=50000, win_rate=0.66, avg_deal_size=25000,
        conversion_rate=0.33, by_stage=[],
    )


def _insight(insufficient: bool):
    return SimpleNamespace(
        id=uuid.uuid4(), subject_type="deal", subject_id=uuid.uuid4(), kind="deal_intelligence",
        summary="s", recommendation="r", evidence=[], reasoning="why", confidence=70,
        affected_records=["deal: X"], expected_outcome="win", insufficient_evidence=insufficient,
        model="m", generated_at=datetime.now(UTC), expires_at=None,
    )


def run(c):
    return asyncio.run(c)


# ---- deal scoping (tenant isolation is always in the filter) ----
def test_deal_conds_always_scopes_brand():
    conds = svc._deal_conds(_TENANT, None, None)
    assert len(conds) == 1  # just the brand filter
    conds2 = svc._deal_conds(_TENANT, uuid.uuid4(), "rep-9")
    assert len(conds2) == 3  # brand + pipeline + owner


# ---- orchestration + AI evidence-contract filtering ----
def test_dashboard_reuses_calculators_and_filters_insights(monkeypatch):
    async def _analytics(_s, *, tenant, pipeline_id=None):
        return _pa()

    async def _email_stats(_s, *, tenant):
        return {"open_rate": 0.4, "reply_rate": 0.1, "click_rate": 0.2, "bounce_rate": 0.0}

    async def _list_insights(_s, *, tenant, limit=8):
        # one insufficient (must be dropped) + 6 good (must cap at 5)
        return [_insight(True)] + [_insight(False) for _ in range(6)]

    monkeypatch.setattr(svc.crm_service, "analytics", _analytics)
    monkeypatch.setattr(svc.email_service, "email_stats", _email_stats)
    monkeypatch.setattr(svc.assistant_service, "list_insights", _list_insights)

    # Stub the SQL-heavy sections (validated live) so this stays hermetic.
    async def _kpis(*a, **k):
        return ExecutiveKPIs(
            total_leads=10, qualified_leads=4, active_opportunities=3, won_deals=2, lost_deals=1,
            revenue=50000, pipeline_value=30000, avg_deal_size=25000, win_rate=0.66,
            conversion_rate=0.33, sales_velocity=100.0, avg_sales_cycle_days=12.0,
            lead_response_time_hours=None, email_open_rate=0.4, email_reply_rate=0.1,
            meetings_completed=5, tasks_completed=8, follow_up_compliance=0.9,
        )

    async def _pipeline(*a, **k):
        return PipelineDashboard(analytics=_pa(), funnel=[], lost_reasons=[], risk_distribution=[], stalled_deals=[])

    async def _reps(*a, **k):
        return [RepPerformance(owner_user_id="rep-1", revenue=50000, won_deals=2, open_deals=3,
                               pipeline_value=30000, win_rate=0.66, activities=9, meetings=3,
                               calls=2, emails=5, tasks_completed=8)]

    async def _activity(*a, **k):
        return ActivityCounts(calls=2, meetings=3, emails=5, notes=1, tasks_open=4,
                              tasks_completed=8, follow_ups_due=1)

    async def _forecast(*a, **k):
        return Forecast(monthly=[], quarterly=[], pipeline_weighted_forecast=12000, open_pipeline_value=30000)

    monkeypatch.setattr(svc, "_kpis", _kpis)
    monkeypatch.setattr(svc, "_pipeline", _pipeline)
    monkeypatch.setattr(svc, "_reps", _reps)
    monkeypatch.setattr(svc, "_activity", _activity)
    monkeypatch.setattr(svc, "_forecast", _forecast)

    dash = run(svc.executive_dashboard(object(), tenant=_TENANT))
    # evidence contract: insufficient dropped, capped at 5, each carries confidence + evidence fields
    assert len(dash.ai_insights) == 5
    assert all(not i.insufficient_evidence for i in dash.ai_insights)
    assert all(i.confidence is not None and i.expected_outcome for i in dash.ai_insights)
    # reused numbers flow through
    assert dash.forecast.pipeline_weighted_forecast == 12000
    assert dash.kpis.revenue == 50000
    assert dash.reps[0].owner_user_id == "rep-1"
    assert dash.generated_at is not None


# ---- CSV export (pure) ----
def test_to_csv_contains_kpis_and_rep_leaderboard():
    dash = SimpleNamespace(
        kpis=ExecutiveKPIs(
            total_leads=10, qualified_leads=4, active_opportunities=3, won_deals=2, lost_deals=1,
            revenue=50000, pipeline_value=30000, avg_deal_size=25000, win_rate=0.66,
            conversion_rate=0.33, sales_velocity=100.0, avg_sales_cycle_days=12.0,
            lead_response_time_hours=None, email_open_rate=0.4, email_reply_rate=0.1,
            meetings_completed=5, tasks_completed=8, follow_up_compliance=0.9,
        ),
        reps=[RepPerformance(owner_user_id="rep-1", revenue=50000, won_deals=2, open_deals=3,
                             pipeline_value=30000, win_rate=0.66, activities=9, meetings=3,
                             calls=2, emails=5, tasks_completed=8)],
    )
    out = svc.to_csv(dash)
    assert "Executive KPIs" in out
    assert "revenue,50000" in out
    assert "rep-1" in out and "Rep,Revenue" in out


def test_deal_model_importable_for_conds():
    # guards against a refactor dropping the Deal import the conds rely on
    assert Deal.__tablename__ == "crm_deals"
