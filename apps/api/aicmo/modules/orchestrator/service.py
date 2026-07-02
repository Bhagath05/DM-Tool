"""Module 8 — Agent Orchestrator: assess lifecycle state, route the next action.

Deterministic. Reads each module's state (guarded), never generates or executes.
"""

from __future__ import annotations

from datetime import UTC, datetime, timedelta

import structlog
from sqlalchemy.ext.asyncio import AsyncSession

from aicmo.modules.orchestrator.schemas import (
    LifecycleStage,
    NextAction,
    OrchestratorPlan,
)
from aicmo.tenancy.context import TenantContext

log = structlog.get_logger()

# A strategy older than this is treated as stale (worth refreshing).
_STRATEGY_STALE_DAYS = 45
# Lifecycle order — the AI employee's workflow.
_ORDER = ("understand", "strategize", "plan", "decide", "execute", "learn", "review")
_ACTIONABLE = ("ready", "stale", "needs_approval")


class _State:
    """Cheap, guarded snapshot of each module's state."""

    has_profile = False
    analysis_status: str | None = None
    has_strategy = False
    strategy_stale = False
    active_learnings = 0
    total_leads = 0
    total_views = 0
    published_count = 0
    pending_approvals: list[str]

    def __init__(self) -> None:
        self.pending_approvals = []

    @property
    def has_activity(self) -> bool:
        return bool(self.total_leads or self.total_views or self.published_count)


async def _gather_state(session: AsyncSession, *, tenant: TenantContext) -> _State:
    st = _State()
    brand_id = tenant.brand_id

    try:
        from aicmo.modules.onboarding import service as onboarding_service

        row = await onboarding_service.get_profile_or_none(session, brand_id)
        if row is not None:
            st.has_profile = True
            st.analysis_status = getattr(row, "analysis_status", None)
    except Exception as e:
        log.warning("orchestrator.profile_failed", error=str(e)[:120])

    try:
        from aicmo.modules.strategist import service as strategist_service

        rec = await strategist_service.latest(session, brand_id=brand_id)
        if rec is not None and rec.status == "completed" and rec.strategy:
            st.has_strategy = True
            created = getattr(rec, "created_at", None)
            if created is not None:
                age = datetime.now(UTC) - created
                st.strategy_stale = age > timedelta(days=_STRATEGY_STALE_DAYS)
    except Exception as e:
        log.warning("orchestrator.strategy_failed", error=str(e)[:120])

    try:
        from aicmo.modules.learning import insights_service

        rows = await insights_service.list_insights(
            session, brand_id=brand_id, only_active=True, limit=50
        )
        st.active_learnings = len(rows)
    except Exception as e:
        log.warning("orchestrator.learnings_failed", error=str(e)[:120])

    try:
        from aicmo.modules.analytics import service as analytics_service

        kpis = await analytics_service.overview(session, brand_id=brand_id)
        st.total_leads = kpis.total_leads
        st.total_views = kpis.total_views
    except Exception as e:
        log.warning("orchestrator.analytics_failed", error=str(e)[:120])

    try:
        from aicmo.modules.publishing import service as publishing_service

        sched = await publishing_service.list_scheduled(
            session, brand_id=brand_id, limit=100
        )
        queued = 0
        for item in sched.items:
            if item.publish_status == "published":
                st.published_count += 1
            elif item.publish_status not in ("failed",):
                queued += 1
        if queued:
            st.pending_approvals.append(
                f"{queued} post(s) queued to publish — review before they go out."
            )
    except Exception as e:
        log.warning("orchestrator.publishing_failed", error=str(e)[:120])

    return st


