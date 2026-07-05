"""Phase 6.5 Slice 5 — AI Sales Assistant: grounding gate ("Not enough
evidence"), evidence contract, confidence, subject validation, cross-tenant,
caching. Hermetic — fake session, LLM + audit stubbed. A spy proves the LLM is
NEVER called when evidence is insufficient (no hallucination)."""

from __future__ import annotations

import asyncio
import uuid
from datetime import UTC, datetime, timedelta
from types import SimpleNamespace

import pytest
from fastapi import HTTPException

from aicmo.modules.crm import assistant_service as svc
from aicmo.modules.crm.assistant_models import AIInsight
from aicmo.modules.crm.assistant_schemas import Evidence, SalesInsight
from aicmo.modules.crm.models import Deal, Task
from aicmo.modules.leads.models import Lead

_ORG = uuid.uuid4()
_BRAND = uuid.uuid4()
_TENANT = SimpleNamespace(
    organization_id=_ORG, brand_id=_BRAND, user_id="rep-1", user_uuid=uuid.uuid4()
)


class _Result:
    def __init__(self, one=None):
        self._one = one

    def scalar_one_or_none(self):
        return self._one

    def scalars(self):
        return self

    def all(self):
        return []

    def scalar_one(self):
        return 0


class _Session:
    def __init__(self, store=None, cached=None):
        self._store = store or {}
        self._cached = cached
        self.added: list = []

    async def get(self, _m, i):
        return self._store.get(i)

    async def execute(self, _stmt):
        return _Result(one=self._cached)

    def add(self, o):
        self.added.append(o)

    async def commit(self):
        pass

    async def refresh(self, _o):
        pass


_LLM_CALLS = {"n": 0}


@pytest.fixture(autouse=True)
def _stubs(monkeypatch):
    _LLM_CALLS["n"] = 0

    async def _fake_generate(**_k):
        _LLM_CALLS["n"] += 1
        return SimpleNamespace(data=SalesInsight(
            summary="Warm inbound lead asking about pricing.",
            recommendation="Call within 24h to qualify budget.",
            evidence=[Evidence(source="lead message", detail="asked about pricing")],
            reasoning="Explicit pricing interest + recent inbound signal.",
            confidence=72, affected_records=["lead: Jane"],
            expected_outcome="Could qualify to a deal within a week.",
        ), model="test-model")

    monkeypatch.setattr(svc, "get_llm_router", lambda: SimpleNamespace(generate=_fake_generate))

    async def _noop(*_a, **_k):
        return None

    monkeypatch.setattr(svc, "_audit", _noop)
    monkeypatch.setattr(svc.ai_audit, "record_ai_generation", _noop)


def run(c):
    return asyncio.run(c)


def _lead(**over):
    base = dict(
        id=uuid.uuid4(), organization_id=_ORG, brand_id=_BRAND, email="jane@acme.com",
        name="Jane", company=None, message=None, status="new", utm_source=None,
        tags=[], notes=None,
    )
    base.update(over)
    return Lead(**base)


# ---- subject validation ----
def test_unknown_subject_type_400():
    with pytest.raises(HTTPException) as ei:
        run(svc._own(_Session(), tenant=_TENANT, subject_type="widget", subject_id=uuid.uuid4()))
    assert ei.value.status_code == 400


def test_cross_tenant_subject_404():
    lead = _lead(brand_id=uuid.uuid4())
    with pytest.raises(HTTPException) as ei:
        run(svc._own(_Session({lead.id: lead}), tenant=_TENANT, subject_type="lead", subject_id=lead.id))
    assert ei.value.status_code == 404


def test_invalid_kind_for_subject_400():
    lead = _lead(message="hi", notes="met")
    with pytest.raises(HTTPException) as ei:
        run(svc.generate(_Session({lead.id: lead}), tenant=_TENANT, subject_type="lead",
                         subject_id=lead.id, kind="deal_coaching"))
    assert ei.value.status_code == 400


