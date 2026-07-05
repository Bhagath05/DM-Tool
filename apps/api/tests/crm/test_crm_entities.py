"""Phase 6.5 Slice 2 — CRM companies/contacts: domain normalisation, CRUD field
mapping, cross-tenant guards, merge logic, and AI-summary grounding. Hermetic —
fake session, no DB/network (audit + LLM stubbed)."""

from __future__ import annotations

import asyncio
import uuid
from types import SimpleNamespace

import pytest
from fastapi import HTTPException

from aicmo.modules.crm import ai as crm_ai
from aicmo.modules.crm import entities_service as svc
from aicmo.modules.crm.models import Company, Contact
from aicmo.modules.crm.schemas import (
    CompanyCreate,
    CompanySummary,
    ContactCreate,
    ContactSummary,
)

_ORG = uuid.uuid4()
_BRAND = uuid.uuid4()
_TENANT = SimpleNamespace(
    organization_id=_ORG, brand_id=_BRAND, user_id="rep-1", user_uuid=uuid.uuid4()
)


class _Result:
    def scalars(self):
        return self

    def all(self):
        return []

    def scalar_one(self):
        return 0

    def scalar_one_or_none(self):
        return None


class _Session:
    """get() dispatches by id from a store; execute() is a benign no-op."""

    def __init__(self, store=None):
        self._store = store or {}
        self.added: list = []
        self.deleted: list = []

    async def get(self, _model, _id):
        return self._store.get(_id)

    async def execute(self, _stmt):
        return _Result()

    def add(self, obj):
        self.added.append(obj)

    async def delete(self, obj):
        self.deleted.append(obj)

    async def commit(self):
        pass

    async def refresh(self, _obj):
        pass


@pytest.fixture(autouse=True)
def _stub_audit(monkeypatch):
    async def _noop(*_a, **_k):
        return None

    monkeypatch.setattr(svc, "_audit", _noop)


def run(c):
    return asyncio.run(c)


# ---- domain normalisation ----
@pytest.mark.parametrize("website,expected", [
    ("https://www.acme.com", "acme.com"),
    ("http://acme.com/path", "acme.com"),
    ("acme.io", "acme.io"),
    ("https://WWW.Foo.CO.UK", "foo.co.uk"),
    (None, None),
    ("", None),
])
def test_domain_normalisation(website, expected):
    assert svc._domain(website) == expected


# ---- create field mapping ----
def test_create_company_derives_domain_and_owner():
    session = _Session()
    row = run(svc.create_company(
        session, tenant=_TENANT,
        payload=CompanyCreate(name="Acme", website="https://www.acme.com", industry="SaaS"),
    ))
    assert row.domain == "acme.com"
    assert row.owner_user_id == "rep-1"
    assert row.brand_id == _BRAND and row.organization_id == _ORG


def test_create_contact_validates_company_ownership():
    # company_id points at a company owned by another brand → 404
    foreign = Company(
        id=uuid.uuid4(), organization_id=_ORG, brand_id=uuid.uuid4(), name="Other",
    )
    session = _Session({foreign.id: foreign})
    with pytest.raises(HTTPException) as ei:
        run(svc.create_contact(
            session, tenant=_TENANT,
            payload=ContactCreate(name="Jane", company_id=foreign.id),
        ))
    assert ei.value.status_code == 404


# ---- cross-tenant guards ----
def test_owned_company_cross_tenant_404():
    other = Company(id=uuid.uuid4(), organization_id=_ORG, brand_id=uuid.uuid4(), name="X")
    with pytest.raises(HTTPException) as ei:
        run(svc._owned_company(_Session({other.id: other}), tenant=_TENANT, company_id=other.id))
    assert ei.value.status_code == 404


