"""Phase 9.1.5 — Scaling Intelligence tests."""

from __future__ import annotations

from aicmo.modules.performance.intelligence.scaling import (
    summarise_budget_waste,
    summarise_scale_candidates,
)

from ._fixtures import rollup


# ---------------------------------------------------------------------
#  Scale candidate
# ---------------------------------------------------------------------


def test_scale_candidate_picks_cheap_creative_with_headroom() -> None:
    rollups = [
        # Cheap winner with low spend → headroom.
        rollup(creative_ref="cheap", conversions=20, spend=500),     # CPL 25
        # Expensive others bring brand avg up to ~150.
        rollup(creative_ref="expA",  conversions=5,  spend=1_500),   # CPL 300
        rollup(creative_ref="expB",  conversions=5,  spend=1_000),   # CPL 200
    ]
    drafts = summarise_scale_candidates(rollups)
    assert len(drafts) == 1
    assert drafts[0].evidence["creative_ref"] == "cheap"
    assert drafts[0].evidence["cpl_advantage_ratio"] > 1.25


def test_scale_candidate_silent_when_winner_already_dominates_spend() -> None:
    # Single creative is >50% of total spend → no headroom signal.
    rollups = [
        rollup(creative_ref="dominant", conversions=50, spend=8_000),  # CPL 160
        rollup(creative_ref="other",    conversions=5,  spend=1_000),  # CPL 200
    ]
    assert summarise_scale_candidates(rollups) == []


def test_scale_candidate_silent_when_no_creative_beats_brand_avg() -> None:
    # All within 5% of each other.
    rollups = [
        rollup(creative_ref="A", conversions=10, spend=1_000),  # CPL 100
        rollup(creative_ref="B", conversions=10, spend=1_050),  # CPL 105
        rollup(creative_ref="C", conversions=10, spend=1_100),  # CPL 110
    ]
    assert summarise_scale_candidates(rollups) == []


def test_scale_candidate_confidence_capped_at_80() -> None:
    rollups = [
        # Massive sample on the cheap one.
        rollup(creative_ref="cheap", conversions=500, spend=1_000),
        rollup(creative_ref="expA",  conversions=5,   spend=1_500),
        rollup(creative_ref="expB",  conversions=5,   spend=1_000),
    ]
    drafts = summarise_scale_candidates(rollups)
    assert drafts[0].confidence == 80


# ---------------------------------------------------------------------
#  Budget waste
# ---------------------------------------------------------------------


def test_budget_waste_picks_high_cpl_high_spend_creative() -> None:
    rollups = [
        rollup(creative_ref="winner", conversions=20, spend=1_000),   # CPL 50
        rollup(creative_ref="bleeder", conversions=5,  spend=2_500),  # CPL 500
    ]
    drafts = summarise_budget_waste(rollups)
    assert len(drafts) == 1
    assert drafts[0].evidence["creative_ref"] == "bleeder"
    assert drafts[0].evidence["cpl_overrun_ratio"] > 1.5


def test_budget_waste_silent_when_high_cpl_but_low_spend() -> None:
    # High CPL but the wasted spend is < 10% of total — not a waste card.
    rollups = [
        rollup(creative_ref="winner", conversions=200, spend=10_000),  # CPL 50, 95%+ of total
        rollup(creative_ref="tiny",   conversions=1,   spend=300),     # CPL 300, ~3% of total
    ]
    assert summarise_budget_waste(rollups) == []


def test_budget_waste_estimates_freed_leads_honestly() -> None:
    rollups = [
        rollup(creative_ref="winner",  conversions=20, spend=1_000),   # CPL 50
        rollup(creative_ref="bleeder", conversions=5,  spend=2_500),   # CPL 500
    ]
    drafts = summarise_budget_waste(rollups)
    # Brand avg CPL ≈ 140; at 140 the bleeder's 2500 ≈ 17 leads,
    # net of the 5 already counted = ~12 freed leads.
    freed = drafts[0].evidence["freed_leads_estimate"]
    assert 5 <= freed <= 20
