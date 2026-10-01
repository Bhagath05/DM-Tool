"""Phase 3D — belief freshness / decay (pure, no Postgres).

Pins every guarantee the resolver relies on: deterministic, bounded, never
negative, 0→0 (insufficient never ages up), monotonic with age, and honoring
the validity window.
"""

from __future__ import annotations

from datetime import UTC, datetime, timedelta

from aicmo.modules.belief import freshness


def _now() -> datetime:
    return datetime(2026, 1, 1, tzinfo=UTC)


def _aged(days: int) -> datetime:
    return _now() - timedelta(days=days)


def test_zero_confidence_never_ages_up():
    for days in (0, 30, 400):
        eff, reason = freshness.effective_confidence(
            original_confidence=0, reference_time=_aged(days), now=_now()
        )
        assert eff == 0
        assert "unvalidated" in reason.lower()


def test_fresh_window_keeps_full_confidence():
    eff, reason = freshness.effective_confidence(
        original_confidence=80, reference_time=_aged(5), now=_now()
    )
    assert eff == 80
    assert "current" in reason.lower()


def test_never_exceeds_original():
    for days in (0, 10, 60, 200, 1000):
        eff, _ = freshness.effective_confidence(
            original_confidence=70, reference_time=_aged(days), now=_now()
        )
        assert 0 <= eff <= 70


def test_monotonic_non_increasing_with_age():
    prev = 101
    for days in range(0, 400, 7):
        eff, _ = freshness.effective_confidence(
            original_confidence=90, reference_time=_aged(days), now=_now()
        )
        assert eff <= prev
        prev = eff


def test_stale_floors_at_forty_percent():
    eff, reason = freshness.effective_confidence(
        original_confidence=80, reference_time=_aged(365), now=_now()
    )
    assert eff == round(80 * 0.4)  # 60% max decay → 40% retained
    assert eff > 0  # never negative, never zero for a once-supported belief
    assert "aged down" in reason.lower()


def test_future_or_missing_reference_is_treated_as_fresh():
    future, _ = freshness.effective_confidence(
        original_confidence=60, reference_time=_now() + timedelta(days=30), now=_now()
    )
    missing, _ = freshness.effective_confidence(
        original_confidence=60, reference_time=None, now=_now()
    )
    assert future == 60 and missing == 60


def test_aging_band_between_fresh_and_stale_is_partial():
    fresh, _ = freshness.effective_confidence(
        original_confidence=80, reference_time=_aged(10), now=_now()
    )
    mid, _ = freshness.effective_confidence(
        original_confidence=80, reference_time=_aged(100), now=_now()
    )
    stale, _ = freshness.effective_confidence(
        original_confidence=80, reference_time=_aged(365), now=_now()
    )
    assert stale < mid < fresh


def test_is_expired():
    assert freshness.is_expired(None, _now()) is False
    assert freshness.is_expired(_now() - timedelta(seconds=1), _now()) is True
    assert freshness.is_expired(_now() + timedelta(days=1), _now()) is False
