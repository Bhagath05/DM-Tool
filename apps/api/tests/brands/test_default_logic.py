"""Phase 10.2f — Brand default + activate + archive-clears-default.

Pin the pure-logic invariants of the new brand service functions:

  - set_default_brand: clears prior default in same TX
  - set_default_brand: refuses to promote an archived brand
  - set_default_brand: idempotent when already default
  - activate_brand_for_member: updates member.last_active_brand_id
  - activate_brand_for_member: idempotent when no change
  - archive_brand: clears is_default if the archived brand was default

A real-DB integration pass for the partial unique index
`uq_brands_one_default_per_org` runs in 10.2f-7 (verify).
"""

from __future__ import annotations

import uuid
from datetime import datetime, timezone
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from aicmo.modules.brands import service


def _brand_row(**overrides):
    row = MagicMock()
    row.id = overrides.get("id", uuid.uuid4())
    row.organization_id = overrides.get("organization_id", uuid.uuid4())
    row.slug = overrides.get("slug", "main")
    row.name = overrides.get("name", "Main")
    row.description = overrides.get("description", None)
    row.status = overrides.get("status", "active")
    row.created_by_user_id = overrides.get(
        "created_by_user_id", uuid.uuid4()
    )
    row.created_at = overrides.get("created_at", datetime.now(timezone.utc))
    row.updated_at = overrides.get("updated_at", datetime.now(timezone.utc))
    row.logo_url = overrides.get("logo_url", None)
    row.website = overrides.get("website", None)
    row.is_default = overrides.get("is_default", False)
    # `is_active` property — derived from status
    row.is_active = row.status == "active"
    return row


def _member_row(**overrides):
    row = MagicMock()
    row.id = overrides.get("id", uuid.uuid4())
    row.organization_id = overrides.get("organization_id", uuid.uuid4())
    row.user_id = overrides.get("user_id", uuid.uuid4())
    row.last_active_brand_id = overrides.get("last_active_brand_id", None)
    row.status = overrides.get("status", "active")
    return row


def _scalars_first_returning(prior_default):
    """Build a fake execute() chain so:
        result = await session.execute(stmt)
        result.scalars().first() == prior_default
    """
    scalars = MagicMock()
    scalars.first = MagicMock(return_value=prior_default)
    result = MagicMock()
    result.scalars = MagicMock(return_value=scalars)
    return result


# ---------------------------------------------------------------------
#  set_default_brand
# ---------------------------------------------------------------------


@pytest.mark.asyncio
async def test_set_default_promotes_target_and_clears_prior() -> None:
    org_id = uuid.uuid4()
    target = _brand_row(organization_id=org_id, is_default=False)
    prior = _brand_row(organization_id=org_id, is_default=True)

    session = MagicMock()

    # `session.get(Brand, brand_id)` → target
    session.get = AsyncMock(return_value=target)
    # `session.execute(...)` is called once for the prior-default lookup
    session.execute = AsyncMock(
        return_value=_scalars_first_returning(prior)
    )
    session.flush = AsyncMock()

    with patch(
        "aicmo.modules.brands.service.audit_service.record",
        new=AsyncMock(),
    ) as rec:
        result = await service.set_default_brand(
            session,
            actor_user_id=uuid.uuid4(),
            organization_id=org_id,
            brand_id=target.id,
        )

    assert target.is_default is True
    assert prior.is_default is False
    assert result.previous_default_brand_id == prior.id
    assert result.brand_id == target.id
    rec.assert_awaited_once()


@pytest.mark.asyncio
async def test_set_default_no_prior_default_works() -> None:
    org_id = uuid.uuid4()
    target = _brand_row(organization_id=org_id, is_default=False)

    session = MagicMock()
    session.get = AsyncMock(return_value=target)
    session.execute = AsyncMock(return_value=_scalars_first_returning(None))
    session.flush = AsyncMock()

    with patch(
        "aicmo.modules.brands.service.audit_service.record",
        new=AsyncMock(),
    ):
        result = await service.set_default_brand(
            session,
            actor_user_id=uuid.uuid4(),
            organization_id=org_id,
            brand_id=target.id,
        )
    assert target.is_default is True
    assert result.previous_default_brand_id is None


