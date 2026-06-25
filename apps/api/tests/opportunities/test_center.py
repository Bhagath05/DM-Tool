"""Opportunity Center — pure-function unit tests.

Covers the parts of `modules/opportunities/center.py` that don't need
Postgres (composer + LLM are integration concerns that exercise
end-to-end in dev):

- `derive_opportunity_id` is deterministic + collision-resistant
- `_assemble_report`:
    * drops opportunities that landed in the wrong bucket
    * dedupes opportunities with the same derived id
    * caps at MAX_CONTENT_OPPS / MAX_AD_OPPS
- Deterministic fallback always satisfies the Constitution contract
  (Pydantic refuses to construct the narrative otherwise)
- Zero-state fallback recommends getting the first lead in, never paid
  ads, and includes "skip paid" guard
- Trending-topic + winning-channel signals appear in the fallback hero
- `_detect_winning_platform` falls back through summary → preferred → 'Instagram'
"""

from __future__ import annotations

import uuid

import pytest
from pydantic import ValidationError

from aicmo.modules.opportunities.center import (
    MAX_AD_OPPS,
    MAX_CONTENT_OPPS,
    _assemble_report,
    _detect_winning_platform,
    _fallback_hero,
    _fallback_narrative,
    _fallback_zero_state,
)
from aicmo.modules.opportunities.schemas import (
    GeneratorHint,
    Opportunity,
    OpportunityCenterReport,
    OpportunityHeroRecommendation,
    _NarrativeOpportunity,
    _OpportunityCenterNarrative,
    derive_opportunity_id,
)

# ---------------------------------------------------------------------
#  Tiny fakes — keep schemas valid without a real BusinessProfile row.
# ---------------------------------------------------------------------


class FakeProfile:
    """SimpleNamespace would work but we want predictable attribute names.

    Only the attributes the fallback path reads are populated.
    """

    def __init__(
        self,
        *,
        preferred_platforms: list[str] | None = None,
        primary_goal_text: str | None = None,
    ):
        self.preferred_platforms = preferred_platforms or []
        self.primary_goal_text = primary_goal_text


def empty_composed(
    *,
    counts_total: int = 0,
    trending_topics: list[str] | None = None,
    top_source: str | None = None,
    top_asset: str | None = None,
    profile: FakeProfile | None = None,
) -> dict:
    return {
        "profile": profile or FakeProfile(preferred_platforms=["Instagram"]),
        "counts": {
            "total": counts_total,
            "hot": 0,
            "last_7d": counts_total,
            "last_24h": 0,
        },
        "counts_block": "",
        "top_source_summary": top_source,
        "top_asset_summary": top_asset,
        "trends_summary": " · ".join(trending_topics or []),
        "trending_topics": trending_topics or [],
        "recent_content_summary": None,
        "recent_ads_summary": None,
        "signals": ["test signal"],
        "analysis": None,
    }


def make_content_hint(**overrides) -> GeneratorHint:
    base = {
        "target": "content",
        "format": "social_post",
        "platform": "Instagram",
        "goal": "Drive engagement",
        "objective": None,
    }
    base.update(overrides)
    return GeneratorHint(**base)


def make_ad_hint(**overrides) -> GeneratorHint:
    base = {
        "target": "ad",
        "format": "meta",
        "platform": None,
        "goal": "Drive conversions / sales",
        "objective": "leads",
    }
    base.update(overrides)
    return GeneratorHint(**base)


def make_narrative_opp(
    *,
    kind: str = "content",
    headline: str = "Ship one Instagram reel today",
    recommended_action: str = "Publish one Instagram reel before Friday.",
    generator: GeneratorHint | None = None,
) -> _NarrativeOpportunity:
    return _NarrativeOpportunity(
        kind=kind,  # type: ignore[arg-type]
        headline=headline,
        what_is_happening="One of your channels is producing fresh signal.",
        why_it_matters="Acting on that signal in the next 7 days compounds.",
        recommended_action=recommended_action,
        expected_result="Likely 5-12 new visitors and 1-2 leads.",
        confidence=70,
        reason="Based on the test signal.",
        impact_category="lead",
        evidence=["Test evidence line."],
        generator=generator or (make_content_hint() if kind == "content" else make_ad_hint()),
    )


def make_valid_hero() -> OpportunityHeroRecommendation:
    return OpportunityHeroRecommendation(
        what_is_happening="Test inbox state.",
        impact_category="lead",
        recommendation="Ship one Instagram post pointing at your lead page.",
        expected_result="Likely 5-12 visits and 1-2 leads.",
        confidence=65,
        reason="Test reason for hero.",
    )


