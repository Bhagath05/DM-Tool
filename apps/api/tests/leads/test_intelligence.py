"""Lead Intelligence — pure-function unit tests.

Covers the parts of `modules/leads/intelligence.py` that don't require
Postgres. The composer + LLM call are integration concerns that exercise
end-to-end manually; here we lock in:

- The prescorer ranks the right kinds of leads higher (hot + recent +
  phone + paid campaign > old + cold + anonymous).
- The deterministic fallback always satisfies the Constitution contract.
- The assembler:
    * drops priorities that reference invalid lead_index values
    * promotes rank-1 → 'focus' when no LLM priority was 'focus'
    * demotes second-'focus' to 'hot' when the LLM mis-orders
- Zero-state report renders cleanly without an LLM call.

Why no Postgres: the rest of the repo's test harness is pure-function
(see conftest.py). The LLM and SQL paths are exercised in dev + staging
and pinned by the schemas refusing invalid responses.
"""

from __future__ import annotations

import uuid
from datetime import UTC, datetime, timedelta
from types import SimpleNamespace

import pytest

from aicmo.modules.leads.intelligence import (
    MAX_PRIORITIES,
    _assemble_report,
    _bucket_from_score,
    _fallback_hero,
    _fallback_narrative,
    _format_leads_block,
    _prescore_lead,
    _zero_state_report,
)
from aicmo.modules.leads.schemas import (
    LeadCountsSnapshot,
    LeadHeroRecommendation,
    LeadIntelligenceReport,
    _LeadIntelligenceNarrative,
    _NarrativeLeadPriority,
)

# ---------------------------------------------------------------------
#  Helpers
# ---------------------------------------------------------------------


NOW = datetime(2026, 6, 2, 12, 0, 0, tzinfo=UTC)


def make_lead(
    *,
    lead_id: uuid.UUID | None = None,
    email: str = "person@example.com",
    name: str | None = "Alex Doe",
    company: str | None = None,
    phone: str | None = None,
    message: str | None = None,
    status: str = "new",
    age_hours: int = 12,
    utm_campaign: str | None = None,
    utm_source: str | None = None,
    utm_medium: str | None = None,
    source_asset_type: str | None = None,
):
    """Lightweight fake — only the attributes the intelligence module reads.

    Using SimpleNamespace keeps tests free of SQLAlchemy session plumbing.
    """
    return SimpleNamespace(
        id=lead_id or uuid.uuid4(),
        email=email,
        name=name,
        company=company,
        phone=phone,
        message=message,
        status=status,
        created_at=NOW - timedelta(hours=age_hours),
        utm_campaign=utm_campaign,
        utm_source=utm_source,
        utm_medium=utm_medium,
        source_asset_type=source_asset_type,
    )


def empty_counts(total: int = 0) -> LeadCountsSnapshot:
    return LeadCountsSnapshot(
        total=total,
        new_count=total,
        hot_count=0,
        last_7d=total,
        last_24h=total,
    )


# ---------------------------------------------------------------------
#  Prescorer
# ---------------------------------------------------------------------


class TestPrescorer:
    def test_hot_recent_phone_paid_beats_cold_old_anon(self) -> None:
        gold = make_lead(
            status="hot",
            age_hours=12,
            phone="+1234567890",
            utm_campaign="june-launch",
            company="Acme Co",
        )
        junk = make_lead(
            status="cold",
            age_hours=24 * 30,
            phone=None,
            utm_campaign=None,
        )
        assert _prescore_lead(gold, now=NOW) > _prescore_lead(junk, now=NOW)

    def test_phone_adds_signal(self) -> None:
        with_phone = make_lead(phone="+1234567890")
        without_phone = make_lead(phone=None)
        assert _prescore_lead(with_phone, now=NOW) > _prescore_lead(without_phone, now=NOW)

    def test_recent_beats_old_at_same_status(self) -> None:
        fresh = make_lead(age_hours=6)
        stale = make_lead(age_hours=24 * 10)
        assert _prescore_lead(fresh, now=NOW) > _prescore_lead(stale, now=NOW)

    def test_score_is_bounded(self) -> None:
        maxed = make_lead(
            status="hot",
            age_hours=1,
            phone="+1",
            message="A real intent message that's clearly longer than 20 chars.",
            utm_campaign="x",
            company="y",
        )
        assert 0 <= _prescore_lead(maxed, now=NOW) <= 100

    def test_long_message_signals_engagement(self) -> None:
        with_msg = make_lead(message="I'd love a quote on the premium plan for our team.")
        no_msg = make_lead(message=None)
        assert _prescore_lead(with_msg, now=NOW) > _prescore_lead(no_msg, now=NOW)