def test_owned_contact_cross_tenant_404():
    other = Contact(id=uuid.uuid4(), organization_id=_ORG, brand_id=uuid.uuid4(), name="X")
    with pytest.raises(HTTPException) as ei:
        run(svc._owned_contact(_Session({other.id: other}), tenant=_TENANT, contact_id=other.id))
    assert ei.value.status_code == 404


# ---- merge ----
def test_merge_contact_into_self_rejected():
    cid = uuid.uuid4()
    c = Contact(id=cid, organization_id=_ORG, brand_id=_BRAND, name="A")
    with pytest.raises(HTTPException) as ei:
        run(svc.merge_contacts(_Session({cid: c}), tenant=_TENANT, survivor_id=cid, duplicate_id=cid))
    assert ei.value.status_code == 400


def test_merge_contacts_fills_blanks_and_unions_tags():
    survivor = Contact(
        id=uuid.uuid4(), organization_id=_ORG, brand_id=_BRAND, name="Jane",
        email=None, phone="111", title=None, linkedin=None, company_id=None, notes=None,
        tags=["vip"], custom_fields={"a": 1},
    )
    dup = Contact(
        id=uuid.uuid4(), organization_id=_ORG, brand_id=_BRAND, name="Jane D",
        email="jane@acme.com", phone="999", title="CTO", linkedin=None, company_id=None,
        notes="met at conf", tags=["warm"], custom_fields={"b": 2},
    )
    session = _Session({survivor.id: survivor, dup.id: dup})
    out = run(svc.merge_contacts(session, tenant=_TENANT, survivor_id=survivor.id, duplicate_id=dup.id))
    # blank survivor fields filled from the duplicate…
    assert out.email == "jane@acme.com"
    assert out.title == "CTO"
    # …but a field the survivor already had is preserved
    assert out.phone == "111"
    assert set(out.tags) == {"vip", "warm"}
    assert out.custom_fields == {"a": 1, "b": 2}
    assert dup in session.deleted


def test_merge_company_into_self_rejected():
    cid = uuid.uuid4()
    c = Company(id=cid, organization_id=_ORG, brand_id=_BRAND, name="Acme")
    with pytest.raises(HTTPException) as ei:
        run(svc.merge_companies(_Session({cid: c}), tenant=_TENANT, survivor_id=cid, duplicate_id=cid))
    assert ei.value.status_code == 400


# ---- AI grounding ----
def test_contact_summary_is_grounded(monkeypatch):
    captured = {}

    async def _fake_generate(**kwargs):
        captured["prompt"] = kwargs["messages"][0].content
        return SimpleNamespace(data=ContactSummary(
            summary="CTO at Acme", talking_points=["ask about roadmap"],
            confidence=70, reason="title + company",
        ))

    monkeypatch.setattr(crm_ai, "get_llm_router", lambda: SimpleNamespace(generate=_fake_generate))
    contact = Contact(
        id=uuid.uuid4(), organization_id=_ORG, brand_id=_BRAND, name="Jane", title="CTO",
        email="jane@acme.com", linkedin=None, notes=None, tags=[], company_id=None,
    )
    out = run(crm_ai.contact_summary(_Session(), contact))
    assert out.confidence == 70
    # the prompt was built only from real fields we set
    assert "Jane" in captured["prompt"] and "CTO" in captured["prompt"]


def test_company_summary_is_grounded(monkeypatch):
    async def _fake_generate(**_k):
        return SimpleNamespace(data=CompanySummary(
            summary="Mid-market SaaS", opportunities=["upsell"], risks=[],
            confidence=65, reason="industry + employees",
        ))

    monkeypatch.setattr(crm_ai, "get_llm_router", lambda: SimpleNamespace(generate=_fake_generate))
    company = Company(
        id=uuid.uuid4(), organization_id=_ORG, brand_id=_BRAND, name="Acme",
        industry="SaaS", employees=200, tech_stack=["AWS"],
    )
    out = run(crm_ai.company_summary(_Session(), company))
    assert out.confidence == 65 and "upsell" in out.opportunities
