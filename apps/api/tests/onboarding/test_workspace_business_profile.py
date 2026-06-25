"""A4 backend tests — combined org+brand+business-profile creation.

Adds coverage for the new conditional INSERT in `create_workspace`.
Reuses the same stubbed AsyncSession pattern as test_workspace_service.

What's pinned:
  - Full payload → BusinessProfile IS inserted (5 rows total: Org, Brand,
    Member, MemberRole, BusinessProfile)
  - Profile is brand-scoped (brand_id + organization_id set)
  - Single `primary_goal` becomes `goals=[primary_goal]` on the model
  - Audit event fires for business_profile.created
  - Minimum-only payload → profile is SKIPPED (4 rows, no BusinessProfile)
  - Specific missing fields skip profile creation:
      * blank industry
      * target_audience < 10 chars
      * blank brand_tone
      * blank primary_goal
      * empty preferred_platforms
"""

from __future__ import annotations

import uuid
from typing import Any
from unittest.mock import AsyncMock, MagicMock

import pytest

from aicmo.modules.onboarding.models import BusinessProfile
from aicmo.modules.orgs import service as orgs_service
from aicmo.modules.orgs.models import MemberRole, Organization, OrganizationMember
from aicmo.modules.orgs.schemas import OnboardingWorkspacePayload
from aicmo.modules.brands.models import Brand


# ---------------------------------------------------------------------
#  Fixture builders — keep identical to test_workspace_service.py so
#  failures are diffable across both files.
# ---------------------------------------------------------------------


def _user() -> MagicMock:
    u = MagicMock()
    u.id = uuid.uuid4()
    u.clerk_user_id = "clerk_a4_test"
    u.display_name = None
    return u


def _full_payload(**over) -> OnboardingWorkspacePayload:
    base = dict(
        organization_name="Acme",
        organization_slug="acme",
        brand_name="Acme Espresso",
        brand_slug="acme-espresso",
        display_name=None,
        industry="Cafe / Restaurant",
        website="https://acme.example",
        brand_description="Specialty coffee for office mornings",
        target_audience="Young professionals who buy coffee on the way to work",
        primary_goal="leads",
        preferred_platforms=["instagram", "google"],
        brand_tone="friendly",
    )
    base.update(over)
    return OnboardingWorkspacePayload(**base)


def _minimum_payload(**over) -> OnboardingWorkspacePayload:
    """Just the workspace required fields — no business profile data."""
    base = dict(
        organization_name="Acme",
        organization_slug="acme",
        brand_name="Acme Espresso",
        brand_slug="acme-espresso",
    )
    base.update(over)
    return OnboardingWorkspacePayload(**base)


class _StubSession:
    """Same shape as test_workspace_service.py's stub."""

    def __init__(self, *, owner_role_id: uuid.UUID | None = None):
        self._owner_role_id = owner_role_id or uuid.uuid4()
        self.added: list[Any] = []
        self.flush_calls = 0
        self.rollback_called = False
        self.commit_called = False
        self.fail_on_flush: int | None = None

    def add(self, row: Any) -> None:
        if not hasattr(row, "id") or row.id is None:
            row.id = uuid.uuid4()
        self.added.append(row)

    async def flush(self) -> None:
        self.flush_calls += 1

    async def rollback(self) -> None:
        self.rollback_called = True

    async def commit(self) -> None:
        self.commit_called = True

    async def execute(self, stmt: Any) -> Any:
        result = MagicMock()
        result.scalar_one.return_value = self._owner_role_id
        return result

    async def get(self, *_a, **_kw):
        return None


@pytest.fixture(autouse=True)
def _stub_audit(monkeypatch):
    """Replace audit_service.record with a recorder."""
    calls: list[dict[str, Any]] = []

    async def fake_record(_session, **kw):
        calls.append(kw)

    monkeypatch.setattr(
        "aicmo.modules.orgs.service.audit_service.record",
        fake_record,
    )
    return calls


# ---------------------------------------------------------------------
#  Full payload → BusinessProfile IS created
# ---------------------------------------------------------------------


