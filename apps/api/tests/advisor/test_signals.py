"""Unified signal gatherer tests."""

from __future__ import annotations

from aicmo.modules.advisor.signals import has_minimum_evidence
from aicmo.modules.advisor.brain import BusinessBrain


def test_has_minimum_evidence_requires_brain_and_activity():
    brain = BusinessBrain(
        industry="Cafe",
        business_type="Coffee shop",
        target_audience="Urban professionals who want specialty coffee",
    )
    from aicmo.modules.advisor.signals import IntelligenceSignals

    empty = IntelligenceSignals(
        brain=brain,
        brain_complete=True,
        setup_steps=[],
        outcome_context={},
        connector_context={},
        content_intelligence={},
        lead_context={},
        analytics_signals=[],
        has_outcomes=False,
        has_connectors=False,
        has_content_intel=False,
        has_lead_intel=False,
        activity_signals=0,
    )
    assert has_minimum_evidence(empty) is False

    with_leads = empty.__class__(
        **{**empty.__dict__, "has_lead_intel": True, "activity_signals": 1}
    )
    assert has_minimum_evidence(with_leads) is True
