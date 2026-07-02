"""Phase 6.2 Part 1 — asset traceability links + IDOR-safe ownership validation."""

from __future__ import annotations

import uuid
from types import SimpleNamespace

import pytest
from fastapi import HTTPException

from aicmo.modules.content import service
from aicmo.modules.content.schemas import GenerateRequest


def _payload(**over):
    base = dict(content_type="social_post", platform="instagram", goal="Drive engagement")
    base.update(over)
    return GenerateRequest.model_validate(base)


class _Session:
    """session.get(model, id) → the row registered for that id, else None."""

    def __init__(self, rows: dict):
        self._rows = rows

    async def get(self, _model, id_):
        return self._rows.get(id_)


_BRAND = uuid.uuid4()
_OTHER_BRAND = uuid.uuid4()
_TENANT = SimpleNamespace(brand_id=_BRAND, organization_id=uuid.uuid4(), user_id="u")


@pytest.mark.asyncio
async def test_no_links_passes():
    await service._validate_link_ownership(
        _Session({}), tenant=_TENANT, payload=_payload()
    )  # no exception


@pytest.mark.asyncio
async def test_owned_link_passes():
    cid = uuid.uuid4()
    session = _Session({cid: SimpleNamespace(brand_id=_BRAND)})
    await service._validate_link_ownership(
        session, tenant=_TENANT, payload=_payload(campaign_id=cid)
    )


@pytest.mark.asyncio
async def test_unknown_link_rejected():
    session = _Session({})  # id not found
    with pytest.raises(HTTPException) as ei:
        await service._validate_link_ownership(
            session, tenant=_TENANT, payload=_payload(bundle_id=uuid.uuid4())
        )
    assert ei.value.status_code == 400


@pytest.mark.asyncio
async def test_cross_tenant_link_rejected():
    # A real row, but owned by a DIFFERENT brand → must be rejected (IDOR).
    sid = uuid.uuid4()
    session = _Session({sid: SimpleNamespace(brand_id=_OTHER_BRAND)})
    with pytest.raises(HTTPException) as ei:
        await service._validate_link_ownership(
            session, tenant=_TENANT, payload=_payload(strategy_id=sid)
        )
    assert ei.value.status_code == 400
    assert "workspace" in ei.value.detail.lower()


def test_request_and_response_expose_link_fields():
    p = _payload(recommendation_id=uuid.uuid4())
    assert p.recommendation_id is not None
    from aicmo.modules.content.schemas import GeneratedContentResponse

    fields = GeneratedContentResponse.model_fields
    assert {"campaign_id", "bundle_id", "strategy_id", "recommendation_id"} <= set(fields)