# ---- grounding gate: NOT ENOUGH EVIDENCE (no LLM) ----
def test_thin_lead_returns_not_enough_evidence_without_llm():
    lead = _lead()  # no message/notes/tags/company/source → 0 signals
    row = run(svc.generate(_Session({lead.id: lead}), tenant=_TENANT,
                           subject_type="lead", subject_id=lead.id))
    assert row.insufficient_evidence is True
    assert row.summary == "Not enough evidence."
    assert row.confidence == 0 and row.recommendation is None
    assert _LLM_CALLS["n"] == 0  # the model was never asked to hallucinate


# ---- evidence contract: sufficient → full insight ----
def test_rich_lead_produces_full_evidence_contract():
    lead = _lead(message="interested in pricing", notes="met at conf", tags=["hot"], status="new")
    row = run(svc.generate(_Session({lead.id: lead}), tenant=_TENANT,
                           subject_type="lead", subject_id=lead.id))
    assert _LLM_CALLS["n"] == 1
    assert row.insufficient_evidence is False
    # every contract field is present + persisted
    assert row.summary and row.recommendation and row.reasoning and row.expected_outcome
    assert row.confidence == 72
    assert row.evidence and row.evidence[0]["source"] == "lead message"
    assert any("lead: Jane" in a for a in row.affected_records)
    # generated_at + expires_at (TTL) set
    assert row.generated_at is not None and row.expires_at is not None
    assert row.expires_at > row.generated_at
    assert row.model == "test-model"


def test_default_kind_for_meeting_and_call():
    meeting = Task(id=uuid.uuid4(), organization_id=_ORG, brand_id=_BRAND, title="Demo",
                   activity_type="meeting", status="open", priority="medium", deal_id=None,
                   description="x", notes=None)
    call = Task(id=uuid.uuid4(), organization_id=_ORG, brand_id=_BRAND, title="Call",
                activity_type="call", status="open", priority="medium", deal_id=None,
                description="x", notes=None)
    assert svc._default_kind("task", meeting) == "meeting_intelligence"
    assert svc._default_kind("task", call) == "call_intelligence"


# ---- caching: fresh cached insight returned without a new LLM call ----
def test_cache_hit_skips_llm():
    lead = _lead(message="hi", notes="met")
    cached = AIInsight(
        id=uuid.uuid4(), organization_id=_ORG, brand_id=_BRAND, subject_type="lead",
        subject_id=lead.id, kind="lead_intelligence", summary="cached", confidence=60,
        insufficient_evidence=False, generated_at=datetime.now(UTC),
        expires_at=datetime.now(UTC) + timedelta(hours=5),
    )
    row = run(svc.generate(_Session({lead.id: lead}, cached=cached), tenant=_TENANT,
                           subject_type="lead", subject_id=lead.id))
    assert row is cached and _LLM_CALLS["n"] == 0


def test_force_regenerates_even_with_cache():
    lead = _lead(message="hi", notes="met", tags=["x"])
    cached = AIInsight(
        id=uuid.uuid4(), organization_id=_ORG, brand_id=_BRAND, subject_type="lead",
        subject_id=lead.id, kind="lead_intelligence", summary="cached", confidence=60,
        insufficient_evidence=False, generated_at=datetime.now(UTC),
        expires_at=datetime.now(UTC) + timedelta(hours=5),
    )
    row = run(svc.generate(_Session({lead.id: lead}, cached=cached), tenant=_TENANT,
                           subject_type="lead", subject_id=lead.id, force=True))
    assert row is not cached and _LLM_CALLS["n"] == 1


# ---- deal subject wiring (uses aggregate queries; smoke the resolve path) ----
def test_deal_subject_resolves_and_gates():
    deal = Deal(id=uuid.uuid4(), organization_id=_ORG, brand_id=_BRAND, pipeline_id=uuid.uuid4(),
                title="Acme", value=1000, currency="USD", status="open", probability=30,
                stage_id=None, created_at=datetime.now(UTC), competitors=[], lost_reason=None)
    # value+status give 1 base signal; counts return 0 in the fake → < min → insufficient.
    row = run(svc.generate(_Session({deal.id: deal}), tenant=_TENANT,
                           subject_type="deal", subject_id=deal.id))
    assert row.subject_type == "deal"
    assert row.insufficient_evidence is True and _LLM_CALLS["n"] == 0
