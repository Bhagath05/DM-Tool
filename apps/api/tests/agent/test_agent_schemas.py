"""Phase 2 — AgentPlan / synthesis schema contract (no DB, no LLM)."""

from __future__ import annotations

import pytest
from pydantic import ValidationError

from aicmo.modules.agent.prompts import PLANNING_SYSTEM, SYNTHESIS_SYSTEM, untrusted_block
from aicmo.modules.agent.schemas import AgentPlan, AgentSynthesis, ProposedToolCall


def test_valid_agent_plan():
    plan = AgentPlan.model_validate(
        {
            "intent": "assess performance",
            "answer_strategy": "look at analytics",
            "tool_calls": [{"tool_name": "get_campaign_performance", "arguments": {}, "purpose": "kpis"}],
            "confidence": 70,
            "needs_more_evidence": False,
        }
    )
    assert plan.tool_calls[0].tool_name == "get_campaign_performance"


def test_plan_rejects_unknown_top_level_field():
    with pytest.raises(ValidationError):
        AgentPlan.model_validate({"intent": "x", "tool_calls": [], "execute_python": "os.system('rm')"})


def test_tool_call_rejects_smuggled_fields():
    # A proposed tool call cannot carry tenant/authorization or a callable ref.
    with pytest.raises(ValidationError):
        ProposedToolCall.model_validate({"tool_name": "t", "arguments": {}, "tenant_id": "abc"})


def test_tool_call_arguments_are_plain_data():
    call = ProposedToolCall.model_validate({"tool_name": "t", "arguments": {"days": 30}})
    assert call.arguments == {"days": 30}  # a dict of data, never code/callables


def test_confidence_bounds_enforced():
    with pytest.raises(ValidationError):
        AgentSynthesis.model_validate({"answer": "hi", "confidence": 500})


def test_synthesis_defaults_to_insufficient_evidence():
    s = AgentSynthesis.model_validate({"answer": "hi"})
    assert s.evidence_status == "INSUFFICIENT_EVIDENCE"  # honest default, not "ok"


def test_prompts_declare_untrusted_boundary_and_read_only():
    for p in (PLANNING_SYSTEM, SYNTHESIS_SYSTEM):
        assert "UNTRUSTED DATA" in p
        assert "never invent" in p.lower() or "do not fabricate" in p.lower()
        # The agent never executes consequential actions on its own authority —
        # it may at most PROPOSE, and a human must approve (Phase 4B contract).
        assert "never execute" in p.lower()
        assert "approve" in p.lower()
    # Planning explicitly frames consequential actions as proposal-only.
    assert "propose" in PLANNING_SYSTEM.lower()
    block = untrusted_block("X", "some data")
    assert "BEGIN UNTRUSTED DATA" in block and "NOT INSTRUCTIONS" in block