# ---------------------------------------------------------------------
#  Bucket mapping
# ---------------------------------------------------------------------


class TestBucketFromScore:
    @pytest.mark.parametrize(
        "score, expected",
        [
            (100, "focus"),
            (70, "focus"),
            (69, "hot"),
            (50, "hot"),
            (49, "warm"),
            (30, "warm"),
            (29, "cold"),
            (0, "cold"),
        ],
    )
    def test_bands(self, score: int, expected: str) -> None:
        assert _bucket_from_score(score) == expected


# ---------------------------------------------------------------------
#  Leads block formatter
# ---------------------------------------------------------------------


class TestLeadsBlock:
    def test_empty_renders_placeholder(self) -> None:
        assert "(no candidate leads" in _format_leads_block([], now=NOW)

    def test_indices_are_one_based(self) -> None:
        block = _format_leads_block(
            [make_lead(email="a@x.com"), make_lead(email="b@x.com")], now=NOW
        )
        assert block.splitlines()[0].startswith("1. ")
        assert block.splitlines()[1].startswith("2. ")

    def test_attribution_appears_when_present(self) -> None:
        block = _format_leads_block(
            [make_lead(utm_campaign="launch", utm_source="instagram")], now=NOW
        )
        assert "campaign=launch" in block
        assert "source=instagram" in block

    def test_phone_signal_appears(self) -> None:
        block = _format_leads_block([make_lead(phone="+1234567890")], now=NOW)
        assert "has phone" in block

    def test_long_message_truncated(self) -> None:
        long_msg = "x" * 500
        block = _format_leads_block([make_lead(message=long_msg)], now=NOW)
        # truncation marker present, full 500 chars not in block
        assert "…" in block
        assert "x" * 500 not in block


# ---------------------------------------------------------------------
#  Fallback narrative (LLM unavailable path)
# ---------------------------------------------------------------------


class TestFallbackNarrative:
    """The fallback MUST satisfy the Constitution contract for every
    priority. If a single field is missing, Pydantic refuses construction
    of the narrative — these tests pin that we always pass."""

    def test_empty_inbox_returns_hero_only(self) -> None:
        composed = {
            "counts": empty_counts(total=0),
            "candidates": [],
            "prescores": [],
        }
        narrative = _fallback_narrative(composed)
        assert isinstance(narrative, _LeadIntelligenceNarrative)
        assert narrative.priorities == []
        assert narrative.hero_recommendation.confidence >= 0
        assert narrative.hero_recommendation.confidence <= 100
        # zero-state hero pivots to "get your first lead"
        assert "page" in narrative.hero_recommendation.recommendation.lower() or \
               "share" in narrative.hero_recommendation.recommendation.lower()

    def test_with_candidates_fills_every_required_field(self) -> None:
        leads = [
            make_lead(status="hot", phone="+1", age_hours=6, utm_campaign="paid"),
            make_lead(status="new", age_hours=20),
            make_lead(status="cold", age_hours=24 * 14),
        ]
        prescores = [_prescore_lead(ld, now=NOW) for ld in leads]
        composed = {
            "counts": LeadCountsSnapshot(total=3, new_count=1, hot_count=1, last_7d=2, last_24h=1),
            "candidates": leads,
            "prescores": prescores,
        }
        narrative = _fallback_narrative(composed)
        assert len(narrative.priorities) >= 1
        # Constitution contract — every priority has every required field
        for p in narrative.priorities:
            assert p.why_now and len(p.why_now) >= 10
            assert p.recommended_action and len(p.recommended_action) >= 5
            assert p.expected_result and len(p.expected_result) >= 5
            assert 0 <= p.confidence <= 100
            assert p.reason and 5 <= len(p.reason) <= 200
            assert p.cta_label and 2 <= len(p.cta_label) <= 24
            assert p.impact_category in ("revenue", "lead", "customer", "time", "cost")
            assert p.estimated_value_band in ("high", "medium", "low", "unknown")
            assert p.priority in ("focus", "hot", "warm", "cold")

    def test_only_one_focus_in_fallback(self) -> None:
        leads = [
            make_lead(status="hot", phone="+1", age_hours=6, utm_campaign="paid"),
            make_lead(status="hot", phone="+1", age_hours=6, utm_campaign="paid"),
        ]
        prescores = [_prescore_lead(ld, now=NOW) for ld in leads]
        composed = {
            "counts": LeadCountsSnapshot(total=2, new_count=0, hot_count=2, last_7d=2, last_24h=2),
            "candidates": leads,
            "prescores": prescores,
        }
        narrative = _fallback_narrative(composed)
        focus_count = sum(1 for p in narrative.priorities if p.priority == "focus")
        assert focus_count == 1

    def test_caps_at_max_priorities(self) -> None:
        leads = [
            make_lead(status="hot", phone="+1", age_hours=6) for _ in range(MAX_PRIORITIES + 3)
        ]
        prescores = [_prescore_lead(ld, now=NOW) for ld in leads]
        composed = {
            "counts": LeadCountsSnapshot(
                total=len(leads),
                new_count=0,
                hot_count=len(leads),
                last_7d=len(leads),
                last_24h=len(leads),
            ),
            "candidates": leads,
            "prescores": prescores,
        }
        narrative = _fallback_narrative(composed)
        assert len(narrative.priorities) <= MAX_PRIORITIES


