"""Advisor dedupe + fingerprint tests."""

from __future__ import annotations

import uuid
from datetime import UTC, datetime, timedelta
from types import SimpleNamespace

from aicmo.modules.advisor.dedupe import (
    fingerprint_for_hero,
    fingerprint_for_opportunity,
    impact_label,
    should_suppress,
)
from aicmo.modules.opportunities.schemas import GeneratorHint


def test_fingerprint_stable_for_same_action():
    gen = GeneratorHint(
        target="content",
        format="social_post",
        platform="Instagram",
        goal="Drive engagement",
    )
    a = fingerprint_for_opportunity(
        kind="content", generator=gen, recommended_action="Post a reel"
    )
    b = fingerprint_for_opportunity(
        kind="content", generator=gen, recommended_action="Post a reel"
    )
    assert a == b


def test_suppresses_recently_completed():
    gen = GeneratorHint(
        target="content",
        format="social_post",
        platform="Instagram",
        goal="Drive engagement",
    )
    fp = fingerprint_for_opportunity(
        kind="content", generator=gen, recommended_action="Ship one post"
    )
    row = SimpleNamespace(
        source_fingerprint=fp,
        status="completed",
        completed_at=datetime.now(UTC) - timedelta(days=7),
        skipped_at=None,
    )
    assert should_suppress(fp, [row]) is True


def test_does_not_suppress_old_completed():
    gen = GeneratorHint(
        target="content",
        format="social_post",
        platform="Instagram",
        goal="Drive engagement",
    )
    fp = fingerprint_for_opportunity(
        kind="content", generator=gen, recommended_action="Ship one post"
    )
    row = SimpleNamespace(
        source_fingerprint=fp,
        status="completed",
        completed_at=datetime.now(UTC) - timedelta(days=120),
        skipped_at=None,
    )
    assert should_suppress(fp, [row]) is False


def test_hero_fingerprint():
    assert fingerprint_for_hero("Launch weekend offer") != fingerprint_for_hero(
        "Other action"
    )


def test_impact_label_bands():
    assert impact_label(80) == "High"
    assert impact_label(50) == "Medium"
    assert impact_label(10) == "Low"
