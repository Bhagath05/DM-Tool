"""Phase 9.1.5 — recommender template tests.

Two pillars:

  1. Every new diagnostic kind has a non-empty, contract-compliant
     template that runs through `compose()` and `to_card()` cleanly.

  2. The banned-phrase lint: no template emits media-buyer jargon
     ("CTR", "creative fatigue", "media buy", etc.). If a template
     drifts to jargon a customer wouldn't understand, this fails.
"""

from __future__ import annotations

import uuid
from datetime import datetime

import pytest

from aicmo.modules.performance import recommender
from aicmo.modules.performance.schemas import DiagnosticDraft

# ---------------------------------------------------------------------
#  Banned-phrase list — Constitution-aligned
#
#  Match-rules: case-insensitive substring. Watch for false positives
#  on word boundaries (e.g. "frequency" inside "infrequency") — we
#  haven't tripped any yet but if we do, switch the test to a regex
#  with word boundaries.
# ---------------------------------------------------------------------

BANNED_PHRASES = (
    "ctr",
    "cpc",
    "cpm",
    "roas",
    "creative fatigue",
    "audience segment",
    "media buy",
    "media buyer",
    "leverage",
    "synergize",
    "synergise",
    "click-through",
    "impression share",
    "optimise spend",
    "optimize spend",
    "performant",
    "monetize the funnel",
    "monetise the funnel",
)


# ---------------------------------------------------------------------
#  Per-kind fixtures
# ---------------------------------------------------------------------


def _draft(kind: str, evidence: dict, *, conf: int = 75, impact: str = "lead") -> DiagnosticDraft:
    return DiagnosticDraft(
        kind=kind,  # type: ignore[arg-type]
        impact_category=impact,  # type: ignore[arg-type]
        confidence=conf,
        subject_creative_ref="subject",
        evidence=evidence,
    )


KIND_FIXTURES: list[tuple[str, dict, str]] = [
    (
        "audience_winner",
        {
            "audience": "parents",
            "creatives_count": 2,
            "creative_refs": ["A", "B"],
            "impressions": 5000, "clicks": 200, "conversions": 20,
            "spend": 1000.0, "currency": "INR",
            "cpl": 50.0, "roas": 4.0,
            "runner_up_audience": "executives", "runner_up_cpl": 200.0,
            "field_size": 3,
        },
        "lead",
    ),
    (
        "audience_loser",
        {
            "audience": "executives",
            "creatives_count": 1, "creative_refs": ["C"],
            "impressions": 5000, "conversions": 5,
            "spend": 2500.0, "currency": "INR", "cpl": 500.0,
            "winner_audience": "parents", "winner_cpl": 50.0,
            "cpl_ratio": 10.0,
        },
        "cost",
    ),
    (
        "concept_winner",
        {
            "concept_family": "family_experience",
            "creatives_count": 2, "creative_refs": ["A", "B"],
            "impressions": 5000, "clicks": 200, "conversions": 20,
            "spend": 1000.0, "currency": "INR",
            "cpl": 50.0, "roas": 4.0,
            "runner_up": "authority", "runner_up_cpl": 200.0,
            "field_size": 2,
        },
        "lead",
    ),
    (
        "emotion_winner",
        {
            "emotion": "warmth",
            "creatives_count": 2, "creative_refs": ["A", "B"],
            "impressions": 5000, "clicks": 200, "conversions": 20,
            "spend": 1000.0, "currency": "INR",
            "cpl": 50.0, "roas": 4.0,
            "runner_up": "trust", "runner_up_cpl": 150.0,
            "field_size": 2,
        },
        "lead",
    ),
    (
        "funnel_winner",
        {
            "funnel_stage": "conversion",
            "creatives_count": 2, "creative_refs": ["A", "B"],
            "impressions": 5000, "clicks": 200, "conversions": 20,
            "spend": 1000.0, "currency": "INR",
            "cpl": 50.0, "roas": 4.0,
            "runner_up": "consideration", "runner_up_cpl": 150.0,
            "field_size": 2,
        },
        "lead",
    ),
    (
        "pattern_winner",
        {
            "pattern": ("family_experience", "warmth"),
            "pattern_label": "family_experience × warmth",
            "concept_family": "family_experience", "emotion": "warmth",
            "creatives_count": 2, "creative_refs": ["A", "B"],
            "impressions": 5000, "clicks": 200, "conversions": 20,
            "spend": 1000.0, "currency": "INR",
            "cpl": 50.0, "roas": 4.0,
            "runner_up": "authority", "runner_up_cpl": 150.0,
            "field_size": 2,
        },
        "lead",
    ),
    (
        "offer_winner",
        {
            "offer_type": "consultation",
            "creatives_count": 2, "creative_refs": ["A", "B"],
            "clicks": 200, "conversions": 30, "cvr": 0.15,
            "spend": 1000.0, "currency": "INR",
            "runner_up_offer": "discount", "runner_up_cvr": 0.05,
            "cvr_ratio": 3.0, "field_size": 2,
        },
        "revenue",
    ),
    (
        "offer_pricing_sensitivity",
        {
            "better_side": "discount_on",
            "better_cvr": 0.20, "better_conversions": 30, "better_creatives": 3,
            "worse_side": "discount_off",
            "worse_cvr": 0.10, "worse_conversions": 15, "worse_creatives": 3,
            "cvr_ratio": 2.0, "currency": "INR",
        },
        "revenue",
    ),
    (
        "scale_candidate",
        {
            "creative_ref": "Family reel A",
            "platform": "meta",
            "cpl": 50.0, "brand_avg_cpl": 150.0,
            "cpl_advantage_ratio": 3.0,
            "spend": 1000.0, "currency": "INR",
            "conversions": 20, "headroom_share": 0.7,
            "concept_family": "family_experience", "audience": "parents",
        },
        "lead",
    ),
    (
        "budget_waste",
        {
            "creative_ref": "Generic banner",
            "platform": "meta",
            "cpl": 500.0, "brand_avg_cpl": 100.0,
            "cpl_overrun_ratio": 5.0,
            "spend": 2500.0, "currency": "INR",
            "conversions": 5, "spend_share": 0.4,
            "freed_leads_estimate": 20,
        },
        "cost",
    ),
    (
        "creative_dna",
        {
            "audience": "parents", "concept_family": "family_experience",
            "emotion": "warmth", "offer_type": "consultation",
            "funnel_stage": "conversion",
            "creatives_count": 2, "creative_refs": ["A", "B"],
            "impressions": 5000, "clicks": 200, "conversions": 38,
            "spend": 2000.0, "currency": "INR",
            "cpl": 52.6, "roas": 4.5,
            "runner_up_cpl": 250.0, "field_size": 2,
        },
        "revenue",
    ),
]