# ---------------------------------------------------------------------
#  Deterministic id derivation
# ---------------------------------------------------------------------


class TestDeriveOpportunityId:
    def test_same_inputs_yield_same_id(self) -> None:
        hint = make_content_hint()
        a = derive_opportunity_id(
            kind="content", generator=hint, recommended_action="Publish a reel."
        )
        b = derive_opportunity_id(
            kind="content", generator=hint, recommended_action="Publish a reel."
        )
        assert a == b

    def test_whitespace_and_case_normalised(self) -> None:
        hint = make_content_hint()
        a = derive_opportunity_id(
            kind="content", generator=hint, recommended_action="Publish a Reel."
        )
        b = derive_opportunity_id(
            kind="content", generator=hint, recommended_action="  publish   a   reel.  "
        )
        assert a == b

    def test_different_action_yields_different_id(self) -> None:
        hint = make_content_hint()
        a = derive_opportunity_id(
            kind="content", generator=hint, recommended_action="Publish a reel."
        )
        b = derive_opportunity_id(
            kind="content", generator=hint, recommended_action="Publish a carousel."
        )
        assert a != b

    def test_different_format_yields_different_id(self) -> None:
        a = derive_opportunity_id(
            kind="content",
            generator=make_content_hint(format="social_post"),
            recommended_action="x",
        )
        b = derive_opportunity_id(
            kind="content",
            generator=make_content_hint(format="reel"),
            recommended_action="x",
        )
        assert a != b

    def test_kind_separates_namespace(self) -> None:
        a = derive_opportunity_id(
            kind="content", generator=make_content_hint(), recommended_action="x"
        )
        b = derive_opportunity_id(
            kind="ad", generator=make_ad_hint(), recommended_action="x"
        )
        assert a != b

    def test_returns_uuid(self) -> None:
        result = derive_opportunity_id(
            kind="content",
            generator=make_content_hint(),
            recommended_action="anything",
        )
        assert isinstance(result, uuid.UUID)


# ---------------------------------------------------------------------
#  Assembler
# ---------------------------------------------------------------------


class TestAssembler:
    def _narrative(
        self,
        *,
        content: list[_NarrativeOpportunity] | None = None,
        ad: list[_NarrativeOpportunity] | None = None,
        skip: list[str] | None = None,
    ) -> _OpportunityCenterNarrative:
        return _OpportunityCenterNarrative(
            headline="Test headline at least five chars.",
            hero_recommendation=make_valid_hero(),
            content_opportunities=content or [],
            ad_opportunities=ad or [],
            skip_for_now=skip or [],
        )

    def test_drops_misbucketed_opportunities(self) -> None:
        narrative = self._narrative(
            content=[
                make_narrative_opp(kind="content"),
                make_narrative_opp(
                    kind="ad",  # wrong bucket
                    recommended_action="Run an ad",
                    generator=make_ad_hint(),
                ),
            ]
        )
        report = _assemble_report(narrative=narrative, composed=empty_composed())
        assert len(report.content_opportunities) == 1
        assert all(o.kind == "content" for o in report.content_opportunities)

    def test_dedupes_by_derived_id(self) -> None:
        hint = make_content_hint()
        a = make_narrative_opp(
            kind="content",
            recommended_action="Publish a reel.",
            generator=hint,
        )
        b = make_narrative_opp(
            kind="content",
            recommended_action="publish a reel.",  # same normalised
            generator=hint,
        )
        narrative = self._narrative(content=[a, b])
        report = _assemble_report(narrative=narrative, composed=empty_composed())
        assert len(report.content_opportunities) == 1

    def test_passes_through_exactly_max_content_opps(self) -> None:
        items = [
            make_narrative_opp(
                kind="content",
                recommended_action=f"Action variant {i}",
                generator=make_content_hint(format=("social_post" if i % 2 else "reel")),
            )
            for i in range(MAX_CONTENT_OPPS)
        ]
        narrative = self._narrative(content=items)
        report = _assemble_report(narrative=narrative, composed=empty_composed())
        assert len(report.content_opportunities) == MAX_CONTENT_OPPS

    def test_passes_through_exactly_max_ad_opps(self) -> None:
        items = [
            make_narrative_opp(
                kind="ad",
                recommended_action=f"Run ad {i}",
                generator=make_ad_hint(format=("meta" if i % 2 else "google_search")),
            )
            for i in range(MAX_AD_OPPS)
        ]
        narrative = self._narrative(ad=items)
        report = _assemble_report(narrative=narrative, composed=empty_composed())
        assert len(report.ad_opportunities) == MAX_AD_OPPS

    def test_narrative_schema_rejects_over_max(self) -> None:
        """Defense in depth — narrative schema enforces the cap BEFORE
        the assembler ever sees the data. Belt + braces."""
        too_many_content = [
            make_narrative_opp(
                kind="content",
                recommended_action=f"Action {i}",
                generator=make_content_hint(format=("social_post" if i % 2 else "reel")),
            )
            for i in range(MAX_CONTENT_OPPS + 1)
        ]
        with pytest.raises(ValidationError):
            _OpportunityCenterNarrative(
                headline="Test headline at least five chars.",
                hero_recommendation=make_valid_hero(),
                content_opportunities=too_many_content,
                ad_opportunities=[],
                skip_for_now=[],
            )

    def test_carries_skip_and_signals_through(self) -> None:
        narrative = self._narrative(skip=["Don't do this."])
        report = _assemble_report(
            narrative=narrative, composed=empty_composed()
        )
        assert isinstance(report, OpportunityCenterReport)
        assert report.skip_for_now == ["Don't do this."]
        assert "test signal" in report.signals_used

    def test_assigned_ids_are_valid_uuids(self) -> None:
        narrative = self._narrative(content=[make_narrative_opp()])
        report = _assemble_report(narrative=narrative, composed=empty_composed())
        assert isinstance(report.content_opportunities[0].id, uuid.UUID)


