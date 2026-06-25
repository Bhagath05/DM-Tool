"""Persona segmentation tests.

Persona is a NULLABLE business-profile field. NOT an authorization role
(those live in `member_roles`). Pinning:
  - schema accepts every documented value
  - schema rejects unknown values
  - persona is omitted when caller didn't send it
  - persona persists onto the BusinessProfile row when caller sent it
"""

from __future__ import annotations

import uuid
from typing import Any
from unittest.mock import AsyncMock, MagicMock

import pytest
from pydantic import ValidationError
from sqlalchemy.exc import IntegrityError  # noqa: F401

from aicmo.modules.brands.models import Brand
from aicmo.modules.onboarding.models import BusinessProfile
from aicmo.modules.orgs import service as orgs_service
from aicmo.modules.orgs.models import Organization, OrganizationMember
from aicmo.modules.orgs.schemas import OnboardingWorkspacePayload


def _payload(**over) -> OnboardingWorkspacePayload:
    base = dict(
        organization_name="Acme",
        organization_slug="acme",
        brand_name="Acme Main",
        brand_slug="acme-main",
        # Profile-bundle minimums so _maybe_create_business_profile fires.
        industry="Cafe",
        target_audience="Local urban professionals who care about quality.",
        brand_tone="friendly",
        primary_goal="leads",
        preferred_platforms=["instagram"],
    )
    base.update(over)
    return OnboardingWorkspacePayload(**base)


# ---------------------------------------------------------------------
#  Schema validation
# ---------------------------------------------------------------------


class TestPersonaSchemaAccepts:
    @pytest.mark.parametrize(
        "persona",
        [
            "solo_founder",
            "in_house_marketer",
            "agency",
            "freelancer",
            "consultant",
            "other",
        ],
    )
    def test_accepts_every_documented_persona(self, persona):
        p = _payload(persona=persona)
        assert p.persona == persona

    def test_persona_is_optional(self):
        p = _payload()  # no persona passed
        assert p.persona is None

    def test_explicit_none_is_allowed(self):
        p = _payload(persona=None)
        assert p.persona is None


class TestPersonaSchemaRejects:
    @pytest.mark.parametrize(
        "bad",
        [
            "Owner",  # auth role bleed
            "admin",  # auth role bleed
            "marketer",  # close but wrong (would-be typo of in_house_marketer)
            "Solo Founder",  # capitalised + space
            "agencyy",  # typo
            "",  # empty string is rejected — caller should pass None instead
            123,
        ],
    )
    def test_rejects_unknown_value(self, bad):
        with pytest.raises(ValidationError):
            _payload(persona=bad)


# ---------------------------------------------------------------------
#  Service pass-through (uses the same stub session as test_workspace_service)
# ---------------------------------------------------------------------


class _StubSession:
    """Records every add(); fakes execute() for the role lookup. Same
    shape as the stub in test_workspace_service.py, intentionally inline
    so this file stands alone."""

    def __init__(self, *, owner_role_id: uuid.UUID | None = None):
        self._owner_role_id = owner_role_id or uuid.uuid4()
        self.added: list[Any] = []
        self.flush_calls = 0
        self.rollback_called = False
        self.audit_calls: list[dict[str, Any]] = []

    def add(self, row: Any) -> None:
        if not hasattr(row, "id") or row.id is None:
            row.id = uuid.uuid4()
        self.added.append(row)

    async def flush(self) -> None:
        self.flush_calls += 1

    async def rollback(self) -> None:
        self.rollback_called = True

    async def execute(self, stmt: Any) -> Any:
        result = MagicMock()
        result.scalar_one.return_value = self._owner_role_id
        return result

    async def get(self, *_a, **_kw):
        return None


def _user():
    u = MagicMock()
    u.id = uuid.uuid4()
    u.clerk_user_id = "clerk_persona_test"
    u.display_name = None
    return u


@pytest.fixture(autouse=True)
def _stub_audit(monkeypatch):
    """audit_service.record is async I/O — stub it for these unit tests."""
    async def fake_record(_session, **_kw):
        return None

    monkeypatch.setattr(
        "aicmo.modules.orgs.service.audit_service.record", fake_record
    )


class TestPersonaPersists:
    @pytest.mark.asyncio
    async def test_persona_lands_on_business_profile_row(self):
        user = _user()
        session = _StubSession()
        await orgs_service.create_workspace(
            session=session,  # type: ignore[arg-type]
            actor_user=user,
            payload=_payload(persona="agency"),
        )
        profiles = [r for r in session.added if isinstance(r, BusinessProfile)]
        assert len(profiles) == 1
        assert profiles[0].persona == "agency"

    @pytest.mark.asyncio
    async def test_persona_is_none_when_caller_omitted_it(self):
        user = _user()
        session = _StubSession()
        await orgs_service.create_workspace(
            session=session,  # type: ignore[arg-type]
            actor_user=user,
            payload=_payload(),
        )
        profiles = [r for r in session.added if isinstance(r, BusinessProfile)]
        assert len(profiles) == 1
        assert profiles[0].persona is None

    @pytest.mark.asyncio
    async def test_no_business_profile_means_persona_is_irrelevant(self):
        """If the profile bundle is too sparse to create a BusinessProfile,
        persona doesn't get persisted anywhere — that's fine, the user
        can add it later via the business-profile edit endpoint."""
        user = _user()
        session = _StubSession()
        # Strip target_audience to suppress profile creation.
        await orgs_service.create_workspace(
            session=session,  # type: ignore[arg-type]
            actor_user=user,
            payload=_payload(persona="agency", target_audience=None),
        )
        profiles = [r for r in session.added if isinstance(r, BusinessProfile)]
        assert profiles == []
        # And the org + brand + member + member_role were still created.
        kinds = [type(r).__name__ for r in session.added]
        assert kinds == [
            "Organization",
            "Brand",
            "OrganizationMember",
            "MemberRole",
        ]


# ---------------------------------------------------------------------
#  Persona is NOT an auth role — defense in depth
# ---------------------------------------------------------------------


class TestPersonaIsNotAnAuthRole:
    def test_persona_cannot_be_a_role_slug(self):
        """Pinned: even though 'owner' is a real role slug elsewhere, the
        Persona literal must not accept it. Persona ∩ Role = ∅."""
        for role_slug in ("owner", "admin", "editor", "viewer"):
            with pytest.raises(ValidationError):
                _payload(persona=role_slug)

    @pytest.mark.asyncio
    async def test_persona_value_does_not_influence_role_assignment(self):
        """No matter what persona the user sends, they still get the
        'owner' role on the new org (because they created it). Persona
        and role are orthogonal."""
        user = _user()
        session = _StubSession()
        await orgs_service.create_workspace(
            session=session,  # type: ignore[arg-type]
            actor_user=user,
            payload=_payload(persona="freelancer"),
        )
        from aicmo.modules.orgs.models import MemberRole

        member_roles = [r for r in session.added if isinstance(r, MemberRole)]
        assert len(member_roles) == 1
        # role_id is the owner-role uuid the stub returned — caller can't
        # influence which role gets assigned via the persona field.
        assert member_roles[0].role_id == session._owner_role_id
