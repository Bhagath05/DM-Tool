"""Pure-function tests for the diagnostic rules — Phase 9.1.

Covers the Constitution discipline:
  - small-sample gate (rollups with insufficient sample → no draft)
  - winner detection picks the lowest-CPL creative
  - confidence stays under the 90 ceiling for single-upload data
  - confidence below 40 is suppressed (Speculative band)
  - budget_reallocation only fires when there's a meaningful gap
  - revenue vs lead impact category resolution
"""

from __future__ import annotations

import uuid
from datetime import date

from aicmo.modules.performance.diagnostics import diagnose
from aicmo.modules.performance.schemas import CreativeRollup


def _rollup(
    *,
    creative_ref: str,
    impressions: int = 5000,
    clicks: int = 100,
    conversions: int = 10,
    spend_micros: int = 5_000_000_000,  # 5,000 INR default
    conversion_value_micros: int = 0,
    sample_state: str = "sufficient",
    concept_family: str | None = None,
    audience: str | None = None,
    offer_type: str | None = None,
    currency: str = "INR",
) -> CreativeRollup:
    return CreativeRollup(
        creative_ref=creative_ref,
        platform="meta",
        matched_asset_type=None,
        matched_asset_id=None,
        concept_family=concept_family,
        emotion=None,
        audience=audience,
        funnel_stage=None,
        business_goal=None,
        offer_type=offer_type,  # type: ignore[arg-type]
        impressions=impressions,
        clicks=clicks,
        conversions=conversions,
        spend_micros=spend_micros,
        conversion_value_micros=conversion_value_micros,
        currency=currency,
        first_seen=date(2026, 5, 1),
        last_seen=date(2026, 5, 31),
        sample_state=sample_state,  # type: ignore[arg-type]
    )


# ---------------------------------------------------------------------
#  small-sample discipline
# ---------------------------------------------------------------------


def test_diagnose_returns_empty_when_all_rollups_insufficient() -> None:
    rollups = [
        _rollup(creative_ref="A", sample_state="insufficient"),
        _rollup(creative_ref="B", sample_state="insufficient"),
    ]
    assert diagnose(rollups) == []


def test_diagnose_returns_empty_when_no_rollups() -> None:
    assert diagnose([]) == []


def test_diagnose_returns_empty_when_sufficient_but_zero_conversions() -> None:
    # Spend + impressions met but no conversions → can't compute CPL.
    # Phase 9.1 stays quiet here rather than fabricating a story.
    rollups = [
        _rollup(creative_ref="A", conversions=0),
        _rollup(creative_ref="B", conversions=0),
    ]
    assert diagnose(rollups) == []


# ---------------------------------------------------------------------
#  winner detection
# ---------------------------------------------------------------------


def test_diagnose_picks_lowest_cpl_as_winner() -> None:
    rollups = [
        # CPL = 100
        _rollup(creative_ref="loser", conversions=10, spend_micros=1_000_000_000),
        # CPL = 25 — winner
        _rollup(creative_ref="winner", conversions=40, spend_micros=1_000_000_000),
        # CPL = 50
        _rollup(creative_ref="middle", conversions=20, spend_micros=1_000_000_000),
    ]
    drafts = diagnose(rollups)
    winner = next((d for d in drafts if d.kind == "winner"), None)
    assert winner is not None
    assert winner.subject_creative_ref == "winner"
    assert winner.evidence["runner_up_ref"] == "middle"


def test_winner_confidence_caps_at_90() -> None:
    # Massive sample + huge margin should still cap.
    rollups = [
        _rollup(
            creative_ref="winner",
            impressions=100_000,
            clicks=5000,
            conversions=500,
            spend_micros=5_000_000_000,
        ),
        _rollup(
            creative_ref="loser",
            impressions=100_000,
            clicks=500,
            conversions=50,
            spend_micros=5_000_000_000,
        ),
    ]
    drafts = diagnose(rollups)
    winner = next(d for d in drafts if d.kind == "winner")
    assert winner.confidence == 90