class TestFullPayloadCreatesProfile:
    @pytest.mark.asyncio
    async def test_business_profile_inserted_alongside_workspace(self, _stub_audit):
        user = _user()
        session = _StubSession()

        await orgs_service.create_workspace(
            session=session,  # type: ignore[arg-type]
            actor_user=user,
            payload=_full_payload(),
        )

        kinds = [type(r).__name__ for r in session.added]
        assert kinds == [
            "Organization",
            "Brand",
            "OrganizationMember",
            "MemberRole",
            "BusinessProfile",
        ]

    @pytest.mark.asyncio
    async def test_profile_is_brand_scoped(self, _stub_audit):
        user = _user()
        session = _StubSession()

        await orgs_service.create_workspace(
            session=session,  # type: ignore[arg-type]
            actor_user=user,
            payload=_full_payload(),
        )

        orgs = [r for r in session.added if isinstance(r, Organization)]
        brands = [r for r in session.added if isinstance(r, Brand)]
        profiles = [r for r in session.added if isinstance(r, BusinessProfile)]
        assert len(profiles) == 1
        assert profiles[0].brand_id == brands[0].id
        assert profiles[0].organization_id == orgs[0].id

    @pytest.mark.asyncio
    async def test_primary_goal_becomes_goals_list(self, _stub_audit):
        user = _user()
        session = _StubSession()

        await orgs_service.create_workspace(
            session=session,  # type: ignore[arg-type]
            actor_user=user,
            payload=_full_payload(primary_goal="awareness"),
        )

        profile = next(r for r in session.added if isinstance(r, BusinessProfile))
        assert profile.goals == ["awareness"]
        assert profile.primary_goal_text == "awareness"

    @pytest.mark.asyncio
    async def test_audit_event_fires_for_business_profile_create(self, _stub_audit):
        user = _user()
        session = _StubSession()

        await orgs_service.create_workspace(
            session=session,  # type: ignore[arg-type]
            actor_user=user,
            payload=_full_payload(),
        )

        actions = [c["action"] for c in _stub_audit]
        assert actions == [
            "organization.created",
            "brand.created",
            "member.role_assigned",
            "business_profile.created",
        ]


# ---------------------------------------------------------------------
#  Minimum payload → profile skipped, workspace still succeeds
# ---------------------------------------------------------------------


class TestMinimumPayloadSkipsProfile:
    @pytest.mark.asyncio
    async def test_minimum_payload_creates_no_profile(self, _stub_audit):
        user = _user()
        session = _StubSession()

        result = await orgs_service.create_workspace(
            session=session,  # type: ignore[arg-type]
            actor_user=user,
            payload=_minimum_payload(),
        )

        kinds = [type(r).__name__ for r in session.added]
        assert "BusinessProfile" not in kinds
        # And workspace creation otherwise succeeded.
        assert result.brand_id is not None

    @pytest.mark.asyncio
    async def test_minimum_payload_emits_only_three_audit_events(
        self, _stub_audit
    ):
        user = _user()
        session = _StubSession()

        await orgs_service.create_workspace(
            session=session,  # type: ignore[arg-type]
            actor_user=user,
            payload=_minimum_payload(),
        )

        actions = [c["action"] for c in _stub_audit]
        # business_profile.created is absent.
        assert actions == [
            "organization.created",
            "brand.created",
            "member.role_assigned",
        ]


# ---------------------------------------------------------------------
#  Specific missing fields → profile skipped
# ---------------------------------------------------------------------


class TestPartialPayloadSkipsProfile:
    @pytest.mark.asyncio
    @pytest.mark.parametrize(
        "missing_field,override",
        [
            ("industry", {"industry": ""}),
            ("industry-none", {"industry": None}),
            ("target_audience-too-short", {"target_audience": "short"}),
            ("target_audience-blank", {"target_audience": ""}),
            ("brand_tone", {"brand_tone": ""}),
            ("primary_goal", {"primary_goal": ""}),
            ("preferred_platforms-empty", {"preferred_platforms": []}),
            ("preferred_platforms-blanks", {"preferred_platforms": ["", "  "]}),
        ],
    )
    async def test_missing_field_skips_profile(
        self, _stub_audit, missing_field, override
    ):
        user = _user()
        session = _StubSession()

        await orgs_service.create_workspace(
            session=session,  # type: ignore[arg-type]
            actor_user=user,
            payload=_full_payload(**override),
        )

        kinds = [type(r).__name__ for r in session.added]
        assert "BusinessProfile" not in kinds, (
            f"Expected no BusinessProfile when {missing_field} is missing, "
            f"but service inserted one anyway"
        )


# ---------------------------------------------------------------------
#  Sanity: existing W1-15 tests still pass shape
# ---------------------------------------------------------------------


class TestBackwardCompat:
    @pytest.mark.asyncio
    async def test_old_w1_15_shape_still_works(self, _stub_audit):
        """The W1-15 wizard sent {org_name, org_slug, brand_name, brand_slug,
        display_name}. A4 added optional fields. Old payload must still
        produce a working (4-row) create."""
        user = _user()
        session = _StubSession()

        payload = OnboardingWorkspacePayload(
            organization_name="Acme",
            organization_slug="acme",
            brand_name="Acme Main",
            brand_slug="acme-main",
            display_name="Jane Doe",
        )
        await orgs_service.create_workspace(
            session=session,  # type: ignore[arg-type]
            actor_user=user,
            payload=payload,
        )

        assert user.display_name == "Jane Doe"
        kinds = [type(r).__name__ for r in session.added]
        assert kinds == [
            "Organization",
            "Brand",
            "OrganizationMember",
            "MemberRole",
        ]
