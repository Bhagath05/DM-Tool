"""Phase 9.1.5 — Creative Intelligence + DNA tests.

Pins:
  - concept/emotion/funnel winners require ≥2 distinct tags w/ sample
  - pattern_winner (hook proxy) keys on the 2-tuple and surfaces
    concept_family + emotion in evidence
  - creative_dna requires ALL FIVE tags present
  - creative_dna confidence is capped at 80
"""

from __future__ import annotations

from aicmo.modules.performance.intelligence.creatives import (
    summarise_concepts,
    summarise_creative_dna,
    summarise_emotions,
    summarise_funnel_stages,
    summarise_patterns,
)

from ._fixtures import rollup


# ---------------------------------------------------------------------
#  Tag-level winners
# ---------------------------------------------------------------------


def test_concept_winner_requires_two_concepts() -> None:
    rollups = [
        rollup(creative_ref="A", concept_family="family_experience", conversions=20),
        rollup(creative_ref="B", concept_family="family_experience", conversions=15),
    ]
    assert summarise_concepts(rollups) == []


def test_concept_winner_picks_lowest_cpl_concept() -> None:
    rollups = [
        rollup(creative_ref="A", concept_family="family_experience", conversions=20, spend=1_000),
        rollup(creative_ref="B", concept_family="authority",         conversions=5,  spend=2_000),
    ]
    drafts = summarise_concepts(rollups)
    assert len(drafts) == 1
    assert drafts[0].evidence["concept_family"] == "family_experience"


def test_emotion_winner_returns_two_emotions_compared() -> None:
    rollups = [
        rollup(creative_ref="A", emotion="warmth", conversions=20, spend=1_000),
        rollup(creative_ref="B", emotion="trust",  conversions=10, spend=2_000),
    ]
    drafts = summarise_emotions(rollups)
    assert drafts[0].kind == "emotion_winner"
    assert drafts[0].evidence["emotion"] == "warmth"


def test_funnel_winner_translates_stage_to_plain_phrase_via_recommender() -> None:
    # We don't run the recommender here, but the draft should carry
    # the raw enum so the recommender can translate it.
    rollups = [
        rollup(creative_ref="A", funnel_stage="conversion",    conversions=20, spend=1_000),
        rollup(creative_ref="B", funnel_stage="consideration", conversions=8,  spend=2_000),
    ]
    drafts = summarise_funnel_stages(rollups)
    assert drafts[0].evidence["funnel_stage"] == "conversion"


# ---------------------------------------------------------------------
#  Pattern winner (hook proxy)
# ---------------------------------------------------------------------


def test_pattern_winner_keys_on_concept_emotion_tuple() -> None:
    rollups = [
        rollup(creative_ref="A", concept_family="family_experience", emotion="warmth", conversions=20, spend=1_000),
        rollup(creative_ref="B", concept_family="authority",         emotion="trust",  conversions=5,  spend=2_000),
    ]
    drafts = summarise_patterns(rollups)
    assert drafts[0].kind == "pattern_winner"
    e = drafts[0].evidence
    assert e["concept_family"] == "family_experience"
    assert e["emotion"] == "warmth"
    assert "pattern_label" in e


def test_pattern_winner_confidence_capped_at_85() -> None:
    rollups = [
        rollup(creative_ref="A", concept_family="family_experience", emotion="warmth", conversions=500, spend=1_000),
        rollup(creative_ref="B", concept_family="authority",         emotion="trust",  conversions=10,  spend=2_000),
    ]
    drafts = summarise_patterns(rollups)
    assert drafts[0].confidence == 85


def test_pattern_winner_skips_rollups_missing_either_half_of_the_combo() -> None:
    rollups = [
        rollup(creative_ref="A", concept_family="family_experience", emotion=None,     conversions=20, spend=1_000),
        rollup(creative_ref="B", concept_family=None,                emotion="trust",  conversions=20, spend=1_000),
    ]
    # Neither row contributes a full 2-tuple → no pattern signal.
    assert summarise_patterns(rollups) == []


# ---------------------------------------------------------------------
#  Creative DNA — apex card
# ---------------------------------------------------------------------


def _full_tags(over: dict | None = None) -> dict:
    base = dict(
        audience="parents",
        concept_family="family_experience",
        emotion="warmth",
        funnel_stage="conversion",
        offer_type="consultation",
    )
    if over:
        base.update(over)
    return base


def test_creative_dna_requires_all_five_tags() -> None:
    # Drop one tag — combo can't form.
    rollups = [
        rollup(creative_ref="A", conversions=20, spend=1_000, **_full_tags({"emotion": None})),
        rollup(creative_ref="B", conversions=20, spend=1_000, **_full_tags({"emotion": None})),
    ]
    assert summarise_creative_dna(rollups) == []


def test_creative_dna_fires_with_full_combo() -> None:
    rollups = [
        rollup(creative_ref="A", conversions=20, spend=1_000, **_full_tags()),
        rollup(creative_ref="B", conversions=15, spend=1_000, **_full_tags()),
    ]
    drafts = summarise_creative_dna(rollups)
    assert len(drafts) == 1
    d = drafts[0]
    assert d.kind == "creative_dna"
    for key in ("audience", "concept_family", "emotion", "offer_type", "funnel_stage"):
        assert d.evidence[key] is not None
    assert d.subject_creative_ref.startswith("dna:")


def test_creative_dna_picks_best_combo_among_multiple() -> None:
    rollups = [
        # Combo A — cheap leads.
        rollup(creative_ref="A1", conversions=20, spend=1_000, **_full_tags()),
        rollup(creative_ref="A2", conversions=20, spend=1_000, **_full_tags()),
        # Combo B — same shape but expensive.
        rollup(
            creative_ref="B1",
            conversions=5,
            spend=2_000,
            **_full_tags({"audience": "executives", "concept_family": "authority", "emotion": "trust"}),
        ),
        rollup(
            creative_ref="B2",
            conversions=5,
            spend=2_000,
            **_full_tags({"audience": "executives", "concept_family": "authority", "emotion": "trust"}),
        ),
    ]
    drafts = summarise_creative_dna(rollups)
    assert len(drafts) == 1
    assert drafts[0].evidence["audience"] == "parents"
    assert drafts[0].evidence["concept_family"] == "family_experience"


def test_creative_dna_confidence_capped_at_80() -> None:
    rollups = [
        rollup(creative_ref="A", conversions=500, spend=1_000, **_full_tags()),
        rollup(creative_ref="B", conversions=5,   spend=2_000,
               **_full_tags({"audience": "executives", "concept_family": "authority", "emotion": "trust"})),
    ]
    drafts = summarise_creative_dna(rollups)
    assert drafts[0].confidence == 80


def test_creative_dna_records_member_count_and_refs() -> None:
    rollups = [
        rollup(creative_ref="A1", conversions=20, spend=1_000, **_full_tags()),
        rollup(creative_ref="A2", conversions=15, spend=1_000, **_full_tags()),
        rollup(
            creative_ref="B1",
            conversions=5,
            spend=2_000,
            **_full_tags({"audience": "executives", "concept_family": "authority"}),
        ),
        rollup(
            creative_ref="B2",
            conversions=5,
            spend=2_000,
            **_full_tags({"audience": "executives", "concept_family": "authority"}),
        ),
    ]
    drafts = summarise_creative_dna(rollups)
    e = drafts[0].evidence
    assert e["creatives_count"] == 2
    assert sorted(e["creative_refs"]) == ["A1", "A2"]