class TestFallbackHero:
    def test_zero_state(self) -> None:
        hero = _fallback_hero(empty_counts(total=0))
        assert isinstance(hero, LeadHeroRecommendation)
        assert "empty" in hero.what_is_happening.lower()

    def test_fresh_24h_signal(self) -> None:
        counts = LeadCountsSnapshot(
            total=5, new_count=5, hot_count=0, last_7d=5, last_24h=2
        )
        hero = _fallback_hero(counts)
        assert "24" in hero.what_is_happening or "today" in hero.recommendation.lower() or "fresh" in hero.what_is_happening.lower()
        assert hero.impact_category == "revenue"

    def test_hot_no_fresh(self) -> None:
        counts = LeadCountsSnapshot(
            total=5, new_count=0, hot_count=3, last_7d=5, last_24h=0
        )
        hero = _fallback_hero(counts)
        assert "hot" in hero.what_is_happening.lower()

    def test_stale_inbox(self) -> None:
        counts = LeadCountsSnapshot(
            total=8, new_count=0, hot_count=0, last_7d=0, last_24h=0
        )
        hero = _fallback_hero(counts)
        assert hero.confidence < 80  # not a high-conviction call


# ---------------------------------------------------------------------
#  Assembler — resolves LLM indices → real leads, enforces single 'focus'
# ---------------------------------------------------------------------


def make_narrative_priority(
    *,
    lead_index: int = 1,
    priority: str = "hot",
    why_now: str = "Recent submission worth a quick reply.",
    recommended_action: str = "Reply within 24 hours.",
    expected_result: str = "Likely a reply within 48h.",
    confidence: int = 65,
    reason: str = "Recency + new status.",
    impact_category: str = "revenue",
    estimated_value_band: str = "medium",
    cta_label: str = "Reply today",
) -> _NarrativeLeadPriority:
    return _NarrativeLeadPriority(
        lead_index=lead_index,
        priority=priority,  # type: ignore[arg-type]
        why_now=why_now,
        recommended_action=recommended_action,
        expected_result=expected_result,
        confidence=confidence,
        reason=reason,
        impact_category=impact_category,  # type: ignore[arg-type]
        estimated_value_band=estimated_value_band,  # type: ignore[arg-type]
        cta_label=cta_label,
    )


def make_valid_hero() -> LeadHeroRecommendation:
    return LeadHeroRecommendation(
        what_is_happening="You have leads to act on right now.",
        impact_category="revenue",
        recommendation="Reply to the freshest leads today.",
        expected_result="1-2 conversations booked within 48 hours.",
        confidence=70,
        reason="Based on fresh inbox signal.",
    )


