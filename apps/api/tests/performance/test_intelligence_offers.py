"""Phase 9.1.5 — Offer Intelligence tests."""

from __future__ import annotations

from aicmo.modules.performance.intelligence.offers import (
    summarise_offers,
    summarise_pricing_sensitivity,
)

from ._fixtures import rollup


# ---------------------------------------------------------------------
#  Offer winner (CVR-based)
# ---------------------------------------------------------------------


def test_offer_winner_picks_highest_cvr_offer() -> None:
    rollups = [
        # Free consult: 20 / 100 clicks = 20% CVR
        rollup(creative_ref="C1", offer_type="consultation", clicks=100, conversions=20, spend=1_000),
        # Discount: 5 / 100 clicks = 5% CVR
        rollup(creative_ref="D1", offer_type="discount", clicks=100, conversions=5, spend=1_500),
    ]
    drafts = summarise_offers(rollups)
    assert drafts[0].kind == "offer_winner"
    assert drafts[0].evidence["offer_type"] == "consultation"
    assert drafts[0].evidence["runner_up_offer"] == "discount"


def test_offer_winner_silent_when_only_one_offer_present() -> None:
    rollups = [
        rollup(creative_ref="C1", offer_type="consultation", clicks=100, conversions=20),
        rollup(creative_ref="C2", offer_type="consultation", clicks=100, conversions=15),
    ]
    assert summarise_offers(rollups) == []


# ---------------------------------------------------------------------
#  Pricing sensitivity (narrow scope)
# ---------------------------------------------------------------------


def test_pricing_silent_with_fewer_than_three_creatives_per_side() -> None:
    rollups = [
        rollup(creative_ref="D1", offer_type="discount", clicks=100, conversions=10, spend=500),
        rollup(creative_ref="D2", offer_type="discount", clicks=100, conversions=10, spend=500),
        rollup(creative_ref="N1", offer_type="none",     clicks=100, conversions=10, spend=500),
        rollup(creative_ref="N2", offer_type="none",     clicks=100, conversions=10, spend=500),
    ]
    assert summarise_pricing_sensitivity(rollups) == []


def test_pricing_fires_when_one_side_wins_clearly() -> None:
    # 3 discount creatives at low CVR, 3 no-discount at high CVR.
    rollups = (
        [rollup(creative_ref=f"D{i}", offer_type="discount", clicks=100, conversions=5, spend=500) for i in range(3)]
        + [rollup(creative_ref=f"N{i}", offer_type="none",   clicks=100, conversions=20, spend=500) for i in range(3)]
    )
    drafts = summarise_pricing_sensitivity(rollups)
    assert len(drafts) == 1
    d = drafts[0]
    assert d.kind == "offer_pricing_sensitivity"
    assert d.evidence["better_side"] == "discount_off"
    assert d.evidence["cvr_ratio"] >= 1.3


def test_pricing_silent_when_gap_below_threshold() -> None:
    # Both sides converge — no signal worth shipping.
    rollups = (
        [rollup(creative_ref=f"D{i}", offer_type="discount", clicks=100, conversions=15, spend=500) for i in range(3)]
        + [rollup(creative_ref=f"N{i}", offer_type="none",   clicks=100, conversions=15, spend=500) for i in range(3)]
    )
    assert summarise_pricing_sensitivity(rollups) == []


def test_pricing_confidence_capped_at_80() -> None:
    rollups = (
        [rollup(creative_ref=f"D{i}", offer_type="discount", clicks=100, conversions=2,  spend=500) for i in range(3)]
        + [rollup(creative_ref=f"N{i}", offer_type="none",   clicks=100, conversions=50, spend=500) for i in range(3)]
    )
    drafts = summarise_pricing_sensitivity(rollups)
    assert drafts[0].confidence <= 80
