"""Intelligence adapter unit tests."""

from __future__ import annotations

from aicmo.modules.advisor.schemas import DataSourceRef, IntelligenceRecommendation


def test_intelligence_recommendation_requires_six_fields():
    rec = IntelligenceRecommendation(
        observation="Lead volume dropped this week.",
        root_cause="No new content was published in 14 days.",
        recommended_action="Publish one Instagram post addressing your top customer question.",
        expected_impact="Re-engage your audience and restart inbound conversations.",
        confidence=55,
        data_sources_used=[
            DataSourceRef(key="leads_7d", label="Leads (7 days)", value="2")
        ],
    )
    assert rec.observation
    assert rec.root_cause
    assert len(rec.data_sources_used) >= 1
