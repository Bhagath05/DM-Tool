"""Phase 10.2d — Last-owner safety on remove_role.

The behaviour change in 10.2d-5: owners may now revoke the owner role
from co-owners (previously blanket-refused). The new rule is enforced
by `_count_owners` — refuse if removal would leave zero owners.

These tests target the pure helper `_count_owners` via a stub session
and the exception path of `remove_role`. End-to-end is exercised by
the live DB smoke in 10.2d-8.
"""

from __future__ import annotations

import uuid
from unittest.mock import AsyncMock, MagicMock

import pytest
from fastapi import HTTPException

from aicmo.modules.orgs import service as orgs_service
from aicmo.tenancy.exceptions import NotAuthorized


def _stub_session(owner_count: int):
    """Build a stub session that returns `owner_count` from
    `_count_owners` and behaves like an active member exists."""
    session = MagicMock()
    # _count_owners issues one SELECT count(...) — return that.
    result = MagicMock()
    result.scalar_one.return_value = owner_count
    session.execute = AsyncMock(return_value=result)
    return session


@pytest.mark.asyncio
async def test_count_owners_returns_int(monkeypatch) -> None:
    """The helper integrates into remove_role's safety check —
    smoke that it speaks ints and not strings."""
    session = _stub_session(owner_count=2)
    n = await orgs_service._count_owners(session, org_id=uuid.uuid4())
    assert n == 2 and isinstance(n, int)


@pytest.mark.asyncio
async def test_count_owners_zero_when_no_owners(monkeypatch) -> None:
    session = _stub_session(owner_count=0)
    n = await orgs_service._count_owners(session, org_id=uuid.uuid4())
    assert n == 0


@pytest.mark.asyncio
async def test_owner_removal_by_non_owner_rejected(monkeypatch) -> None:
    """Even with 5 owners in the org, a non-owner cannot revoke owner.
    NotAuthorized, not the 409 last-owner error — different failure mode."""

    # Force _is_owner: actor=False (admin), target=True (owner).
    monkeypatch.setattr(
        orgs_service,
        "_is_owner",
        AsyncMock(side_effect=[False, True]),  # actor first, target second
    )
    # Member lookup returns a fake member.
    monkeypatch.setattr(
        orgs_service,
        "get_member",
        AsyncMock(return_value=MagicMock(id=uuid.uuid4())),
    )
    monkeypatch.setattr(
        orgs_service,
        "_load_system_or_org_role",
        AsyncMock(return_value=MagicMock(id=uuid.uuid4())),
    )

    session = MagicMock()
    with pytest.raises(NotAuthorized):
        await orgs_service.remove_role(
            session=session,
            actor_user_id=uuid.uuid4(),
            actor_member_id=uuid.uuid4(),
            org_id=uuid.uuid4(),
            member_id=uuid.uuid4(),
            role_slug="owner",
        )


@pytest.mark.asyncio
async def test_owner_removal_when_last_owner_rejected(monkeypatch) -> None:
    """Owner trying to remove owner role when count(owners) == 1 →
    409 Cannot remove last owner."""
    # Both actor and target are owner (actor revoking themselves or
    # a co-owner; we don't distinguish — only count matters).
    monkeypatch.setattr(
        orgs_service,
        "_is_owner",
        AsyncMock(side_effect=[True, True]),
    )
    monkeypatch.setattr(
        orgs_service,
        "_count_owners",
        AsyncMock(return_value=1),  # only one owner left
    )
    monkeypatch.setattr(
        orgs_service,
        "get_member",
        AsyncMock(return_value=MagicMock(id=uuid.uuid4())),
    )
    monkeypatch.setattr(
        orgs_service,
        "_load_system_or_org_role",
        AsyncMock(return_value=MagicMock(id=uuid.uuid4())),
    )

    session = MagicMock()
    with pytest.raises(HTTPException) as exc:
        await orgs_service.remove_role(
            session=session,
            actor_user_id=uuid.uuid4(),
            actor_member_id=uuid.uuid4(),
            org_id=uuid.uuid4(),
            member_id=uuid.uuid4(),
            role_slug="owner",
        )
    assert exc.value.status_code == 409
    assert "last owner" in exc.value.detail.lower()


@pytest.mark.asyncio
async def test_owner_removal_when_multiple_owners_proceeds_to_existing_check(
    monkeypatch,
) -> None:
    """If actor=owner AND count>1, the function moves past the
    last-owner gate. We can't assert success without a full session
    fixture, but we CAN assert the function no longer raises the
    last-owner 409 — the next mock (compute_role_slugs) is what fires."""
    monkeypatch.setattr(
        orgs_service,
        "_is_owner",
        AsyncMock(side_effect=[True, True]),
    )
    monkeypatch.setattr(
        orgs_service,
        "_count_owners",
        AsyncMock(return_value=2),  # safe — 2 owners
    )
    monkeypatch.setattr(
        orgs_service,
        "get_member",
        AsyncMock(return_value=MagicMock(id=uuid.uuid4())),
    )
    monkeypatch.setattr(
        orgs_service,
        "_load_system_or_org_role",
        AsyncMock(return_value=MagicMock(id=uuid.uuid4())),
    )
    # Past the safety gates, the function looks for an existing
    # MemberRole row. Return None → idempotent no-op path.
    session = MagicMock()
    session.execute = AsyncMock(
        return_value=MagicMock(scalar_one_or_none=lambda: None)
    )
    # And compute_role_slugs_for_member, called twice in this path.
    monkeypatch.setattr(
        orgs_service,
        "compute_role_slugs_for_member",
        AsyncMock(return_value={"owner", "admin"}),
    )

    # Should NOT raise.
    result = await orgs_service.remove_role(
        session=session,
        actor_user_id=uuid.uuid4(),
        actor_member_id=uuid.uuid4(),
        org_id=uuid.uuid4(),
        member_id=uuid.uuid4(),
        role_slug="owner",
    )
    assert "owner" in result and "admin" in result