# ---------------------------------------------------------------------
#  Winning-platform detection
# ---------------------------------------------------------------------


class TestDetectWinningPlatform:
    def test_detects_from_summary(self) -> None:
        assert (
            _detect_winning_platform(
                "instagram-launch — 4 leads, 2 hot.",
                FakeProfile(preferred_platforms=["LinkedIn"]),
            )
            == "Instagram"
        )

    def test_falls_back_to_preferred(self) -> None:
        assert (
            _detect_winning_platform(
                None, FakeProfile(preferred_platforms=["LinkedIn", "TikTok"])
            )
            == "LinkedIn"
        )

    def test_final_fallback_instagram(self) -> None:
        assert _detect_winning_platform(None, FakeProfile()) == "Instagram"


# ---------------------------------------------------------------------
#  Fallback narratives (Constitution contract)
# ---------------------------------------------------------------------


class TestFallbackZeroState:
    def test_recommends_first_lead(self) -> None:
        profile = FakeProfile(preferred_platforms=["Instagram"])
        narrative = _fallback_zero_state(profile, trending_topics=[])
        # Hero MUST mention publishing / shipping the first asset
        assert isinstance(narrative.hero_recommendation, OpportunityHeroRecommendation)
        assert "publish" in narrative.hero_recommendation.recommendation.lower()
        # At least one content opportunity
        assert len(narrative.content_opportunities) >= 1
        # Zero state never recommends paid ads
        assert narrative.ad_opportunities == []
        # Guards the founder against premature paid spend
        assert any("paid" in s.lower() for s in narrative.skip_for_now)

    def test_zero_state_adds_trend_opportunity_when_available(self) -> None:
        profile = FakeProfile(preferred_platforms=["LinkedIn"])
        narrative = _fallback_zero_state(profile, trending_topics=["AI agents"])
        # Now there should be 2 content opportunities — base + trend
        assert len(narrative.content_opportunities) >= 2
        assert any(
            "AI agents" in opp.headline for opp in narrative.content_opportunities
        )


