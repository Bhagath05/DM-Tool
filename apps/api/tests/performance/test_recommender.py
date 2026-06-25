"""Recommender / Constitution-contract tests — Phase 9.1.

Every diagnostic that the recommender composes must be:
  - non-empty in all five Constitution fields (what / why / rec / expected / reason)
  - never hardcoded to INR — currency comes from evidence
  - parametrised on the actual evidence (creative names, counts, money)

Plus we run the composed cards through the Pydantic response schema
to assert the AiRecommendation contract holds at the API edge.
"""

from __future__ import annotations

import uuid
from datetime import datetime

from aicmo.modules.performance import recommender
from aicmo.modules.performance.schemas import (
    DiagnosticDraft,
    PerformanceDiagnosticCard,
)


def _winner_draft(
    *,
    confidence: int = 75,
    currency: str = "INR",
    cpl: float = 50.0,
    runner_up_cpl: float | None = 100.0,
) -> DiagnosticDraft:
    return DiagnosticDraft(
        kind="winner",
        impact_category="lead",
        confidence=confidence,
        subject_creative_ref="Family dinner reel",
        evidence={
            "creative_ref": "Family dinner reel",
            "platform": "meta",
            "concept_family": "family_experience",
            "audience": "parents_25_45",
            "offer_type": "consultation",
            "impressions": 12_400,
            "clicks": 240,
            "conversions": 20,
            "spend": 1_000.0,
            "currency": currency,
            "cpl": cpl,
            "roas": None,
            "runner_up_ref": "Founder story" if runner_up_cpl else None,
            "runner_up_cpl": runner_up_cpl,
        },
    )


def _realloc_draft() -> DiagnosticDraft:
    return DiagnosticDraft(
        kind="budget_reallocation",
        impact_category="lead",
        confidence=65,
        subject_creative_ref="Family dinner reel",
        evidence={
            "winner_ref": "Family dinner reel",
            "winner_cpl": 50.0,
            "winner_currency": "INR",
            "underperformer_ref": "Generic banner ad",
            "underperformer_cpl": 200.0,
            "underperformer_spend": 5_000.0,
            "underperformer_conversions": 25,
            "cpl_ratio": 4.0,
        },
    )


# ---------------------------------------------------------------------
#  Constitution contract — every field non-empty
# ---------------------------------------------------------------------


def test_compose_winner_returns_five_non_empty_strings() -> None:
    what, why, rec, expected, reason = recommender.compose(_winner_draft())
    for s in (what, why, rec, expected, reason):
        assert isinstance(s, str)
        assert len(s.strip()) >= 3


def test_compose_realloc_returns_five_non_empty_strings() -> None:
    what, why, rec, expected, reason = recommender.compose(_realloc_draft())
    for s in (what, why, rec, expected, reason):
        assert isinstance(s, str)
        assert len(s.strip()) >= 3


def test_compose_winner_includes_creative_name() -> None:
    what, *_ = recommender.compose(_winner_draft())
    assert "Family dinner reel" in what


def test_compose_winner_renders_account_currency_not_hardcoded_inr() -> None:
    """Constitution: never hardcode INR. Currency comes from evidence."""
    draft = _winner_draft(currency="USD", cpl=20.0, runner_up_cpl=40.0)
    what, why, rec, expected, reason = recommender.compose(draft)
    bundle = " ".join([what, why, rec, expected, reason])
    assert "USD" in bundle
    assert "INR" not in bundle  # specifically not leaked


def test_compose_winner_recommendation_mentions_specific_tags() -> None:
    """When tags are present, the recommendation should be more concrete."""
    _, _, rec, _, _ = recommender.compose(_winner_draft())
    rec_lower = rec.lower()
    assert "family experience" in rec_lower or "family_experience" in rec_lower
    assert "parents" in rec_lower
    assert "consultation" in rec_lower


def test_compose_winner_recommendation_stays_clean_without_tags() -> None:
    """When tags are None, no awkward 'None' or 'undefined' appears."""
    draft = _winner_draft()
    draft.evidence["concept_family"] = None
    draft.evidence["audience"] = None
    draft.evidence["offer_type"] = None
    _, _, rec, _, _ = recommender.compose(draft)
    assert "None" not in rec
    assert "undefined" not in rec


def test_compose_winner_expected_result_scales_with_confidence() -> None:
    high = recommender.compose(_winner_draft(confidence=85))[3]
    low = recommender.compose(_winner_draft(confidence=55))[3]
    assert high != low
    # The high-confidence variant should make a bigger claim.
    assert "30" in high or "50" in high
    assert "15" in low or "30" in low


def test_compose_realloc_recommendation_says_move_not_pause() -> None:
    """Phase 9.1: never recommend pausing. Spend reallocation only."""
    _, _, rec, _, _ = recommender.compose(_realloc_draft())
    rec_lower = rec.lower()
    assert "move" in rec_lower or "shift" in rec_lower
    assert "pause" not in rec_lower or "don't pause" in rec_lower or "don’t pause" in rec_lower


def test_compose_realloc_expected_result_quantifies_when_possible() -> None:
    """If we have spend + CPLs, the expected_result should give a
    concrete extra-leads estimate (not 'noticeable')."""
    _, _, _, expected, _ = recommender.compose(_realloc_draft())
    # 5000 INR / 50 = 100 leads at winner CPL; 5000/200 = 25 leads now.
    # Should mention something like "75 more leads".
    assert any(ch.isdigit() for ch in expected)


# ---------------------------------------------------------------------
#  Pydantic response shape — pins the API contract
# ---------------------------------------------------------------------


def test_to_card_passes_full_pydantic_validation() -> None:
    draft = _winner_draft()
    card = recommender.to_card(
        draft,
        record_id=uuid.uuid4(),
        status="open",
        created_at=datetime.utcnow(),
    )
    # PerformanceDiagnosticCard enforces min_length=3 on every text
    # field and confidence range 0-100. If any composer template
    # drifts, this fails at construction time.
    assert isinstance(card, PerformanceDiagnosticCard)
    assert card.confidence == draft.confidence
    assert card.impact_category == "lead"
    assert card.what_happened
    assert card.why
    assert card.recommendation
    assert card.expected_result
    assert card.reason


def test_compose_raises_for_unknown_kind() -> None:
    """Future-proofing: if a new kind is added but the recommender
    forgets to template it, we crash loudly rather than ship a half-card."""
    draft = DiagnosticDraft(
        kind="winner",  # we'll mutate after construction since enum is checked
        impact_category="lead",
        confidence=70,
        subject_creative_ref="X",
        evidence={},
    )
    object.__setattr__(draft, "kind", "fatigue")  # bypass enum check
    try:
        recommender.compose(draft)
    except NotImplementedError:
        return
    raise AssertionError("expected NotImplementedError for un-templated kind")
