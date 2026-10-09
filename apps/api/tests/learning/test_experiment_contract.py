"""Phase 7.4 — unit tests for the experiment contract + evidence integrity.

Pure (no DB): validates the server-side contract and the deterministic verdicts.
Proves BRO cannot ship an underspecified experiment, cannot manufacture a
significant result, and that inconclusive/incomparable/insufficient cases stay
honest.
"""

from __future__ import annotations

import pytest

from aicmo.modules.learning.experiment_contract import (
    NOISE_BAND,
    EvidenceVerdict,
    ExperimentContractError,
    PrimaryMetric,
    _Side,
    assess_evidence,
    proposal_fingerprint,
    validate_proposal,
)


def _valid_proposal_dict() -> dict:
    return {
        "business_objective": "Get more qualified leads from Instagram",
        "hypothesis": "Founder-led reels beat product carousels for lead intent",
        "primary_metric": "leads",
        "comparison": "Founder reel vs product carousel, same offer",
        "variants": [
            {"label": "Reel", "variable_choices": {"format": "reel"}},
            {"label": "Carousel", "variable_choices": {"format": "carousel"}},
        ],
        "audience": "IN, 18-30, fitness",
        "channel": "instagram",
        "measurement_window_days": 14,
        "success_condition": "Reel yields >=20% more leads at >=100 impressions per arm",
        "inconclusive_condition": "Difference within the 10% noise band or under 100 impressions",
    }


def test_valid_proposal_accepted_and_fingerprint_stable():
    p = validate_proposal(_valid_proposal_dict())
    assert p.primary_metric is PrimaryMetric.LEADS
    # Fingerprint ignores variant order + audience wording.
    d2 = _valid_proposal_dict()
    d2["variants"] = list(reversed(d2["variants"]))
    d2["audience"] = "totally different audience text"
    assert proposal_fingerprint(p) == proposal_fingerprint(validate_proposal(d2))


@pytest.mark.parametrize(
    "mutate",
    [
        lambda d: d.update(variants=[d["variants"][0]]),  # only one variant
        lambda d: d.update(success_condition=""),  # no success condition
        lambda d: d.update(inconclusive_condition=""),  # no inconclusive condition
        lambda d: d.update(primary_metric="vanity_metric"),  # not a measured metric
        lambda d: d.update(measurement_window_days=0),  # window out of range
        lambda d: d.update(hypothesis=""),  # no hypothesis
        lambda d: d.update(variants=[  # duplicate variant labels
            {"label": "Reel"}, {"label": "reel"},
        ]),
    ],
)
def test_invalid_proposals_rejected(mutate):
    d = _valid_proposal_dict()
    mutate(d)
    with pytest.raises(ExperimentContractError):
        validate_proposal(d)


def _side(**kw) -> _Side:
    base = dict(goal="leads", asset_type="content", platform="instagram",
                impressions=500, metric_value=20.0, variable_choices={"format": "reel"})
    base.update(kw)
    return _Side(**base)


def test_insufficient_when_primary_volume_too_low():
    a = assess_evidence(primary_metric=PrimaryMetric.LEADS,
                        primary=_side(impressions=20, metric_value=2.0), baseline=None)
    assert a.verdict is EvidenceVerdict.INSUFFICIENT_EVIDENCE
    assert a.effect is None


def test_single_arm_is_inconclusive_not_a_winner():
    a = assess_evidence(primary_metric=PrimaryMetric.LEADS, primary=_side(), baseline=None)
    assert a.verdict is EvidenceVerdict.INCONCLUSIVE
    assert any("no comparison" in r.lower() for r in a.reasons)


def test_incomparable_objective_or_format():
    a = assess_evidence(
        primary_metric=PrimaryMetric.LEADS,
        primary=_side(goal="leads", asset_type="content", metric_value=30.0),
        baseline=_side(goal="awareness", asset_type="visual", metric_value=20.0),
    )
    assert a.verdict is EvidenceVerdict.INCOMPARABLE


def test_clear_win_is_supported():
    a = assess_evidence(
        primary_metric=PrimaryMetric.LEADS,
        primary=_side(metric_value=30.0),
        baseline=_side(metric_value=20.0),
    )
    assert a.verdict is EvidenceVerdict.SUPPORTED
    assert a.effect is not None and a.effect > NOISE_BAND


def test_clear_loss_is_contradicted():
    a = assess_evidence(
        primary_metric=PrimaryMetric.LEADS,
        primary=_side(metric_value=12.0),
        baseline=_side(metric_value=20.0),
    )
    assert a.verdict is EvidenceVerdict.CONTRADICTED


def test_small_fluctuation_is_inconclusive():
    a = assess_evidence(
        primary_metric=PrimaryMetric.LEADS,
        primary=_side(metric_value=21.0),  # +5% < 10% noise band
        baseline=_side(metric_value=20.0),
    )
    assert a.verdict is EvidenceVerdict.INCONCLUSIVE


def test_confounded_contrast_downgraded_to_inconclusive():
    # Big raw difference, but multiple creative variables differ → cannot attribute.
    a = assess_evidence(
        primary_metric=PrimaryMetric.LEADS,
        primary=_side(metric_value=40.0, variable_choices={"format": "reel", "tone": "bold", "cta": "dm"}),
        baseline=_side(metric_value=20.0, variable_choices={"format": "carousel", "tone": "calm", "cta": "link"}),
    )
    assert a.verdict is EvidenceVerdict.INCONCLUSIVE
    assert any("confounded" in r.lower() for r in a.reasons)


def test_unequal_exposure_downgraded_to_inconclusive():
    a = assess_evidence(
        primary_metric=PrimaryMetric.LEADS,
        primary=_side(impressions=5000, metric_value=40.0),
        baseline=_side(impressions=150, metric_value=20.0),  # >3x exposure gap
    )
    assert a.verdict is EvidenceVerdict.INCONCLUSIVE
    assert any("exposure" in r.lower() for r in a.reasons)


def test_no_assessment_fabricates_a_confidence_percentage():
    a = assess_evidence(
        primary_metric=PrimaryMetric.LEADS,
        primary=_side(metric_value=30.0), baseline=_side(metric_value=20.0),
    )
    # data_strength is the volume proxy (<=0.85), never a 0-100 significance claim.
    assert 0.0 <= a.data_strength <= 0.85
    assert "not proof of cause" in a.note.lower()
