"""Backend service tests for W1-15 — create_workspace.

Covers the brief's four backend requirements:
  1. Transaction success — full happy path returns the expected result
  2. Transaction rollback — duplicate org slug → 409 + rollback called
  3. Duplicate slug handling — both org-slug and brand-slug paths
  4. Owner assignment — system 'owner' role gets attached to the member

The async-session is stubbed (no Postgres yet — see A5 limitations doc).
What we assert is the EXACT sequence the service executes:
  user.display_name update
  → Organization insert + flush
  → Brand insert + flush
  → OrganizationMember insert + flush
  → Role lookup
  → MemberRole insert + flush
  → 3 audit records
"""

from __future__ import annotations

import uuid
from typing import Any
from unittest.mock import AsyncMock, MagicMock

import pytest
from fastapi import HTTPException
from sqlalchemy.exc import IntegrityError

from aicmo.modules.brands.models import Brand
from aicmo.modules.orgs import service as orgs_service
from aicmo.modules.orgs.models import MemberRole, Organization, OrganizationMember
from aicmo.modules.orgs.schemas import OnboardingWorkspacePayload


# ---------------------------------------------------------------------
#  Fixture builders — keep these tiny + obvious so test diffs are clear
# ---------------------------------------------------------------------


def _user(*, display_name: str | None = None) -> MagicMock:
    u = MagicMock()
    u.id = uuid.uuid4()
    u.clerk_user_id = "clerk_wiz_test"
    u.display_name = display_name
    return u


def _payload(**over) -> OnboardingWorkspacePayload:
    base = dict(
        organization_name="Acme",
        organization_slug="acme",
        brand_name="Acme Main",
        brand_slug="acme-main",
        display_name="Jane Doe",
    )
    base.update(over)
    return OnboardingWorkspacePayload(**base)


class _StubSession:
    """Records every add(); fakes execute() for the role lookup.

    Each add() assigns a fresh UUID `.id` to the row so the service can
    keep flowing. We DON'T pretend to enforce the unique constraints
    here — the specific failure tests inject IntegrityError on the right
    flush() call.
    """

    def __init__(self, *, owner_role_id: uuid.UUID | None = None):
        self._owner_role_id = owner_role_id or uuid.uuid4()
        self.added: list[Any] = []
        self.flush_calls = 0
        self.rollback_called = False
        self.commit_called = False
        # When set, the Nth flush() raises IntegrityError.
        self.fail_on_flush: int | None = None
        # Captured audit records via the audit_service stub.
        self.audit_calls: list[dict[str, Any]] = []

    def add(self, row: Any) -> None:
        if not hasattr(row, "id") or row.id is None:
            row.id = uuid.uuid4()
        self.added.append(row)

    async def flush(self) -> None:
        self.flush_calls += 1
        if self.fail_on_flush == self.flush_calls:
            raise IntegrityError("statement", {}, Exception("duplicate"))

    async def rollback(self) -> None:
        self.rollback_called = True

    async def commit(self) -> None:
        self.commit_called = True

    async def execute(self, stmt: Any) -> Any:
        # Only one execute the service runs synchronously: owner role lookup.
        result = MagicMock()
        result.scalar_one.return_value = self._owner_role_id
        return result

    async def get(self, *_a, **_kw):
        return None


@pytest.fixture(autouse=True)
def _stub_audit(monkeypatch):
    """Replace audit_service.record with a recorder so we can assert
    which audit events fired without dragging a real audit table in."""
    calls: list[dict[str, Any]] = []

    async def fake_record(_session, **kw):
        calls.append(kw)

    monkeypatch.setattr(
        "aicmo.modules.orgs.service.audit_service.record",
        fake_record,
    )
    return calls


# ---------------------------------------------------------------------
#  Transaction success
# ---------------------------------------------------------------------


class TestTransactionSuccess:
    @pytest.mark.asyncio
    async def test_full_happy_path(self, _stub_audit):
        user = _user(display_name=None)
        session = _StubSession()

        result = await orgs_service.create_workspace(
            session=session,  # type: ignore[arg-type]
            actor_user=user,
            payload=_payload(),
        )

        # Result shape
        assert result.organization_slug == "acme"
        assert result.brand_slug == "acme-main"
        assert result.role_slugs == ["owner"]

        # Display name was set on the user
        assert user.display_name == "Jane Doe"

        # Row sequence is exactly: Organization, Brand, OrganizationMember, MemberRole
        kinds = [type(r).__name__ for r in session.added]
        assert kinds == [
            "Organization",
            "Brand",
            "OrganizationMember",
            "MemberRole",
        ]

        # 4 flushes (one per add) — no failures.
        assert session.flush_calls == 4
        assert session.rollback_called is False

    @pytest.mark.asyncio
    async def test_display_name_optional(self, _stub_audit):
        user = _user(display_name="Existing Name")
        session = _StubSession()

        await orgs_service.create_workspace(
            session=session,  # type: ignore[arg-type]
            actor_user=user,
            payload=_payload(display_name=None),
        )
        # Display name untouched when payload omitted it.
        assert user.display_name == "Existing Name"

    @pytest.mark.asyncio
    async def test_emits_three_audit_events(self, _stub_audit):
        user = _user()
        session = _StubSession()

        await orgs_service.create_workspace(
            session=session,  # type: ignore[arg-type]
            actor_user=user,
            payload=_payload(),
        )

        actions = [c["action"] for c in _stub_audit]
        assert actions == [
            "organization.created",
            "brand.created",
            "member.role_assigned",
        ]
        # All three carry the same actor + tagged with the via marker.
        for c in _stub_audit:
            assert c["actor_user_id"] == user.id
            assert c["after"].get("via") == "onboarding_wizard"


