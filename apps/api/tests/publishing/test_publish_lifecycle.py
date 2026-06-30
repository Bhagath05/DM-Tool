"""Publishing lifecycle additions — audit-history read + operator retry.

Focus: the tenant-isolation guard (`_require_owned_post`) that both new
endpoints rely on, and the retry state machine. Mock-based (no DB) to match
the lightweight style of the other publishing tests.
"""

from __future__ import annotations

from types import SimpleNamespace
from unittest.mock import AsyncMock
from uuid import uuid4

import pytest
from fastapi import HTTPException

from aicmo.modules.publishing import service


@pytest.mark.asyncio
async def test_require_owned_post_returns_for_owner():
    bid = uuid4()
    row = SimpleNamespace(brand_id=bid)
    session = SimpleNamespace(get=AsyncMock(return_value=row))
    out = await service._require_owned_post(
        session, brand_id=bid, scheduled_post_id=uuid4()
    )
    assert out is row


@pytest.mark.asyncio
async def test_require_owned_post_404_for_other_brand():
    # A post owned by a DIFFERENT brand must 404 — never leak existence.
    row = SimpleNamespace(brand_id=uuid4())
    session = SimpleNamespace(get=AsyncMock(return_value=row))
    with pytest.raises(HTTPException) as exc:
        await service._require_owned_post(
            session, brand_id=uuid4(), scheduled_post_id=uuid4()
        )
    assert exc.value.status_code == 404


@pytest.mark.asyncio
async def test_require_owned_post_404_when_missing():
    session = SimpleNamespace(get=AsyncMock(return_value=None))
    with pytest.raises(HTTPException) as exc:
        await service._require_owned_post(
            session, brand_id=uuid4(), scheduled_post_id=uuid4()
        )
    assert exc.value.status_code == 404


@pytest.mark.asyncio
async def test_list_events_enforces_ownership_before_reading(monkeypatch):
    # If ownership fails, list_events must raise — never return another
    # tenant's audit trail.
    monkeypatch.setattr(
        service,
        "_require_owned_post",
        AsyncMock(side_effect=HTTPException(status_code=404, detail="x")),
    )
    with pytest.raises(HTTPException):
        await service.list_events(
            AsyncMock(), brand_id=uuid4(), scheduled_post_id=uuid4()
        )


@pytest.mark.asyncio
async def test_retry_post_resets_budget_and_republishes(monkeypatch):
    bid = uuid4()
    row = SimpleNamespace(
        id=uuid4(),
        brand_id=bid,
        publish_status="failed",
        attempt_count=3,
        error_message="boom",
    )
    monkeypatch.setattr(service, "_require_owned_post", AsyncMock(return_value=row))
    monkeypatch.setattr(service, "_log_event", AsyncMock())
    monkeypatch.setattr(service, "publish_scheduled_post", AsyncMock(return_value="RESULT"))
    session = SimpleNamespace(flush=AsyncMock())
    tenant = SimpleNamespace(brand_id=bid)

    out = await service.retry_post(
        session, scheduled_post_id=row.id, tenant=tenant
    )

    assert row.attempt_count == 0
    assert row.publish_status == "scheduled"
    assert row.error_message is None
    assert out == "RESULT"
    service.publish_scheduled_post.assert_awaited_once()


@pytest.mark.asyncio
async def test_retry_post_rejects_already_published(monkeypatch):
    row = SimpleNamespace(brand_id=uuid4(), publish_status="published")
    monkeypatch.setattr(service, "_require_owned_post", AsyncMock(return_value=row))
    monkeypatch.setattr(service, "publish_scheduled_post", AsyncMock())
    with pytest.raises(HTTPException) as exc:
        await service.retry_post(
            SimpleNamespace(flush=AsyncMock()),
            scheduled_post_id=uuid4(),
            tenant=SimpleNamespace(brand_id=row.brand_id),
        )
    assert exc.value.status_code == 409
    service.publish_scheduled_post.assert_not_awaited()
