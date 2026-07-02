"""Module 6 — Learning Engine unit tests (no DB; mocked signals + LLM)."""

from __future__ import annotations

from datetime import UTC, datetime, timedelta
from types import SimpleNamespace

import pytest
from pydantic import ValidationError

from aicmo.modules.decision_engine.schemas import DecisionSignals
from aicmo.modules.learning import feedback, synthesis
from aicmo.modules.learning.insights_prompts import (
    SYSTEM_PROMPT,
    build_synthesis_prompt,
)
from aicmo.modules.learning.insights_schemas import (
    LearningInsightDraft,
    SynthesisOutput,
)


# --------------------------------------------------------------------------
#  Fakes
# --------------------------------------------------------------------------
class _FakeScalars:
    def __init__(self, rows):
        self._rows = list(rows)

    def __iter__(self):
        return iter(self._rows)

    def all(self):
        return list(self._rows)


class _FakeResult:
    def __init__(self, rows):
        self._rows = rows

    def scalars(self):
        return _FakeScalars(self._rows)


class _FakeSession:
    """Minimal AsyncSession stand-in. execute() always yields no rows, which is
    all the 'not enough evidence' path needs."""

    def __init__(self):
        self.added = []
        self.committed = False

    async def execute(self, _stmt):
        return _FakeResult([])

    def add(self, obj):
        self.added.append(obj)

    async def commit(self):
        self.committed = True

    async def flush(self):
        pass


_TENANT = SimpleNamespace(
    user_id="user-1",
    organization_id="org-1",
    brand_id="brand-1",
)


def _insight_row(**over):
    base = dict(
        category="channel",
        observation="Instagram brings cheaper leads than email.",
        recommendation="Shift one email slot to an Instagram reel.",
        confidence=72,
        direction="positive",
        affected_modules=["strategy", "decision"],
        expires_at=None,
    )
    base.update(over)
    return SimpleNamespace(**base)


# --------------------------------------------------------------------------
#  Prompts
# --------------------------------------------------------------------------
def test_system_prompt_forbids_fabrication_and_demands_honesty():
    assert "do NOT invent" in SYSTEM_PROMPT
    assert "return ZERO insights" in SYSTEM_PROMPT


def test_build_synthesis_prompt_includes_real_evidence():
    prompt = build_synthesis_prompt(
        business="Brew & Bloom",
        industry="Cafe",
        blocks=["## Leads\nTotal leads 42; conversion 3.5%."],
        )
    assert "Brew & Bloom" in prompt
    assert "42" in prompt


# --------------------------------------------------------------------------
#  Structured-output schema
# --------------------------------------------------------------------------
def test_draft_confidence_bounds():
    with pytest.raises(ValidationError):
        LearningInsightDraft(
            category="channel",
            observation="x",
            evidence=["e"],
            recommendation="r",
            expected_result="+2 to +5 leads",
            confidence=200,
        )


def test_draft_rejects_bad_affected_module():
    with pytest.raises(ValidationError):
        LearningInsightDraft(
            category="channel",
            observation="x",
            evidence=["e"],
            recommendation="r",
            expected_result="range",
            confidence=60,
            affected_modules=["not_a_module"],
        )


def test_synthesis_output_empty_is_valid():
    out = SynthesisOutput(insights=[], data_sufficiency="too thin")
    assert out.insights == []


# --------------------------------------------------------------------------
#  Feedback render block (what the reasoning modules inherit)
# --------------------------------------------------------------------------
def test_render_block_empty_states_no_history_never_fabricates():
    block = feedback.render_insights_block([])
    assert "none yet" in block
    assert "Do not assume" in block


def test_render_block_marks_positive_and_negative():
    rows = [
        _insight_row(direction="positive", observation="Reels win"),
        _insight_row(
            direction="negative",
            category="failed_strategy",
            observation="Paid search wasted budget",
        ),
    ]
    block = feedback.render_insights_block(rows)
    assert "✓" in block and "✗" in block
    assert "Reels win" in block
    assert "do NOT repeat" in block