@pytest.mark.asyncio
async def test_set_default_idempotent_when_already_default() -> None:
    """Calling POST /default on the already-default brand must not
    touch state and must not produce an audit row."""
    org_id = uuid.uuid4()
    target = _brand_row(organization_id=org_id, is_default=True)

    session = MagicMock()
    session.get = AsyncMock(return_value=target)
    session.execute = AsyncMock(
        return_value=_scalars_first_returning(target)
    )
    session.flush = AsyncMock()

    with patch(
        "aicmo.modules.brands.service.audit_service.record",
        new=AsyncMock(),
    ) as rec:
        result = await service.set_default_brand(
            session,
            actor_user_id=uuid.uuid4(),
            organization_id=org_id,
            brand_id=target.id,
        )
    assert target.is_default is True
    assert result.previous_default_brand_id == target.id
    rec.assert_not_awaited()


@pytest.mark.asyncio
async def test_set_default_refuses_archived_brand() -> None:
    """The partial unique index would technically permit a non-active
    default, but the service refuses for UX clarity. Pin the 409."""
    from fastapi import HTTPException

    org_id = uuid.uuid4()
    archived = _brand_row(organization_id=org_id, status="archived")

    session = MagicMock()
    session.get = AsyncMock(return_value=archived)
    session.execute = AsyncMock()
    session.flush = AsyncMock()

    with pytest.raises(HTTPException) as exc:
        await service.set_default_brand(
            session,
            actor_user_id=uuid.uuid4(),
            organization_id=org_id,
            brand_id=archived.id,
        )
    assert exc.value.status_code == 409


@pytest.mark.asyncio
async def test_set_default_404_on_cross_org_brand() -> None:
    """Belt-and-suspenders: even if the URL carries a brand_id that
    belongs to a different org, the service returns 404 — same as the
    rest of the brand surface."""
    from fastapi import HTTPException

    target = _brand_row(organization_id=uuid.uuid4())  # different org

    session = MagicMock()
    session.get = AsyncMock(return_value=target)

    with pytest.raises(HTTPException) as exc:
        await service.set_default_brand(
            session,
            actor_user_id=uuid.uuid4(),
            organization_id=uuid.uuid4(),  # NOT the brand's org
            brand_id=target.id,
        )
    assert exc.value.status_code == 404


# ---------------------------------------------------------------------
#  activate_brand_for_member
# ---------------------------------------------------------------------


@pytest.mark.asyncio
async def test_activate_updates_last_active_brand_id() -> None:
    org_id = uuid.uuid4()
    target = _brand_row(organization_id=org_id, status="active")
    member = _member_row(
        organization_id=org_id, last_active_brand_id=uuid.uuid4()
    )

    # `session.get` is called twice — once for brand, once for member
    session = MagicMock()
    gets = {target.id: target, member.id: member}
    session.get = AsyncMock(side_effect=lambda cls, oid: gets.get(oid))
    session.flush = AsyncMock()

    with patch(
        "aicmo.modules.brands.service.audit_service.record",
        new=AsyncMock(),
    ) as rec:
        result = await service.activate_brand_for_member(
            session,
            actor_user_id=uuid.uuid4(),
            actor_member_id=member.id,
            organization_id=org_id,
            brand_id=target.id,
        )

    assert member.last_active_brand_id == target.id
    assert result.brand_id == target.id
    assert result.member_id == member.id
    rec.assert_awaited_once()


@pytest.mark.asyncio
async def test_activate_idempotent_when_no_change() -> None:
    org_id = uuid.uuid4()
    target = _brand_row(organization_id=org_id, status="active")
    member = _member_row(
        organization_id=org_id, last_active_brand_id=target.id
    )

    session = MagicMock()
    gets = {target.id: target, member.id: member}
    session.get = AsyncMock(side_effect=lambda cls, oid: gets.get(oid))
    session.flush = AsyncMock()

    with patch(
        "aicmo.modules.brands.service.audit_service.record",
        new=AsyncMock(),
    ) as rec:
        await service.activate_brand_for_member(
            session,
            actor_user_id=uuid.uuid4(),
            actor_member_id=member.id,
            organization_id=org_id,
            brand_id=target.id,
        )
    rec.assert_not_awaited()


