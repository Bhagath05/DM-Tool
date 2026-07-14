"""Phase 6.6 Slice 4 — member/role security invariants (Part 7).

Hermetic: the guard *decisions* are isolated by stubbing the DB-backed
helpers, so these pin the security policy (privilege escalation, last-Admin
floor, owner/self protection) without needing Postgres. The queries behind
the helpers run against real Postgres at Render boot.
"""

from __future__ import annotations

import types
import uuid

import pytest
from fastapi import HTTPException

from aicmo.modules.orgs import service
from aicmo.tenancy.exceptions import NotAuthorized


class _Session:
    """Placeholder — the guards short-circuit before touching it."""


def _member(**kw) -> object:
    return types.SimpleNamespace(
        id=kw.get("id", uuid.uuid4()),
        status=kw.get("status", "active"),
        **{k: v for k, v in kw.items() if k not in ("id", "status")},
    )


# ---------------------------------------------------------------------
#  Privilege escalation — assign_role
# ---------------------------------------------------------------------


@pytest.mark.asyncio
async def test_non_owner_cannot_assign_higher_priority_role(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    role = types.SimpleNamespace(id=uuid.uuid4(), priority=100, slug="admin")

    async def _get_member(session, *, org_id, member_id):
        return _member(id=member_id)

    async def _load(session, *, org_id, role_slug):
        return role

    async def _is_owner(session, mid):
        return False

    async def _max_priority(session, mid):
        return 50  # actor tops out below the role they're trying to grant

    monkeypatch.setattr(service, "get_member", _get_member)
    monkeypatch.setattr(service, "_load_system_or_org_role", _load)
    monkeypatch.setattr(service, "_is_owner", _is_owner)
    monkeypatch.setattr(service, "_max_role_priority", _max_priority)

    with pytest.raises(NotAuthorized):
        await service.assign_role(
            _Session(),
            actor_user_id=uuid.uuid4(),
            actor_member_id=uuid.uuid4(),
            org_id=uuid.uuid4(),
            member_id=uuid.uuid4(),
            role_slug="admin",
        )


@pytest.mark.asyncio
async def test_owner_bypasses_escalation_check(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """An owner may grant any role — the escalation guard must not fire.
    We assert it gets *past* the guard (raising a sentinel at the next
    step proves the guard didn't block)."""
    role = types.SimpleNamespace(id=uuid.uuid4(), priority=100, slug="admin")
    reached = {}

    class _TripSession:
        async def execute(self, *_a, **_k):
            # First DB call after the guard block — reaching it proves the
            # escalation check let the owner through.
            raise RuntimeError("passed the escalation guard")

    async def _get_member(session, *, org_id, member_id):
        return _member(id=member_id)

    async def _load(session, *, org_id, role_slug):
        return role

    async def _is_owner(session, mid):
        return True  # actor (and target) owner

    async def _max_priority(session, mid):  # must NOT be called for an owner
        reached["max"] = True
        return 0

    monkeypatch.setattr(service, "get_member", _get_member)
    monkeypatch.setattr(service, "_load_system_or_org_role", _load)
    monkeypatch.setattr(service, "_is_owner", _is_owner)
    monkeypatch.setattr(service, "_max_role_priority", _max_priority)

    with pytest.raises(RuntimeError, match="passed the escalation guard"):
        await service.assign_role(
            _TripSession(),
            actor_user_id=uuid.uuid4(),
            actor_member_id=uuid.uuid4(),
            org_id=uuid.uuid4(),
            member_id=uuid.uuid4(),
            role_slug="admin",
        )
    assert "max" not in reached  # owner skips the priority lookup entirely


# ---------------------------------------------------------------------
#  Last-Admin floor — remove_member
# ---------------------------------------------------------------------


@pytest.mark.asyncio
async def test_cannot_remove_last_team_manager(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    async def _get_member(session, *, org_id, member_id):
        return _member(id=member_id)

    async def _is_owner(session, mid):
        return False

    async def _can_manage(session, mid):
        return True

    async def _count(session, org_id):
        return 1  # the target is the only manager left

    monkeypatch.setattr(service, "get_member", _get_member)
    monkeypatch.setattr(service, "_is_owner", _is_owner)
    monkeypatch.setattr(service, "_member_can_manage_team", _can_manage)
    monkeypatch.setattr(service, "_count_team_managers", _count)

    with pytest.raises(HTTPException) as exc:
        await service.remove_member(
            _Session(),
            actor_user_id=uuid.uuid4(),
            actor_member_id=uuid.uuid4(),
            org_id=uuid.uuid4(),
            member_id=uuid.uuid4(),
        )
    assert exc.value.status_code == 409


# ---------------------------------------------------------------------
#  Deactivate guards — set_member_status
# ---------------------------------------------------------------------


async def _active_member(session, *, org_id, member_id):
    return _member(id=member_id, status="active")


@pytest.mark.asyncio
async def test_cannot_deactivate_owner(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(service, "get_member_any_status", _active_member)

    async def _is_owner(session, mid):
        return True

    monkeypatch.setattr(service, "_is_owner", _is_owner)

    with pytest.raises(HTTPException) as exc:
        await service.set_member_status(
            _Session(),
            actor_user_id=uuid.uuid4(),
            actor_member_id=uuid.uuid4(),
            org_id=uuid.uuid4(),
            member_id=uuid.uuid4(),
            active=False,
        )
    assert exc.value.status_code == 409


@pytest.mark.asyncio
async def test_cannot_deactivate_self(monkeypatch: pytest.MonkeyPatch) -> None:
    me = uuid.uuid4()
    monkeypatch.setattr(service, "get_member_any_status", _active_member)

    async def _is_owner(session, mid):
        return False

    monkeypatch.setattr(service, "_is_owner", _is_owner)

    with pytest.raises(HTTPException) as exc:
        await service.set_member_status(
            _Session(),
            actor_user_id=uuid.uuid4(),
            actor_member_id=me,
            org_id=uuid.uuid4(),
            member_id=me,
            active=False,
        )
    assert exc.value.status_code == 409


# ---------------------------------------------------------------------
#  Ownership transfer
# ---------------------------------------------------------------------


@pytest.mark.asyncio
async def test_only_owner_can_transfer_ownership(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    async def _is_owner(session, mid):
        return False  # actor is NOT the owner

    monkeypatch.setattr(service, "_is_owner", _is_owner)

    with pytest.raises(NotAuthorized):
        await service.transfer_ownership(
            _Session(),
            actor_user_id=uuid.uuid4(),
            actor_member_id=uuid.uuid4(),
            org_id=uuid.uuid4(),
            new_owner_member_id=uuid.uuid4(),
        )


@pytest.mark.asyncio
async def test_cannot_transfer_ownership_to_self(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    me = uuid.uuid4()

    async def _is_owner(session, mid):
        return True

    monkeypatch.setattr(service, "_is_owner", _is_owner)

    with pytest.raises(HTTPException) as exc:
        await service.transfer_ownership(
            _Session(),
            actor_user_id=uuid.uuid4(),
            actor_member_id=me,
            org_id=uuid.uuid4(),
            new_owner_member_id=me,
        )
    assert exc.value.status_code == 409


@pytest.mark.asyncio
async def test_transfer_to_existing_owner_is_noop(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    async def _is_owner(session, mid):
        return True  # both actor and target already own

    async def _get_member(session, *, org_id, member_id):
        return _member(id=member_id)

    async def _boom(session, *, org_id, role_slug):
        raise RuntimeError("should not load roles for a no-op transfer")

    monkeypatch.setattr(service, "_is_owner", _is_owner)
    monkeypatch.setattr(service, "get_member", _get_member)
    monkeypatch.setattr(service, "_load_system_or_org_role", _boom)

    # Returns cleanly without mutating anything.
    result = await service.transfer_ownership(
        _Session(),
        actor_user_id=uuid.uuid4(),
        actor_member_id=uuid.uuid4(),
        org_id=uuid.uuid4(),
        new_owner_member_id=uuid.uuid4(),
    )
    assert result is None


@pytest.mark.asyncio
async def test_cannot_deactivate_last_manager(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(service, "get_member_any_status", _active_member)

    async def _is_owner(session, mid):
        return False

    async def _can_manage(session, mid):
        return True

    async def _count(session, org_id):
        return 1

    monkeypatch.setattr(service, "_is_owner", _is_owner)
    monkeypatch.setattr(service, "_member_can_manage_team", _can_manage)
    monkeypatch.setattr(service, "_count_team_managers", _count)

    with pytest.raises(HTTPException) as exc:
        await service.set_member_status(
            _Session(),
            actor_user_id=uuid.uuid4(),
            actor_member_id=uuid.uuid4(),
            org_id=uuid.uuid4(),
            member_id=uuid.uuid4(),
            active=False,
        )
    assert exc.value.status_code == 409
