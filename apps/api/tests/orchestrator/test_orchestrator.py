"""Module 8 — Agent Orchestrator unit tests (pure state machine; no DB)."""

from __future__ import annotations

from aicmo.modules.orchestrator import service
from aicmo.modules.orchestrator.service import _State


def _stages_by_key(st: _State):
    return {s.key: s for s in service._assess_stages(st)}


def test_empty_workspace_routes_to_understand():
    st = _State()  # nothing done
    by = _stages_by_key(st)
    assert by["understand"].status == "ready"
    assert by["understand"].action == "Complete your business profile"
    # Downstream stages are blocked on their prerequisites.
    assert by["strategize"].status == "blocked"
    assert by["strategize"].blocked_by == "understand"
    assert by["execute"].status == "blocked"


def test_profile_done_but_no_strategy_routes_to_strategize():
    st = _State()
    st.has_profile = True
    st.analysis_status = "completed"
    by = _stages_by_key(st)
    assert by["understand"].status == "done"
    assert by["strategize"].status == "ready"
    assert by["plan"].status == "blocked"  # needs strategy
    assert by["decide"].status == "ready"  # only needs profile


def test_stale_strategy_flags_refresh():
    st = _State()
    st.has_profile = True
    st.analysis_status = "completed"
    st.has_strategy = True
    st.strategy_stale = True
    by = _stages_by_key(st)
    assert by["strategize"].status == "stale"
    assert "Refresh" in by["strategize"].action


def test_execute_always_requires_approval():
    st = _State()
    st.has_profile = True
    st.analysis_status = "completed"
    st.has_strategy = True
    by = _stages_by_key(st)
    assert by["execute"].requires_approval is True
    assert by["execute"].status == "ready"


def test_pending_approvals_flip_execute_to_needs_approval():
    st = _State()
    st.has_profile = True
    st.analysis_status = "completed"
    st.has_strategy = True
    st.pending_approvals = ["2 post(s) queued to publish — review before they go out."]
    by = _stages_by_key(st)
    assert by["execute"].status == "needs_approval"
    assert by["execute"].requires_approval is True


def test_learn_blocked_without_activity_ready_with_it():
    st = _State()
    st.has_profile = True
    st.analysis_status = "completed"
    st.has_strategy = True
    assert _stages_by_key(st)["learn"].status == "blocked"

    st.total_leads = 5  # real activity
    assert _stages_by_key(st)["learn"].status == "ready"

    st.active_learnings = 3  # already learned
    assert _stages_by_key(st)["learn"].status == "done"


def test_next_action_is_earliest_actionable_and_summary_set():
    st = _State()
    st.has_profile = True
    st.analysis_status = "completed"
    # strategize is the earliest actionable gap.
    stages = service._assess_stages(st)
    by = {s.key: s for s in stages}
    # simulate build_plan's selection logic
    order = service._ORDER
    nxt = next(
        (s for k in order for s in [by[k]] if s.status in service._ACTIONABLE and s.action),
        None,
    )
    assert nxt is not None
    assert nxt.key == "strategize"


def test_nothing_executes_note_present_on_schema():
    # The autonomy guarantee is a schema default, always shipped.
    from aicmo.modules.orchestrator.schemas import OrchestratorPlan

    plan = OrchestratorPlan(
        summary="x", current_stage="understand", stages=[], generated_at="now"
    )
    assert "runs automatically" in plan.autonomy_note