# ---------------------------------------------------------------------
#  Transaction rollback — duplicate slug paths
# ---------------------------------------------------------------------


class TestTransactionRollback:
    @pytest.mark.asyncio
    async def test_duplicate_org_slug_rolls_back_and_returns_409(self, _stub_audit):
        user = _user()
        session = _StubSession()
        # Org flush is the FIRST flush. Make it raise IntegrityError.
        session.fail_on_flush = 1

        with pytest.raises(HTTPException) as exc:
            await orgs_service.create_workspace(
                session=session,  # type: ignore[arg-type]
                actor_user=user,
                payload=_payload(organization_slug="taken"),
            )

        assert exc.value.status_code == 409
        assert "taken" in exc.value.detail.lower() or "already taken" in exc.value.detail
        assert session.rollback_called is True

        # Brand / member / member_role were NEVER added because we
        # bailed at the first flush.
        kinds = [type(r).__name__ for r in session.added]
        assert "Brand" not in kinds
        assert "OrganizationMember" not in kinds
        assert "MemberRole" not in kinds

        # No audit events for a failed create.
        assert _stub_audit == []

    @pytest.mark.asyncio
    async def test_duplicate_brand_slug_rolls_back_and_returns_409(
        self, _stub_audit
    ):
        user = _user()
        session = _StubSession()
        # Org flush succeeds (1st), brand flush fails (2nd).
        session.fail_on_flush = 2

        with pytest.raises(HTTPException) as exc:
            await orgs_service.create_workspace(
                session=session,  # type: ignore[arg-type]
                actor_user=user,
                payload=_payload(),
            )

        assert exc.value.status_code == 409
        assert "brand" in exc.value.detail.lower()
        assert session.rollback_called is True

        # Member / member_role NEVER added.
        kinds = [type(r).__name__ for r in session.added]
        assert kinds == ["Organization", "Brand"]
        assert "OrganizationMember" not in kinds


# ---------------------------------------------------------------------
#  Owner role assignment
# ---------------------------------------------------------------------


class TestOwnerAssignment:
    @pytest.mark.asyncio
    async def test_owner_role_id_pulled_from_db(self, _stub_audit):
        owner_role_id = uuid.uuid4()
        user = _user()
        session = _StubSession(owner_role_id=owner_role_id)

        await orgs_service.create_workspace(
            session=session,  # type: ignore[arg-type]
            actor_user=user,
            payload=_payload(),
        )

        # The MemberRole row should carry the resolved owner role id.
        member_roles = [r for r in session.added if isinstance(r, MemberRole)]
        assert len(member_roles) == 1
        assert member_roles[0].role_id == owner_role_id
        # And assigned_by points at the caller (self-assignment is
        # legitimate during onboarding because the user is the org owner).
        assert member_roles[0].assigned_by_user_id == user.id

    @pytest.mark.asyncio
    async def test_member_links_to_first_brand(self, _stub_audit):
        user = _user()
        session = _StubSession()

        await orgs_service.create_workspace(
            session=session,  # type: ignore[arg-type]
            actor_user=user,
            payload=_payload(),
        )

        # The OrganizationMember row's last_active_brand_id is the brand
        # we just created — so the user lands in that brand immediately
        # on first /me without sending a brand header.
        brands = [r for r in session.added if isinstance(r, Brand)]
        members = [r for r in session.added if isinstance(r, OrganizationMember)]
        assert len(brands) == 1
        assert len(members) == 1
        assert members[0].last_active_brand_id == brands[0].id

    @pytest.mark.asyncio
    async def test_org_owner_user_id_matches_caller(self, _stub_audit):
        user = _user()
        session = _StubSession()

        await orgs_service.create_workspace(
            session=session,  # type: ignore[arg-type]
            actor_user=user,
            payload=_payload(),
        )

        orgs = [r for r in session.added if isinstance(r, Organization)]
        assert len(orgs) == 1
        # owner_user_id MUST equal the caller — pins the security
        # invariant that "the wizard always grants Owner to the
        # authenticated user, not someone else".
        assert orgs[0].owner_user_id == user.id
