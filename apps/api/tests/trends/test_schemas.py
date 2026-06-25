"""Trends schema — Founder Experience Audit (Batch 3) tests.

Locks in the Constitution-contract refit of ``TrendingTopic`` and the
backward-compatibility guarantee for reports already persisted in
Postgres.

Coverage:
- New advisory fields (recommended_action / expected_result /
  confidence / reason) hydrate when present and validate range/length.
- The schema still accepts the *legacy* shape (relevance_score only,
  no advisory fields) so old reports don't break loading.
- Confidence is bounded 1-100; length floors prevent the LLM from
  emitting near-empty strings that would render as useless cards.
"""

from __future__ import annotations

import pytest
from pydantic import ValidationError

from aicmo.modules.trends.schemas import TrendAnalysis, TrendingTopic


def _legacy_topic() -> dict:
    """The pre-Batch-3 shape — what's already sitting in old DB rows."""
    return {
        "topic": "Specialty coffee guides",
        "why_it_matters": "Your audience is asking espresso questions on Reddit.",
        "suggested_angles": ["Bean-by-bean walkthrough", "Pour-over basics"],
        "relevance_score": 78,
    }


def _new_topic() -> dict:
    """The post-Batch-3 shape the LLM now emits."""
    return {
        **_legacy_topic(),
        "recommended_action": (
            "Post a 60-second Instagram reel walking through your espresso "
            "bean selection."
        ),
        "expected_result": (
            "Likely 80-150 extra people see it; 1-3 walk in this week."
        ),
        "confidence": 78,
        "reason": (
            "'Espresso bean comparison' is rising +45% on Google Trends "
            "and your audience is already on Instagram."
        ),
    }


# ----------------------------------------------------------------------
#  Backward compatibility — legacy reports still load
# ----------------------------------------------------------------------


def test_topic_accepts_legacy_shape_without_advisory_fields() -> None:
    """Old reports persisted before Batch 3 must still hydrate.

    We intentionally made the four advisory fields nullable in the
    persistence schema so existing JSON in Postgres doesn't fail
    validation on read. Without this test the migration story is
    invisible — a future tightening of the contract would silently
    break the trends list page.
    """
    topic = TrendingTopic.model_validate(_legacy_topic())

    assert topic.recommended_action is None
    assert topic.expected_result is None
    assert topic.confidence is None
    assert topic.reason is None
    # Legacy field still present (frontend hides it but persistence keeps it).
    assert topic.relevance_score == 78


def test_topic_accepts_legacy_shape_without_any_score() -> None:
    """Even older reports with no `relevance_score` at all must load."""
    raw = _legacy_topic()
    del raw["relevance_score"]
    topic = TrendingTopic.model_validate(raw)
    assert topic.relevance_score is None


# ----------------------------------------------------------------------
#  New contract — happy path
# ----------------------------------------------------------------------


def test_topic_accepts_full_advisory_contract() -> None:
    topic = TrendingTopic.model_validate(_new_topic())

    assert topic.recommended_action and len(topic.recommended_action) >= 10
    assert topic.expected_result and len(topic.expected_result) >= 10
    assert topic.reason and len(topic.reason) >= 10
    assert topic.confidence == 78


def test_topic_round_trips_through_model_dump() -> None:
    """Persistence path: a new topic must round-trip without loss."""
    topic = TrendingTopic.model_validate(_new_topic())
    dumped = topic.model_dump(mode="json")
    rehydrated = TrendingTopic.model_validate(dumped)
    assert rehydrated.recommended_action == topic.recommended_action
    assert rehydrated.expected_result == topic.expected_result
    assert rehydrated.confidence == topic.confidence
    assert rehydrated.reason == topic.reason


# ----------------------------------------------------------------------
#  Validation — confidence bounds and string floors
# ----------------------------------------------------------------------


@pytest.mark.parametrize("bad", [0, -1, 101, 200])
def test_confidence_must_be_1_to_100(bad: int) -> None:
    raw = _new_topic()
    raw["confidence"] = bad
    with pytest.raises(ValidationError):
        TrendingTopic.model_validate(raw)


@pytest.mark.parametrize(
    "field",
    ["recommended_action", "expected_result", "reason"],
)
def test_advisory_strings_have_a_meaningful_minimum_length(field: str) -> None:
    """The Constitution requires non-trivial copy. A 3-char `recommended_action`
    like "Do." would render as a useless card — the schema rejects it
    so a buggy LLM response fails loudly instead of silently shipping
    garbage to the founder."""
    raw = _new_topic()
    raw[field] = "ok"  # < min_length=10
    with pytest.raises(ValidationError):
        TrendingTopic.model_validate(raw)


def test_advisory_strings_have_a_max_length_to_protect_card_layout() -> None:
    raw = _new_topic()
    raw["recommended_action"] = "x" * 400  # > max_length=300
    with pytest.raises(ValidationError):
        TrendingTopic.model_validate(raw)


# ----------------------------------------------------------------------
#  TrendAnalysis — wraps a list of topics
# ----------------------------------------------------------------------


def test_analysis_validates_with_mix_of_legacy_and_new_topics() -> None:
    """A report could legally hold a mix during the rollout — e.g. a
    cached legacy report being supplemented mid-flight. Both shapes
    must coexist in the same list."""
    raw = {
        "summary": "Specialty coffee interest is climbing across your platforms.",
        "trending_topics": [_legacy_topic(), _new_topic()],
        "content_ideas": [
            {
                "platform": "Instagram",
                "format": "reel",
                "hook": "The 30-second bean test we use every morning.",
                "description": "Show how you taste-test a new bean shipment.",
            }
        ],
        "hashtag_clusters": [
            {
                "theme": "Specialty coffee",
                "hashtags": ["#coffee", "#specialtycoffee", "#barista"],
            }
        ],
        "marketing_angles": ["Lead with the bean origin story."],
    }
    analysis = TrendAnalysis.model_validate(raw)
    assert len(analysis.trending_topics) == 2
    # Legacy first, new second.
    assert analysis.trending_topics[0].confidence is None
    assert analysis.trending_topics[1].confidence == 78