@pytest.mark.asyncio
async def test_activate_refuses_archived_brand() -> None:
    from fastapi import HTTPException

    org_id = uuid.uuid4()
    target = _brand_row(organization_id=org_id, status="archived")
    member = _member_row(organization_id=org_id)

    session = MagicMock()
    gets = {target.id: target, member.id: member}
    session.get = AsyncMock(side_effect=lambda cls, oid: gets.get(oid))

    with pytest.raises(HTTPException) as exc:
        await service.activate_brand_for_member(
            session,
            actor_user_id=uuid.uuid4(),
            actor_member_id=member.id,
            organization_id=org_id,
            brand_id=target.id,
        )
    assert exc.value.status_code == 404


# ---------------------------------------------------------------------
#  archive_brand — clears default flag
# ---------------------------------------------------------------------


@pytest.mark.asyncio
async def test_archive_brand_clears_default_flag() -> None:
    """If the brand being archived was the default, clear the flag so
    a future `set_default_brand` on a different brand doesn't trip the
    partial unique index."""
    org_id = uuid.uuid4()
    target = _brand_row(
        organization_id=org_id, status="active", is_default=True
    )

    # The active-count query needs to return > 1 (otherwise archive
    # refuses to archive the only active brand).
    count_result = MagicMock()
    count_result.scalar_one = MagicMock(return_value=2)
    session = MagicMock()
    session.get = AsyncMock(
        side_effect=lambda cls, oid: (
            target
            if oid == target.id
            else _MockOrg(org_id, brand_count=3)
        )
    )
    session.execute = AsyncMock(return_value=count_result)
    session.flush = AsyncMock()

    with patch(
        "aicmo.modules.brands.service.audit_service.record",
        new=AsyncMock(),
    ) as rec:
        result = await service.archive_brand(
            session,
            actor_user_id=uuid.uuid4(),
            organization_id=org_id,
            brand_id=target.id,
        )
    assert target.status == "archived"
    assert target.is_default is False  # ← the key assertion
    assert result.status == "archived"
    # Audit row carries the is_default before/after delta
    rec.assert_awaited_once()
    kwargs = rec.await_args.kwargs
    assert kwargs.get("before") == {"is_default": True}
    assert kwargs.get("after") == {"is_default": False}


@pytest.mark.asyncio
async def test_archive_non_default_brand_does_not_emit_default_audit() -> None:
    """If the brand wasn't default, the audit row should NOT carry an
    is_default delta — keeps the audit log noise-free."""
    org_id = uuid.uuid4()
    target = _brand_row(
        organization_id=org_id, status="active", is_default=False
    )

    count_result = MagicMock()
    count_result.scalar_one = MagicMock(return_value=2)
    session = MagicMock()
    session.get = AsyncMock(
        side_effect=lambda cls, oid: (
            target
            if oid == target.id
            else _MockOrg(org_id, brand_count=3)
        )
    )
    session.execute = AsyncMock(return_value=count_result)
    session.flush = AsyncMock()

    with patch(
        "aicmo.modules.brands.service.audit_service.record",
        new=AsyncMock(),
    ) as rec:
        await service.archive_brand(
            session,
            actor_user_id=uuid.uuid4(),
            organization_id=org_id,
            brand_id=target.id,
        )
    kwargs = rec.await_args.kwargs
    assert kwargs.get("before") is None
    assert kwargs.get("after") is None


# ---------------------------------------------------------------------
#  helpers
# ---------------------------------------------------------------------


class _MockOrg:
    """Lightweight Organization stand-in for archive_brand's counter
    decrement. MagicMock auto-attrs would silently absorb the
    decrement, so use a real attribute."""

    def __init__(self, org_id, brand_count):
        self.id = org_id
        self.brand_count = brand_count
