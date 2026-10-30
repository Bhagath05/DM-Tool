"""Phase 7.16 — the Opportunity engine prompt is grounded in belief memory.

Unit: build_opportunity_user_prompt injects the learned-beliefs block, and frames
picks as hypotheses (INSUFFICIENT_EVIDENCE) when the brand has no beliefs.
"""

from __future__ import annotations

from types import SimpleNamespace

from aicmo.modules.opportunities.prompts import build_opportunity_user_prompt


def _profile():
    return SimpleNamespace(
        business_name="Brew & Bloom", industry="Cafe", business_location="Hyderabad",
        primary_goal_text="More leads", current_monthly_leads_band="10-50",
        monthly_budget_band="low", preferred_platforms=["instagram"],
        target_audience="Remote workers who want specialty coffee",
    )


def _kwargs(belief_block=None):
    return dict(
        profile=_profile(), counts_block="(none)", top_source_summary=None,
        top_asset_summary=None, trends_summary=None, recent_content_summary=None,
        recent_ads_summary=None, signals=[], memory_block=None, belief_block=belief_block,
    )


def test_opportunity_prompt_injects_learned_beliefs():
    prompt = build_opportunity_user_prompt(
        **_kwargs(belief_block="- [channel] Reels beat static for leads (82%)")
    )
    assert "LEARNED" in prompt
    assert "Reels beat static for leads" in prompt


def test_opportunity_prompt_states_insufficient_evidence_when_no_beliefs():
    prompt = build_opportunity_user_prompt(**_kwargs(belief_block=None))
    assert "INSUFFICIENT_EVIDENCE" in prompt