class TestAssembler:
    def _composed_with(self, leads):
        return {
            "counts": LeadCountsSnapshot(
                total=len(leads),
                new_count=len(leads),
                hot_count=0,
                last_7d=len(leads),
                last_24h=len(leads),
            ),
            "candidates": leads,
            "signals": ["test signal"],
            "prescores": [_prescore_lead(ld, now=NOW) for ld in leads],
        }

    def test_resolves_indices_to_real_leads(self) -> None:
        leads = [make_lead(email="first@x.com"), make_lead(email="second@x.com")]
        narrative = _LeadIntelligenceNarrative(
            headline="Two leads to work through this week.",
            hero_recommendation=make_valid_hero(),
            priorities=[
                make_narrative_priority(lead_index=2, priority="focus"),
                make_narrative_priority(lead_index=1, priority="hot"),
            ],
            skip_for_now=[],
        )
        report = _assemble_report(narrative=narrative, composed=self._composed_with(leads))
        assert isinstance(report, LeadIntelligenceReport)
        assert len(report.priorities) == 2
        assert report.priorities[0].email == "second@x.com"
        assert report.priorities[0].rank == 1
        assert report.priorities[1].email == "first@x.com"
        assert report.priorities[1].rank == 2

    def test_drops_priorities_with_invalid_index(self) -> None:
        leads = [make_lead(email="only@x.com")]
        narrative = _LeadIntelligenceNarrative(
            headline="One lead.",
            hero_recommendation=make_valid_hero(),
            priorities=[
                make_narrative_priority(lead_index=99, priority="focus"),  # hallucination
                make_narrative_priority(lead_index=1, priority="hot"),
            ],
            skip_for_now=[],
        )
        report = _assemble_report(narrative=narrative, composed=self._composed_with(leads))
        assert len(report.priorities) == 1
        assert report.priorities[0].email == "only@x.com"
        # Promoted to focus because original focus was dropped
        assert report.priorities[0].priority == "focus"

    def test_demotes_second_focus_to_hot(self) -> None:
        leads = [
            make_lead(email="a@x.com"),
            make_lead(email="b@x.com"),
        ]
        narrative = _LeadIntelligenceNarrative(
            headline="Two leads.",
            hero_recommendation=make_valid_hero(),
            priorities=[
                make_narrative_priority(lead_index=1, priority="focus"),
                make_narrative_priority(lead_index=2, priority="focus"),
            ],
            skip_for_now=[],
        )
        report = _assemble_report(narrative=narrative, composed=self._composed_with(leads))
        focus_count = sum(1 for p in report.priorities if p.priority == "focus")
        assert focus_count == 1
        assert report.priorities[0].priority == "focus"
        assert report.priorities[1].priority == "hot"

    def test_caps_at_max_priorities(self) -> None:
        leads = [make_lead(email=f"{i}@x.com") for i in range(MAX_PRIORITIES + 3)]
        priorities = [
            make_narrative_priority(lead_index=i + 1, priority="hot")
            for i in range(MAX_PRIORITIES + 3)
        ]
        narrative = _LeadIntelligenceNarrative(
            headline="Many leads.",
            hero_recommendation=make_valid_hero(),
            priorities=priorities,
            skip_for_now=[],
        )
        report = _assemble_report(narrative=narrative, composed=self._composed_with(leads))
        assert len(report.priorities) == MAX_PRIORITIES

    def test_carries_signals_and_counts(self) -> None:
        leads = [make_lead()]
        narrative = _LeadIntelligenceNarrative(
            headline="Just one lead in the inbox.",
            hero_recommendation=make_valid_hero(),
            priorities=[],
            skip_for_now=["Don't do this."],
        )
        report = _assemble_report(narrative=narrative, composed=self._composed_with(leads))
        assert report.signals_used == ["test signal"]
        assert report.counts.total == 1
        assert report.skip_for_now == ["Don't do this."]
        # Empty priorities is OK — Constitution allows the hero to stand alone.
        assert report.priorities == []


# ---------------------------------------------------------------------
#  Zero-state — skips the LLM entirely when inbox is empty
# ---------------------------------------------------------------------


class TestZeroState:
    def test_no_priorities(self) -> None:
        composed = {
            "counts": empty_counts(total=0),
            "signals": ["Inbox is empty — pre-traction."],
        }
        report = _zero_state_report(composed)
        assert report.priorities == []
        assert report.counts.total == 0
        assert "empty" in report.headline.lower() or "first" in report.headline.lower()

    def test_carries_skip_advice(self) -> None:
        composed = {"counts": empty_counts(total=0), "signals": []}
        report = _zero_state_report(composed)
        # Should warn the founder off buying lists or similar anti-patterns
        assert len(report.skip_for_now) >= 1
