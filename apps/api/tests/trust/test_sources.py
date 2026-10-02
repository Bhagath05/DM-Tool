"""Source taxonomy: provenance quality, not a universal ranking."""

from __future__ import annotations

import pytest

from aicmo.modules.trust.enums import SourceTier
from aicmo.modules.trust.sources import (
    can_back_causal,
    can_back_fact,
    can_back_metric,
    is_grounding,
    is_monetary_grade,
)

_GROUNDING = [
    SourceTier.VERIFIED_PROVIDER, SourceTier.FIRST_PARTY_DATA,
    SourceTier.USER_PROVIDED, SourceTier.DERIVED_INTERNAL, SourceTier.RESEARCH,
]
_NON_GROUNDING = [SourceTier.MODEL_INFERENCE, SourceTier.UNKNOWN]


@pytest.mark.parametrize("tier", _GROUNDING)
def test_grounding_tiers(tier) -> None:
    assert is_grounding(tier)
    assert can_back_metric(tier)


@pytest.mark.parametrize("tier", _NON_GROUNDING)
def test_non_grounding_tiers(tier) -> None:
    assert not is_grounding(tier)
    assert not can_back_metric(tier)


def test_fact_needs_a_grounding_source() -> None:
    assert can_back_fact([SourceTier.MODEL_INFERENCE, SourceTier.FIRST_PARTY_DATA])
    assert not can_back_fact([SourceTier.MODEL_INFERENCE, SourceTier.UNKNOWN])
    assert not can_back_fact([])


def test_causal_needs_a_grounding_source() -> None:
    assert can_back_causal([SourceTier.VERIFIED_PROVIDER])
    assert not can_back_causal([SourceTier.UNKNOWN])


def test_monetary_grade() -> None:
    assert is_monetary_grade(SourceTier.VERIFIED_PROVIDER)
    assert is_monetary_grade(SourceTier.FIRST_PARTY_DATA)
    for tier in [SourceTier.USER_PROVIDED, SourceTier.RESEARCH, SourceTier.MODEL_INFERENCE]:
        assert not is_monetary_grade(tier)