def _assess_stages(st: _State) -> list[LifecycleStage]:
    stages: list[LifecycleStage] = []

    # 1) understand
    if not st.has_profile:
        stages.append(LifecycleStage(
            key="understand", label="Understand the business", status="ready",
            reason="No business profile yet — this is where everything starts.",
            action="Complete your business profile", link="/onboarding",
        ))
    elif st.analysis_status == "failed":
        stages.append(LifecycleStage(
            key="understand", label="Understand the business", status="ready",
            reason="The business analysis didn't finish.",
            action="Re-run your business analysis", link="/onboarding",
        ))
    elif st.analysis_status == "pending":
        stages.append(LifecycleStage(
            key="understand", label="Understand the business", status="done",
            reason="Profile saved; AI analysis is still running.", link="/onboarding",
        ))
    else:
        stages.append(LifecycleStage(
            key="understand", label="Understand the business", status="done",
            reason="Business profile and AI analysis are complete.", link="/onboarding",
        ))

    # 2) strategize
    if not st.has_profile:
        stages.append(LifecycleStage(
            key="strategize", label="Build the strategy", status="blocked",
            reason="Needs your business profile first.", link="/strategy",
            blocked_by="understand",
        ))
    elif not st.has_strategy:
        stages.append(LifecycleStage(
            key="strategize", label="Build the strategy", status="ready",
            reason="No marketing strategy yet.",
            action="Generate your marketing strategy", link="/strategy",
        ))
    elif st.strategy_stale:
        stages.append(LifecycleStage(
            key="strategize", label="Build the strategy", status="stale",
            reason=f"Your strategy is over {_STRATEGY_STALE_DAYS} days old.",
            action="Refresh your marketing strategy", link="/strategy",
        ))
    else:
        stages.append(LifecycleStage(
            key="strategize", label="Build the strategy", status="done",
            reason="A current marketing strategy is in place.", link="/strategy",
        ))

    # 3) plan (daily, on-demand)
    if not st.has_strategy:
        stages.append(LifecycleStage(
            key="plan", label="Plan today's tasks", status="blocked",
            reason="Needs a marketing strategy to plan from.", link="/planner",
            blocked_by="strategize",
        ))
    else:
        stages.append(LifecycleStage(
            key="plan", label="Plan today's tasks", status="ready",
            reason="Turn the strategy into today's concrete to-dos.",
            action="Generate today's task plan", link="/planner",
        ))

    # 4) decide (on-demand)
    if not st.has_profile:
        stages.append(LifecycleStage(
            key="decide", label="Decide next moves", status="blocked",
            reason="Needs a business profile to reason over.", link="/decisions",
            blocked_by="understand",
        ))
    else:
        stages.append(LifecycleStage(
            key="decide", label="Decide next moves", status="ready",
            reason="Get evidence-grounded decisions from your real data.",
            action="Generate fresh strategic decisions", link="/decisions",
        ))

    # 5) execute (ALWAYS human-approved)
    if not st.has_strategy:
        stages.append(LifecycleStage(
            key="execute", label="Execute campaigns", status="blocked",
            reason="Create a strategy before running campaigns.", link="/campaigns",
            blocked_by="strategize", requires_approval=True,
        ))
    elif st.pending_approvals:
        stages.append(LifecycleStage(
            key="execute", label="Execute campaigns", status="needs_approval",
            reason="You have work queued that needs your review.",
            action="Review the items awaiting your approval", link="/social",
            requires_approval=True,
        ))
    else:
        stages.append(LifecycleStage(
            key="execute", label="Execute campaigns", status="ready",
            reason="Draft a campaign — nothing publishes until you approve it.",
            action="Create a campaign draft (you approve before it publishes)",
            link="/campaigns", requires_approval=True,
        ))

    # 6) learn
    if not st.has_activity:
        stages.append(LifecycleStage(
            key="learn", label="Learn from results", status="blocked",
            reason="Needs real results (published posts or leads) to learn from.",
            link="/learning", blocked_by="execute",
        ))
    elif st.active_learnings > 0:
        stages.append(LifecycleStage(
            key="learn", label="Learn from results", status="done",
            reason=f"{st.active_learnings} active lesson(s) learned from your results.",
            action="Refresh lessons from the latest results", link="/learning",
        ))
    else:
        stages.append(LifecycleStage(
            key="learn", label="Learn from results", status="ready",
            reason="You have real results — distil lessons from them.",
            action="Run the Learning Engine", link="/learning",
        ))

    # 7) review
    has_any = st.has_profile or st.has_strategy or st.has_activity or st.active_learnings
    if not has_any:
        stages.append(LifecycleStage(
            key="review", label="Review the insights feed", status="blocked",
            reason="Nothing to surface yet.", link="/insights", blocked_by="understand",
        ))
    else:
        stages.append(LifecycleStage(
            key="review", label="Review the insights feed", status="ready",
            reason="See every insight — decisions, opportunities, lessons — in one feed.",
            action="Open your unified Insights Feed", link="/insights",
        ))

    return stages


async def build_plan(
    session: AsyncSession, *, tenant: TenantContext
) -> OrchestratorPlan:
    st = await _gather_state(session, tenant=tenant)
    stages = _assess_stages(st)
    by_key = {s.key: s for s in stages}

    # current stage = earliest not-done; next action = earliest actionable step.
    current = "review"
    for key in _ORDER:
        if by_key[key].status != "done":
            current = key
            break

    next_action: NextAction | None = None
    for key in _ORDER:
        s = by_key[key]
        if s.status in _ACTIONABLE and s.action:
            next_action = NextAction(
                stage=s.key, action=s.action, why=s.reason, link=s.link,
                requires_approval=s.requires_approval,
            )
            break

    blocked_on = next(
        (s.blocked_by for s in stages if s.status == "blocked" and s.blocked_by), None
    )

    if next_action is not None:
        summary = f"Next: {next_action.action.rstrip('.')} — {next_action.why}"
    else:
        summary = "Everything's current — keep an eye on your insights feed."

    return OrchestratorPlan(
        summary=summary,
        current_stage=current,  # type: ignore[arg-type]
        next_action=next_action,
        stages=stages,
        blocked_on=blocked_on,
        pending_approvals=st.pending_approvals,
        generated_at=datetime.now(UTC).isoformat(),
    )