# ---------------------------------------------------------------------
#  Tests
# ---------------------------------------------------------------------


@pytest.mark.parametrize("kind,evidence,impact", KIND_FIXTURES, ids=[f[0] for f in KIND_FIXTURES])
def test_compose_returns_five_non_empty_fields(kind, evidence, impact) -> None:
    what, why, rec, expected, reason = recommender.compose(_draft(kind, evidence, impact=impact))
    for s in (what, why, rec, expected, reason):
        assert isinstance(s, str)
        assert len(s.strip()) >= 3
        # Defensive — these should never appear in a rendered card.
        assert "None" not in s, f"{kind!r} leaked 'None' into output"


@pytest.mark.parametrize("kind,evidence,impact", KIND_FIXTURES, ids=[f[0] for f in KIND_FIXTURES])
def test_compose_contains_no_banned_jargon(kind, evidence, impact) -> None:
    """Constitution: founder language only. No CTR / CPM / 'leverage' / etc."""
    what, why, rec, expected, reason = recommender.compose(_draft(kind, evidence, impact=impact))
    bundle = " ".join([what, why, rec, expected, reason]).lower()
    for banned in BANNED_PHRASES:
        assert banned not in bundle, (
            f"{kind!r} contains banned phrase '{banned}'. Rewrite in founder language."
        )


@pytest.mark.parametrize("kind,evidence,impact", KIND_FIXTURES, ids=[f[0] for f in KIND_FIXTURES])
def test_compose_renders_account_currency_not_hardcoded(kind, evidence, impact) -> None:
    """Switch every fixture's currency to USD; confirm no INR leaks."""
    e = dict(evidence)
    if "currency" in e:
        e["currency"] = "USD"
    if "winner_currency" in e:
        e["winner_currency"] = "USD"
    what, why, rec, expected, reason = recommender.compose(_draft(kind, e, impact=impact))
    bundle = " ".join([what, why, rec, expected, reason])
    assert "INR" not in bundle, f"{kind!r} leaks hardcoded INR with USD evidence"


@pytest.mark.parametrize("kind,evidence,impact", KIND_FIXTURES, ids=[f[0] for f in KIND_FIXTURES])
def test_to_card_passes_pydantic_validation(kind, evidence, impact) -> None:
    card = recommender.to_card(
        _draft(kind, evidence, impact=impact),
        record_id=uuid.uuid4(),
        status="open",
        created_at=datetime.utcnow(),
    )
    assert card.kind == kind
    # Every Constitution field non-empty.
    for field in (
        "what_happened", "why", "recommendation", "expected_result", "reason"
    ):
        assert getattr(card, field).strip()


def test_creative_dna_card_spells_out_all_five_dimensions() -> None:
    """User spec: DNA card must call out audience/feeling/angle/offer/buyer-stage."""
    fixture = next(f for f in KIND_FIXTURES if f[0] == "creative_dna")
    what, *_ = recommender.compose(_draft(fixture[0], fixture[1], impact=fixture[2]))
    bundle = what.lower()
    for must_have in ("audience", "feeling", "angle", "offer", "buyer stage"):
        assert must_have in bundle, f"DNA 'what' missing label: {must_have!r}"
