"""Phase 6.5 — CRM core: deal lifecycle, ownership, stage inheritance, AI
grounding. Hermetic — a fake session, no DB, no network (audit + LLM stubbed).
"""

from __future__ import annotations

import asyncio
import uuid
from types import SimpleNamespace

import pytest
from fastapi import HTTPException

from aicmo.modules.crm import ai as crm_ai
from aicmo.modules.crm import service
from aicmo.modules.crm.models import Deal, DealStageEvent, PipelineStage
from aicmo.modules.crm.schemas import DealCreate, DealNextAction

_ORG = uuid.uuid4()
_BRAND = uuid.uuid4()
_TENANT = SimpleNamespace(
    organization_id=_ORG, brand_id=_BRAND, user_id="rep-1", user_uuid=uuid.uuid4()
)
_PIPELINE = uuid.uuid4()


def _deal(**over):
    base = dict(
        id=uuid.uuid4(), organization_id=_ORG, brand_id=_BRAND, pipeline_id=_PIPELINE,
        stage_id=None, lead_id=None, title="Acme deal", company="Acme", contact_name=None,
        contact_email=None, contact_phone=None, value=10000, currency="USD", probability=30,
        status="open", priority="medium", expected_close_date=None, owner_user_id="rep-1",
        source=None, tags=[], products=[], competitors=[], lost_reason=None, won_at=None,
        lost_at=None, ai_next_action=None, ai_generated_at=None,
    )
    base.update(over)
    return Deal(**base)


def _stage(**over):
    base = dict(
        id=uuid.uuid4(), organization_id=_ORG, brand_id=_BRAND, pipeline_id=_PIPELINE,
        name="Proposal", position=2, probability=55, is_won=False, is_lost=False,
    )
    base.update(over)
    return PipelineStage(**base)


class _Session:
    """Dispatches session.get by model; records adds."""

    def __init__(self, *, deal=None, stages=None, pipeline=True):
        self._deal = deal
        self._stages = {s.id: s for s in (stages or [])}
        self._pipeline = pipeline
        self.added: list = []

    async def get(self, model, _id):
        name = getattr(model, "__tablename__", "")
        if name == "crm_deals":
            return self._deal
        if name == "crm_pipeline_stages":
            return self._stages.get(_id)
        if name == "crm_pipelines":
            return SimpleNamespace(brand_id=_BRAND) if self._pipeline else None
        return None

    def add(self, obj):
        self.added.append(obj)

    async def commit(self):
        pass

    async def refresh(self, _obj):
        pass


@pytest.fixture(autouse=True)
def _stub_audit(monkeypatch):
    async def _noop(*_a, **_k):
        return None

    monkeypatch.setattr(service.audit_service, "record", _noop)


def run(c):
    return asyncio.run(c)


# ---- move state machine ----
def test_move_to_won_stage_marks_won_and_records_event():
    deal = _deal(status="open")
    won = _stage(name="Won", probability=100, is_won=True)
    session = _Session(deal=deal, stages=[won])
    out = run(service.move_deal(session, tenant=_TENANT, deal_id=deal.id, stage_id=won.id))
    assert out.status == "won"
    assert out.probability == 100
    assert out.won_at is not None
    ev = next(o for o in session.added if isinstance(o, DealStageEvent))
    assert ev.to_status == "won" and ev.to_stage_id == won.id


def test_move_to_lost_stage_marks_lost():
    deal = _deal()
    lost = _stage(name="Lost", probability=0, is_lost=True)
    out = run(service.move_deal(_Session(deal=deal, stages=[lost]), tenant=_TENANT, deal_id=deal.id, stage_id=lost.id))
    assert out.status == "lost" and out.lost_at is not None


def test_move_to_open_stage_inherits_stage_probability():
    deal = _deal(probability=10)
    stage = _stage(probability=55)
    out = run(service.move_deal(_Session(deal=deal, stages=[stage]), tenant=_TENANT, deal_id=deal.id, stage_id=stage.id))
    assert out.status == "open" and out.probability == 55


def test_move_rejects_stage_from_other_pipeline():
    deal = _deal()
    foreign = _stage(pipeline_id=uuid.uuid4())
    with pytest.raises(HTTPException) as ei:
        run(service.move_deal(_Session(deal=deal, stages=[foreign]), tenant=_TENANT, deal_id=deal.id, stage_id=foreign.id))
    assert ei.value.status_code == 400


# ---- close ----
def test_close_won_sets_probability_100():
    deal = _deal()
    out = run(service.close_deal(_Session(deal=deal), tenant=_TENANT, deal_id=deal.id, close_status="won", lost_reason=None))
    assert out.status == "won" and out.probability == 100


def test_close_lost_records_reason():
    deal = _deal()
    out = run(service.close_deal(_Session(deal=deal), tenant=_TENANT, deal_id=deal.id, close_status="lost", lost_reason="price"))
    assert out.status == "lost" and out.lost_reason == "price" and out.probability == 0


# ---- ownership / tenant isolation ----
def test_cross_tenant_deal_is_404():
    other = _deal(brand_id=uuid.uuid4())
    with pytest.raises(HTTPException) as ei:
        run(service._owned_deal(_Session(deal=other), tenant=_TENANT, deal_id=other.id))
    assert ei.value.status_code == 404


# ---- create inherits stage probability ----
def test_create_deal_inherits_stage_probability_when_unset():
    stage = _stage(probability=40)
    session = _Session(stages=[stage])
    payload = DealCreate(pipeline_id=_PIPELINE, stage_id=stage.id, title="New deal")
    out = run(service.create_deal(session, tenant=_TENANT, payload=payload))
    assert out.probability == 40


# ---- AI grounding ----
def test_context_lines_use_only_present_fields():
    deal = _deal(company="Acme", competitors=["Rival Inc"], probability=60)
    session = _Session(deal=deal)
    lines = run(crm_ai._context_lines(session, deal))
    joined = "\n".join(lines)
    assert "Company: Acme" in joined
    assert "Competitors: Rival Inc" in joined
    assert "Win probability: 60%" in joined
    # a field that's absent must NOT appear (no fabrication)
    assert "Expected close" not in joined


def test_next_action_returns_grounded_contract(monkeypatch):
    result = DealNextAction(
        recommendation="Send a tailored proposal", reason="value + proposal stage",
        confidence=78, expected_result="advance to negotiation in 1-2 weeks",
        risk_score=35, opportunity_score=70,
    )

    async def _fake_generate(**_k):
        return SimpleNamespace(data=result)

    monkeypatch.setattr(crm_ai, "get_llm_router", lambda: SimpleNamespace(generate=_fake_generate))
    out = run(crm_ai.next_action(_Session(deal=_deal()), _deal()))
    assert out.confidence == 78 and out.risk_score == 35
    assert 0 <= out.opportunity_score <= 100