# --------------------------------------------------------------------------
#  active_insights_for_module — routing + expiry filter (in-Python)
# --------------------------------------------------------------------------
@pytest.mark.asyncio
async def test_active_insights_filters_by_module_and_expiry(monkeypatch):
    now = datetime.now(UTC)
    rows = [
        _insight_row(affected_modules=["strategy"], observation="keep-strategy"),
        _insight_row(affected_modules=["planner"], observation="wrong-module"),
        _insight_row(
            affected_modules=["strategy"],
            observation="expired-one",
            expires_at=now - timedelta(days=1),
        ),
    ]

    async def fake_execute(_stmt):
        return _FakeResult(rows)

    session = _FakeSession()
    monkeypatch.setattr(session, "execute", fake_execute)

    out = await feedback.active_insights_for_module(
        session, brand_id="brand-1", module="strategy"
    )
    observations = [r.observation for r in out]
    assert "keep-strategy" in observations
    assert "wrong-module" not in observations  # different module
    assert "expired-one" not in observations  # past expires_at


# --------------------------------------------------------------------------
#  synthesize() — the honest "Not enough historical evidence." path
# --------------------------------------------------------------------------
@pytest.mark.asyncio
async def test_synthesize_returns_not_enough_without_calling_llm(monkeypatch):
    # Empty workspace: profile exists but zero real history.
    empty_sig = DecisionSignals(
        has_profile=True, business_name="New Co", industry="Bakery"
    )

    async def fake_gather(_session, *, tenant):
        return empty_sig

    async def fake_events(*a, **k):
        return []

    async def fake_memory(*a, **k):
        return []

    async def fake_strategies(*a, **k):
        return SimpleNamespace(items=[])

    monkeypatch.setattr(synthesis, "gather_signals", fake_gather)
    monkeypatch.setattr(
        synthesis.learning_service, "top_learning_events_for_context", fake_events
    )
    monkeypatch.setattr(synthesis.advisor_memory, "load_brand_memory", fake_memory)
    monkeypatch.setattr(
        "aicmo.modules.strategist.service.list_strategies", fake_strategies
    )

    def _boom():
        raise AssertionError("LLM must NOT be called with no history")

    monkeypatch.setattr(synthesis, "get_llm_router", _boom)

    result = await synthesis.synthesize(_FakeSession(), tenant=_TENANT)

    assert result.insights_created == 0
    assert result.note == "Not enough historical evidence."


@pytest.mark.asyncio
async def test_synthesize_persists_only_confident_evidence_backed(monkeypatch):
    # Non-empty history so we reach the LLM.
    sig = DecisionSignals(
        has_profile=True,
        business_name="Brew Co",
        industry="Cafe",
        total_leads=40,
        published_posts=12,
        winning_patterns=["Reels beat static 2x"],
    )

    async def fake_gather(_session, *, tenant):
        return sig

    async def fake_events(*a, **k):
        return []

    async def fake_memory(*a, **k):
        return []

    async def fake_strategies(*a, **k):
        return SimpleNamespace(items=[])

    monkeypatch.setattr(synthesis, "gather_signals", fake_gather)
    monkeypatch.setattr(
        synthesis.learning_service, "top_learning_events_for_context", fake_events
    )
    monkeypatch.setattr(synthesis.advisor_memory, "load_brand_memory", fake_memory)
    monkeypatch.setattr(
        "aicmo.modules.strategist.service.list_strategies", fake_strategies
    )

    output = SynthesisOutput(
        insights=[
            LearningInsightDraft(
                category="channel",
                observation="Reels convert best",
                evidence=["Reels beat static 2x"],
                recommendation="Prioritise reels",
                expected_result="+3 to +6 leads",
                confidence=70,
                affected_modules=["strategy"],
            ),
            # Below the trust floor — must be dropped.
            LearningInsightDraft(
                category="budget",
                observation="guess",
                evidence=["thin"],
                recommendation="maybe",
                expected_result="unclear",
                confidence=20,
            ),
            # No evidence — must be dropped.
            LearningInsightDraft(
                category="seasonal",
                observation="hunch",
                evidence=[],
                recommendation="maybe",
                expected_result="unclear",
                confidence=90,
            ),
        ],
        data_sufficiency="Moderate history.",
    )
    fake_router = SimpleNamespace(
        generate=_async_return(SimpleNamespace(data=output))
    )
    monkeypatch.setattr(synthesis, "get_llm_router", lambda: fake_router)

    session = _FakeSession()
    result = await synthesis.synthesize(session, tenant=_TENANT)

    assert result.insights_created == 1  # only the confident, evidence-backed one
    assert len(session.added) == 1
    persisted = session.added[0]
    assert persisted.category == "channel"
    assert persisted.confidence == 70


def _async_return(value):
    async def _inner(*a, **k):
        return value

    return _inner