def test_winner_impact_category_revenue_when_value_present() -> None:
    rollups = [
        _rollup(
            creative_ref="A",
            conversion_value_micros=10_000_000_000,  # ₹10k
            conversions=10,
            spend_micros=1_000_000_000,
        ),
        _rollup(
            creative_ref="B",
            conversion_value_micros=2_000_000_000,
            conversions=5,
            spend_micros=1_000_000_000,
        ),
    ]
    winner = next(d for d in diagnose(rollups) if d.kind == "winner")
    assert winner.impact_category == "revenue"


def test_winner_impact_category_lead_when_no_value() -> None:
    rollups = [
        _rollup(creative_ref="A", conversions=10, spend_micros=1_000_000_000),
        _rollup(creative_ref="B", conversions=5, spend_micros=1_000_000_000),
    ]
    winner = next(d for d in diagnose(rollups) if d.kind == "winner")
    assert winner.impact_category == "lead"


def test_winner_evidence_surfaces_tags_for_recommender() -> None:
    """The recommender uses concept_family/audience/offer_type to write
    a more specific 'make 2-3 more variants in the same direction'
    sentence. Pin that they flow through."""
    rollups = [
        _rollup(
            creative_ref="A",
            conversions=20,
            spend_micros=1_000_000_000,
            concept_family="family_experience",
            audience="parents_25_45",
            offer_type="consultation",
        ),
        _rollup(creative_ref="B", conversions=5, spend_micros=1_000_000_000),
    ]
    winner = next(d for d in diagnose(rollups) if d.kind == "winner")
    assert winner.evidence["concept_family"] == "family_experience"
    assert winner.evidence["audience"] == "parents_25_45"
    assert winner.evidence["offer_type"] == "consultation"


# ---------------------------------------------------------------------
#  budget reallocation
# ---------------------------------------------------------------------


def test_budget_realloc_only_fires_when_gap_is_material() -> None:
    # CPLs are 50 and 60 — only a 1.2x gap, below the 1.5x threshold.
    rollups = [
        _rollup(creative_ref="A", conversions=20, spend_micros=1_000_000_000),
        _rollup(
            creative_ref="B",
            conversions=20,
            spend_micros=1_200_000_000,
        ),  # CPL=60, A=50 → 1.2x
    ]
    drafts = diagnose(rollups)
    kinds = [d.kind for d in drafts]
    assert "winner" in kinds
    assert "budget_reallocation" not in kinds


def test_budget_realloc_fires_when_gap_exceeds_threshold() -> None:
    # CPLs are 50 (winner) and 200 (underperformer) — 4x gap.
    rollups = [
        _rollup(creative_ref="winner", conversions=20, spend_micros=1_000_000_000),
        _rollup(
            creative_ref="loser",
            conversions=5,
            spend_micros=1_000_000_000,
        ),
    ]
    drafts = diagnose(rollups)
    realloc = next((d for d in drafts if d.kind == "budget_reallocation"), None)
    assert realloc is not None
    assert realloc.evidence["winner_ref"] == "winner"
    assert realloc.evidence["underperformer_ref"] == "loser"
    assert realloc.evidence["cpl_ratio"] >= 1.5


def test_budget_realloc_confidence_one_band_below_winner() -> None:
    rollups = [
        _rollup(creative_ref="winner", conversions=40, spend_micros=1_000_000_000),
        _rollup(creative_ref="loser", conversions=5, spend_micros=1_000_000_000),
    ]
    drafts = diagnose(rollups)
    winner = next(d for d in drafts if d.kind == "winner")
    realloc = next(d for d in drafts if d.kind == "budget_reallocation")
    # Realloc is derived, so it's intentionally less confident than
    # the directly-observed winner.
    assert realloc.confidence == max(40, winner.confidence - 10)
    assert realloc.confidence < winner.confidence


def test_no_realloc_when_only_one_creative_with_sample() -> None:
    rollups = [
        _rollup(creative_ref="A", conversions=20, spend_micros=1_000_000_000),
    ]
    drafts = diagnose(rollups)
    kinds = [d.kind for d in drafts]
    # No runner-up → winner still allowed (with reduced confidence),
    # but realloc has no FROM, so should not fire.
    assert "budget_reallocation" not in kinds
