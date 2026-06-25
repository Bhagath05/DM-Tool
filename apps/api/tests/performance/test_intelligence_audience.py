"""Phase 9.1.5 — Audience Intelligence tests.

Pin the small-sample gates, winner/loser dual-fire behaviour, and
NULL-tag exclusion so future refactors of the grouping helper don't
silently regress.
"""

from __future__ import annotations

from aicmo.modules.performance.intelligence.audience import summarise_audiences

from ._fixtures import rollup


def test_no_audiences_when_only_one_audience_present() -> None:
    rollups = [
        rollup(creative_ref="A1", audience="parents", conversions=20),
        rollup(creative_ref="A2", audience="parents", conversions=15),
    ]
    assert summarise_audiences(rollups) == []


def test_no_audiences_when_all_tags_null() -> None:
    rollups = [
        rollup(creative_ref="A1", audience=None, conversions=20),
        rollup(creative_ref="A2", audience=None, conversions=18),
    ]
    assert summarise_audiences(rollups) == []


def test_fires_winner_when_two_audiences_compared() -> None:
    rollups = [
        # CPL = 50 -> winner
        rollup(creative_ref="A1", audience="parents",   conversions=20, spend=1_000),
        # CPL = 200 -> loser (4x ratio)
        rollup(creative_ref="A2", audience="executives", conversions=10, spend=2_000),
    ]
    drafts = summarise_audiences(rollups)
    kinds = [d.kind for d in drafts]
    assert "audience_winner" in kinds
    winner = next(d for d in drafts if d.kind == "audience_winner")
    assert winner.evidence["audience"] == "parents"
    assert winner.evidence["runner_up_audience"] == "executives"
    assert winner.confidence >= 60


def test_loser_only_fires_when_gap_is_material_and_spend_nontrivial() -> None:
    # Gap = 1.1x — below the 1.5x threshold. No loser card.
    rollups = [
        rollup(creative_ref="A1", audience="parents",   conversions=20, spend=1_000),  # CPL 50
        rollup(creative_ref="A2", audience="executives", conversions=20, spend=1_100),  # CPL 55
    ]
    drafts = summarise_audiences(rollups)
    kinds = [d.kind for d in drafts]
    assert "audience_winner" in kinds
    assert "audience_loser" not in kinds


def test_loser_fires_when_gap_exceeds_threshold() -> None:
    rollups = [
        rollup(creative_ref="A1", audience="parents",   conversions=20, spend=1_000),  # CPL 50
        rollup(creative_ref="A2", audience="executives", conversions=5,  spend=2_500),  # CPL 500 (10x)
    ]
    drafts = summarise_audiences(rollups)
    kinds = [d.kind for d in drafts]
    assert {"audience_winner", "audience_loser"}.issubset(set(kinds))
    loser = next(d for d in drafts if d.kind == "audience_loser")
    assert loser.confidence < next(d.confidence for d in drafts if d.kind == "audience_winner")


def test_loser_confidence_caps_below_winner() -> None:
    rollups = [
        rollup(creative_ref="A1", audience="parents",   conversions=50, spend=1_000),  # CPL 20
        rollup(creative_ref="A2", audience="executives", conversions=5,  spend=2_500),  # CPL 500
    ]
    drafts = summarise_audiences(rollups)
    winner_conf = next(d.confidence for d in drafts if d.kind == "audience_winner")
    loser_conf = next(d.confidence for d in drafts if d.kind == "audience_loser")
    assert loser_conf == max(40, winner_conf - 10)
    assert loser_conf < winner_conf


def test_confidence_cap_at_90_for_audience_winner() -> None:
    rollups = [
        rollup(creative_ref="A1", audience="parents",   conversions=500, spend=1_000),
        rollup(creative_ref="A2", audience="executives", conversions=10,  spend=2_000),
    ]
    drafts = summarise_audiences(rollups)
    winner = next(d for d in drafts if d.kind == "audience_winner")
    assert winner.confidence == 90


def test_pools_creatives_within_an_audience() -> None:
    rollups = [
        rollup(creative_ref="A1a", audience="parents",   conversions=10, spend=500),
        rollup(creative_ref="A1b", audience="parents",   conversions=10, spend=500),  # combined 20 / 1000
        rollup(creative_ref="A2",  audience="executives", conversions=10, spend=2_000),
    ]
    drafts = summarise_audiences(rollups)
    winner = next(d for d in drafts if d.kind == "audience_winner")
    assert winner.evidence["creatives_count"] == 2
    assert sorted(winner.evidence["creative_refs"]) == ["A1a", "A1b"]
    assert winner.evidence["conversions"] == 20
