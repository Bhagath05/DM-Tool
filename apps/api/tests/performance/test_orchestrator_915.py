"""Phase 9.1.5 — orchestrator integration tests.

Verifies the family top-N gate, dedup-by-subject, and 9.1 backward
compatibility (the two baseline cards still fire).
"""

from __future__ import annotations

from aicmo.modules.performance.diagnostics import diagnose

from ._fixtures import rollup


def _scenario() -> list:
    """A rich enough rollup that every layer can potentially fire."""
    return [
        # Family creatives — cheap leads, parents audience, consultation offer.
        rollup(
            creative_ref="Family reel A",
            conversions=20, spend=1_000, conversion_value=4_000,
            audience="parents", concept_family="family_experience",
            emotion="warmth", funnel_stage="conversion", offer_type="consultation",
        ),
        rollup(
            creative_ref="Family reel B",
            conversions=20, spend=1_000, conversion_value=4_000,
            audience="parents", concept_family="family_experience",
            emotion="warmth", funnel_stage="conversion", offer_type="consultation",
        ),
        # Authority creatives — middling, executives audience, none offer.
        rollup(
            creative_ref="Authority deck A",
            conversions=10, spend=1_500, conversion_value=2_000,
            audience="executives", concept_family="authority",
            emotion="trust", funnel_stage="consideration", offer_type="none",
        ),
        rollup(
            creative_ref="Authority deck B",
            conversions=8, spend=1_500, conversion_value=1_600,
            audience="executives", concept_family="authority",
            emotion="trust", funnel_stage="consideration", offer_type="none",
        ),
        # Wasteful banner — high CPL, meaningful spend.
        rollup(
            creative_ref="Generic banner",
            conversions=5, spend=2_500, conversion_value=1_000,
            audience="executives", concept_family="authority",
            emotion="trust", funnel_stage="consideration", offer_type="none",
        ),
    ]


def test_top_n_gate_caps_at_seven_cards() -> None:
    drafts = diagnose(_scenario())
    assert 0 < len(drafts) <= 7


def test_at_most_one_card_per_intelligence_family() -> None:
    drafts = diagnose(_scenario())
    families = {
        "audience": {"audience_winner", "audience_loser"},
        "creative": {
            "concept_winner",
            "emotion_winner",
            "funnel_winner",
            "pattern_winner",
        },
        "offer": {"offer_winner", "offer_pricing_sensitivity"},
        "scaling": {"scale_candidate", "budget_waste"},
        "dna": {"creative_dna"},
    }
    for family, kinds in families.items():
        in_family = [d for d in drafts if d.kind in kinds]
        assert len(in_family) <= 1, f"{family} fired {len(in_family)} cards"


def test_baseline_cards_still_fire() -> None:
    drafts = diagnose(_scenario())
    kinds = {d.kind for d in drafts}
    assert "winner" in kinds


def test_orchestrator_dedupes_by_subject() -> None:
    drafts = diagnose(_scenario())
    subjects = [d.subject_creative_ref for d in drafts]
    assert len(subjects) == len(set(subjects))


def test_orchestrator_sorts_confidence_desc() -> None:
    drafts = diagnose(_scenario())
    confs = [d.confidence for d in drafts]
    assert confs == sorted(confs, reverse=True)


def test_orchestrator_returns_empty_when_no_sample() -> None:
    rollups = [
        rollup(creative_ref="A", sample_state="insufficient"),
        rollup(creative_ref="B", sample_state="insufficient"),
    ]
    assert diagnose(rollups) == []


def test_orchestrator_returns_empty_when_no_conversions() -> None:
    rollups = [
        rollup(creative_ref="A", conversions=0),
        rollup(creative_ref="B", conversions=0),
    ]
    assert diagnose(rollups) == []


def test_creative_dna_in_output_when_full_tags_present() -> None:
    drafts = diagnose(_scenario())
    kinds = {d.kind for d in drafts}
    assert "creative_dna" in kinds
