"""Phase 8 — AI Marketing Health scoring.

`brand_completeness` and `_status` are pure, so they're pinned directly.
`compute_health` is exercised with the DB counts stubbed, which keeps these
hermetic while still proving the plain-language contract: every score
carries an explanation, a why, and a recommendation, and the headline points
at the weakest area.
"""

from __future__ import annotations

import types
import uuid

import pytest

from aicmo.modules.advisor import health as health_mod
from aicmo.modules.advisor.health import _status, brand_completeness, compute_health


def _profile(**over) -> object:
    base = dict(
        brand_id=uuid.uuid4(),
        business_name="Bella's Bakery",
        website="https://bellasbakery.in",
        industry="Bakery",
        target_audience="Local families",
        brand_tone="warm",
        writing_style="Short and sensory.",
        pricing="From ₹120",
        products=["Sourdough"],
        services=["Catering"],
        unique_selling_points=["Baked same day"],
        competitors=["Other bakery"],
        goals=["More walk-ins"],
        keywords=["sourdough"],
        brand_colors=["#8B4513"],
        fonts=["Playfair"],
        brand_rules=["Never say cheap"],
    )
    base.update(over)
    return types.SimpleNamespace(**base)


class TestStatus:
    def test_bands(self) -> None:
        assert _status(85) == "good"
        assert _status(70) == "good"
        assert _status(55) == "watch"
        assert _status(40) == "watch"
        assert _status(10) == "bad"


class TestBrandCompleteness:
    def test_fully_filled_is_100(self) -> None:
        assert brand_completeness(_profile()) == 100

    def test_empty_is_0(self) -> None:
        empty = _profile(
            business_name="",
            website=None,
            industry="",
            target_audience="",
            brand_tone="",
            writing_style=None,
            pricing=None,
            products=[],
            services=[],
            unique_selling_points=[],
            competitors=[],
            goals=[],
            keywords=[],
            brand_colors=[],
            fonts=[],
            brand_rules=[],
        )
        assert brand_completeness(empty) == 0

    def test_partial_is_proportional(self) -> None:
        half = _profile(
            products=[], services=[], unique_selling_points=[], competitors=[],
            goals=[], keywords=[], brand_colors=[], fonts=[],
        )
        assert half == half  # sanity
        assert brand_completeness(half) == 50


def _stub_counts(monkeypatch, *, content=0, leads=0, ads=0, pages=0, connections=0):
    from aicmo.modules.ads.models import GeneratedAd
    from aicmo.modules.content.models import GeneratedContent
    from aicmo.modules.integrations.models import IntegrationConnection
    from aicmo.modules.landing_pages.models import LandingPage
    from aicmo.modules.leads.models import Lead

    mapping = {
        GeneratedContent: content,
        Lead: leads,
        GeneratedAd: ads,
        LandingPage: pages,
        IntegrationConnection: connections,
    }

    async def _count(session, model, brand_id, since=None):
        return mapping[model]

    monkeypatch.setattr(health_mod, "_count", _count)


class TestComputeHealth:
    @pytest.mark.asyncio
    async def test_brand_new_business_scores_honestly_low(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        _stub_counts(monkeypatch)
        out = await compute_health(None, profile=_profile())
        # Brand Brain is full, but nothing has been *done* yet.
        assert out.overall < 70
        by_key = {s.key: s for s in out.scores}
        assert by_key["brand"].score == 100
        assert by_key["content"].score == 0
        assert by_key["leads"].score == 0
        assert by_key["content"].status == "bad"

    @pytest.mark.asyncio
    async def test_active_business_scores_well(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        _stub_counts(
            monkeypatch, content=12, leads=10, ads=3, pages=2, connections=3
        )
        out = await compute_health(None, profile=_profile())
        assert out.overall >= 70
        assert out.overall_status == "good"
        by_key = {s.key: s for s in out.scores}
        assert by_key["content"].score == 100
        assert by_key["leads"].score == 100
        assert by_key["social"].score == 100

    @pytest.mark.asyncio
    async def test_every_score_carries_the_constitution_contract(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        _stub_counts(monkeypatch, content=4, leads=1)
        out = await compute_health(None, profile=_profile())
        assert out.scores, "expected health scores"
        for s in out.scores:
            assert s.explanation.strip(), f"{s.key} missing explanation"
            assert s.why.strip(), f"{s.key} missing why"
            assert s.recommendation.strip(), f"{s.key} missing recommendation"
            assert 0 <= s.score <= 100
            assert s.status in ("good", "watch", "bad")

    @pytest.mark.asyncio
    async def test_headline_points_at_the_weakest_area(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        # Everything decent except leads → focus should land on leads.
        _stub_counts(
            monkeypatch, content=12, leads=0, ads=3, pages=2, connections=3
        )
        out = await compute_health(None, profile=_profile())
        assert out.focus_key == "leads"

    @pytest.mark.asyncio
    async def test_counts_are_never_over_100(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        _stub_counts(
            monkeypatch, content=999, leads=999, ads=99, pages=99, connections=99
        )
        out = await compute_health(None, profile=_profile())
        for s in out.scores:
            assert s.score <= 100, f"{s.key} exceeded 100"
        assert out.overall <= 100
