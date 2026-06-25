"""CS1-5 — growth module: schemas, catalog (industry-free), service logic."""

from __future__ import annotations

import uuid

import pytest

from aicmo.modules.growth.catalog import OBJECTIVE_CATEGORIES, OBJECTIVE_KIND_SLUGS
from aicmo.modules.growth.schemas import CreateObjectiveRequest, ObjectiveKindOut
from aicmo.modules.growth.service import (
    MissingBrand,
    UnknownObjectiveKind,
    create_objective,
)
from aicmo.tenancy.context import TenantContext


# ---- schema ----
def test_create_request_rejects_empty_statement():
    with pytest.raises(Exception):
        CreateObjectiveRequest(objective_kind="get_leads", statement="")


def test_objective_kind_out_from_attrs():
    class Row:
        slug = "get_leads"
        display_name = "Get Leads"
        category = "lead"
        kpi_hint = "leads / cost per lead"
        default_channels = ["meta", "google"]

    out = ObjectiveKindOut.model_validate(Row())
    assert out.slug == "get_leads" and out.default_channels == ["meta", "google"]


# ---- catalog is industry-FREE (Law 2) ----
def test_catalog_categories_are_outcomes_not_industries():
    # outcomes only — none of these are industries
    assert "lead" in OBJECTIVE_CATEGORIES and "booking" in OBJECTIVE_CATEGORIES
    industries = {"restaurant", "healthcare", "real_estate", "saas", "retail", "fitness"}
    assert OBJECTIVE_CATEGORIES.isdisjoint(industries)
    assert len(OBJECTIVE_KIND_SLUGS) == 9


# ---- service logic (fake session) ----
class FakeKind:
    def __init__(self, active=True):
        self.is_active = active


class FakeSession:
    def __init__(self, kind=None):
        self._kind = kind
        self.added: list = []

    async def get(self, model, pk):
        return self._kind

    def add(self, obj):
        self.added.append(obj)


def _tenant(brand_id):
    return TenantContext(
        user_id="u_1", user_uuid=uuid.uuid4(), organization_id=uuid.uuid4(),
        brand_id=brand_id, member_id=uuid.uuid4(), role_slugs=("owner",),
        permissions=frozenset({"growth.create"}),
    )


@pytest.mark.asyncio
async def test_create_objective_happy_path():
    s = FakeSession(kind=FakeKind())
    t = _tenant(uuid.uuid4())
    obj = await create_objective(
        s, tenant=t, payload=CreateObjectiveRequest(objective_kind="get_leads", statement="More leads"))
    assert obj.objective_kind == "get_leads"
    assert obj.brand_id == t.brand_id and obj.organization_id == t.organization_id
    assert obj.status == "active"
    assert s.added == [obj]


@pytest.mark.asyncio
async def test_create_objective_unknown_kind_rejected():
    s = FakeSession(kind=None)  # session.get returns None → unknown
    with pytest.raises(UnknownObjectiveKind):
        await create_objective(
            s, tenant=_tenant(uuid.uuid4()),
            payload=CreateObjectiveRequest(objective_kind="get_unicorns", statement="x"))


@pytest.mark.asyncio
async def test_create_objective_requires_brand():
    s = FakeSession(kind=FakeKind())
    with pytest.raises(MissingBrand):
        await create_objective(
            s, tenant=_tenant(None),  # no brand resolved
            payload=CreateObjectiveRequest(objective_kind="get_leads", statement="x"))