class TestFallbackWithTraction:
    def test_includes_ad_when_top_source_present(self) -> None:
        composed = empty_composed(
            counts_total=8,
            top_source="instagram-launch — 4 leads, 2 hot.",
            trending_topics=["coffee guides"],
        )
        narrative = _fallback_narrative(composed)
        assert len(narrative.ad_opportunities) >= 1
        assert narrative.ad_opportunities[0].kind == "ad"

    def test_no_ad_when_no_winning_channel(self) -> None:
        composed = empty_composed(counts_total=8, trending_topics=["something"])
        narrative = _fallback_narrative(composed)
        assert narrative.ad_opportunities == []

    def test_every_field_filled_on_each_opportunity(self) -> None:
        """The Constitution contract holds across the full fallback path."""
        composed = empty_composed(
            counts_total=12,
            top_source="instagram — 5 leads, 1 hot.",
            top_asset="'Promote a launch' (content / reel on Instagram) has driven 4 leads.",
            trending_topics=["specialty coffee guides", "third wave drinks"],
        )
        narrative = _fallback_narrative(composed)

        for opp in (
            *narrative.content_opportunities,
            *narrative.ad_opportunities,
        ):
            assert opp.headline and len(opp.headline) >= 4
            assert opp.what_is_happening and len(opp.what_is_happening) >= 10
            assert opp.why_it_matters and len(opp.why_it_matters) >= 10
            assert opp.recommended_action and len(opp.recommended_action) >= 8
            assert opp.expected_result and len(opp.expected_result) >= 5
            assert 0 <= opp.confidence <= 100
            assert opp.reason and 5 <= len(opp.reason) <= 200
            assert opp.impact_category in {"revenue", "lead", "customer", "time", "cost"}
            assert opp.generator.target in {"content", "ad"}
            assert opp.generator.format
            assert opp.generator.goal


class TestFallbackHero:
    def test_trending_topic_appears(self) -> None:
        hero = _fallback_hero(
            counts={"total": 5, "hot": 1, "last_7d": 3, "last_24h": 1},
            trending_topics=["pricing transparency"],
            top_source_summary=None,
            winning_platform="Instagram",
        )
        assert "pricing transparency" in hero.what_is_happening or "pricing transparency" in hero.recommendation

    def test_top_source_appears_when_no_trend(self) -> None:
        hero = _fallback_hero(
            counts={"total": 5, "hot": 1, "last_7d": 3, "last_24h": 1},
            trending_topics=[],
            top_source_summary="june-launch — 3 leads, 1 hot.",
            winning_platform="LinkedIn",
        )
        assert "june-launch" in hero.what_is_happening

    def test_neutral_when_no_signals(self) -> None:
        hero = _fallback_hero(
            counts={"total": 5, "hot": 0, "last_7d": 0, "last_24h": 0},
            trending_topics=[],
            top_source_summary=None,
            winning_platform="Instagram",
        )
        # Low-conviction → confidence below the "high" band
        assert hero.confidence < 80


# ---------------------------------------------------------------------
#  Full assembled report end-to-end (fallback path, no LLM)
# ---------------------------------------------------------------------


class TestEndToEndFallbackAssembly:
    def test_fallback_produces_valid_report(self) -> None:
        composed = empty_composed(
            counts_total=12,
            top_source="instagram — 5 leads, 1 hot.",
            trending_topics=["coffee guides"],
        )
        narrative = _fallback_narrative(composed)
        report = _assemble_report(narrative=narrative, composed=composed)
        assert isinstance(report, OpportunityCenterReport)
        assert isinstance(report.hero_recommendation, OpportunityHeroRecommendation)
        # At least one content opp, every one with a derived id
        assert len(report.content_opportunities) >= 1
        for opp in report.content_opportunities:
            assert isinstance(opp, Opportunity)
            assert isinstance(opp.id, uuid.UUID)


# ---------------------------------------------------------------------
#  Schema-level contract — refuses invalid opportunities
# ---------------------------------------------------------------------


class TestOpportunityContractEnforcement:
    @pytest.mark.parametrize("field", [
        "headline",
        "what_is_happening",
        "why_it_matters",
        "recommended_action",
        "expected_result",
        "reason",
    ])
    def test_empty_required_string_rejected(self, field: str) -> None:
        valid = {
            "id": uuid.uuid4(),
            "kind": "content",
            "headline": "Real headline",
            "what_is_happening": "Plain-English explanation here.",
            "why_it_matters": "Why this business cares.",
            "recommended_action": "Verb-led action.",
            "expected_result": "Ranged outcome.",
            "confidence": 70,
            "reason": "Cited signal.",
            "impact_category": "lead",
            "evidence": [],
            "generator": make_content_hint(),
        }
        valid[field] = ""
        with pytest.raises(ValidationError):
            Opportunity(**valid)

    def test_confidence_out_of_range_rejected(self) -> None:
        with pytest.raises(ValidationError):
            Opportunity(
                id=uuid.uuid4(),
                kind="content",
                headline="Real headline",
                what_is_happening="Plain-English explanation here.",
                why_it_matters="Why this business cares.",
                recommended_action="Verb-led action.",
                expected_result="Ranged outcome.",
                confidence=150,
                reason="Cited signal.",
                impact_category="lead",
                evidence=[],
                generator=make_content_hint(),
            )
