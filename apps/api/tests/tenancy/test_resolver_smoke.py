"""A5 backend smoke tests — exercise `require_tenant` + `require_permission`.

These don't need a real Postgres; the resolver's surface is
`session.execute(...)` and `session.get(...)`, which we mock. The DB
layer is exercised by the integration suite (separate from A5 scope).

What we ARE proving here:
  - require_tenant rejects a request whose X-Organization-Id header
    refers to an org the user is NOT a member of (TenantMismatch / 403)
  - require_tenant rejects a malformed X-Organization-Id header (400)
  - require_tenant rejects a brand that doesn't belong to the active
    org (BrandNotInOrg / 403)
  - require_tenant rejects an inactive org (OrganizationInactive / 403)
  - require_tenant auto-resolves the org when the user has exactly one
    active membership (no header needed)
  - require_permission rejects when the resolved permission set doesn't
    contain the required slug (NotAuthorized / 403)
"""

from __future__ import annotations

import uuid
from typing import Any
from unittest.mock import AsyncMock, MagicMock

import pytest

from aicmo.auth.clerk import AuthContext
from aicmo.tenancy.dependencies import require_permission, require_tenant
from aicmo.tenancy.exceptions import (
    BrandNotInOrg,
    MissingTenant,
    NotAuthorized,
    OrganizationInactive,
    TenantMismatch,
)


# ---------------------------------------------------------------------
#  Fixture builders
# ---------------------------------------------------------------------


def _make_user(*, user_id: uuid.UUID | None = None) -> MagicMock:
    """User row stand-in."""
    user = MagicMock()
    user.id = user_id or uuid.uuid4()
    user.clerk_user_id = "clerk_test"
    user.email = "u@example.com"
    user.status = "active"
    return user


def _make_member(
    *,
    user_id: uuid.UUID,
    org_id: uuid.UUID,
    last_active_brand_id: uuid.UUID | None = None,
) -> MagicMock:
    member = MagicMock()
    member.id = uuid.uuid4()
    member.user_id = user_id
    member.organization_id = org_id
    member.status = "active"
    member.last_active_brand_id = last_active_brand_id
    return member


def _make_org(
    *, org_id: uuid.UUID | None = None, status: str = "active"
) -> MagicMock:
    org = MagicMock()
    org.id = org_id or uuid.uuid4()
    org.status = status
    return org


def _make_brand(
    *,
    brand_id: uuid.UUID | None = None,
    org_id: uuid.UUID,
    status: str = "active",
) -> MagicMock:
    brand = MagicMock()
    brand.id = brand_id or uuid.uuid4()
    brand.organization_id = org_id
    brand.status = status
    return brand


def _make_request(headers: dict[str, str]) -> MagicMock:
    """Stand-in for starlette.Request. Resolver only touches `.headers.get`."""
    request = MagicMock()
    request.headers.get.side_effect = lambda key: headers.get(key)
    return request


class _StubAsyncSession:
    """Just enough AsyncSession surface for the resolver.

    The resolver calls:
      - session.execute(stmt) → returns rows
      - session.get(Model, id) → returns ORM row or None
      - session.flush() → for `last_active_brand_id` updates

    Test-by-test we pre-seed the lookups by SQL string substring (cheap
    and clear) instead of by SQL-AST inspection.
    """

    def __init__(
        self,
        *,
        user_row: Any = None,
        member_row: Any = None,
        member_org_id: uuid.UUID | None = None,
        only_brand_id: uuid.UUID | None = None,
        single_org_id: uuid.UUID | None = None,
        org_lookup: dict[uuid.UUID, Any] | None = None,
        brand_lookup: dict[uuid.UUID, Any] | None = None,
        permissions: set[str] | None = None,
        role_slugs: set[str] | None = None,
    ):
        self._user_row = user_row
        self._member_row = member_row
        self._only_brand_id = only_brand_id
        self._single_org_id = single_org_id
        self._org_lookup = org_lookup or {}
        self._brand_lookup = brand_lookup or {}
        self._permissions = permissions or set()
        self._role_slugs = role_slugs or set()
        self.flush = AsyncMock()
        self.rollback = AsyncMock()
        self.add = MagicMock()

    async def execute(self, stmt: Any) -> Any:
        """Crude SQL-string match against the resolver's queries.
        Returns a result whose .scalar_one_or_none / .scalars().all()
        reflect what the resolver would expect from each query."""
        sql = str(stmt).lower()

        # _get_or_create_user → SELECT user
        if "users" in sql and "clerk_user_id" in sql:
            return _result(scalar_one_or_none=self._user_row)

        # _single_active_membership_org → SELECT org_id from members
        if "organization_members" in sql and "organization_id" in sql and "select organization_members.organization_id" in sql:
            ids = [self._single_org_id] if self._single_org_id else []
            return _result(scalars_all=ids)

        # _load_active_member → SELECT member
        if "organization_members" in sql and "user_id" in sql:
            return _result(scalar_one_or_none=self._member_row)

        # _only_active_brand → SELECT brand id
        if "brands" in sql and "select brands.id" in sql:
            ids = [self._only_brand_id] if self._only_brand_id else []
            return _result(scalars_all=ids)

        # permissions / role lookups
        if "permissions.slug" in sql:
            return _result(scalars_all=list(self._permissions))
        if "roles.slug" in sql:
            return _result(scalars_all=list(self._role_slugs))

        # Fallback — return empty.
        return _result(scalar_one_or_none=None, scalars_all=[])

    async def get(self, model: Any, id_: uuid.UUID) -> Any:
        name = getattr(model, "__name__", str(model)).lower()
        if "organization" in name:
            return self._org_lookup.get(id_)
        if "brand" in name:
            return self._brand_lookup.get(id_)
        return None


def _result(
    *,
    scalar_one_or_none: Any = None,
    scalars_all: list[Any] | None = None,
) -> Any:
    r = MagicMock()
    r.scalar_one_or_none.return_value = scalar_one_or_none
    r.scalars.return_value.all.return_value = scalars_all or []
    r.scalars.return_value.first.return_value = (
        scalars_all[0] if scalars_all else None
    )
    return r


def _auth(*, clerk_user_id: str = "clerk_test") -> AuthContext:
    return AuthContext(
        user_id=clerk_user_id,
        session_id=None,
        org_id=None,
        claims={"sub": clerk_user_id},
    )


# ---------------------------------------------------------------------
#  require_tenant
# ---------------------------------------------------------------------


class TestRequireTenantSuccess:
    @pytest.mark.asyncio
    async def test_auto_resolves_single_membership_with_single_brand(self):
        user_id = uuid.uuid4()
        org_id = uuid.uuid4()
        brand_id = uuid.uuid4()
        user = _make_user(user_id=user_id)
        member = _make_member(user_id=user_id, org_id=org_id)
        org = _make_org(org_id=org_id)
        brand = _make_brand(brand_id=brand_id, org_id=org_id)

        session = _StubAsyncSession(
            user_row=user,
            member_row=member,
            single_org_id=org_id,
            only_brand_id=brand_id,
            org_lookup={org_id: org},
            brand_lookup={brand_id: brand},
            permissions={"content.create"},
            role_slugs={"admin"},
        )
        request = _make_request({})  # NO headers — auto-resolve must work
        dep = require_tenant()

        ctx = await dep(
            request=request, auth=_auth(), session=session  # type: ignore[arg-type]
        )

        assert ctx.organization_id == org_id
        assert ctx.brand_id == brand_id
        assert "content.create" in ctx.permissions
        assert "admin" in ctx.role_slugs


class TestRequireTenantRejections:
    @pytest.mark.asyncio
    async def test_rejects_when_user_is_not_a_member_of_requested_org(self):
        """Header tampering simulation: user crafts a request with an
        org id they're NOT a member of. Resolver's _load_active_member
        returns None → TenantMismatch (403)."""
        user_id = uuid.uuid4()
        attacker_org = uuid.uuid4()
        user = _make_user(user_id=user_id)

        session = _StubAsyncSession(
            user_row=user,
            member_row=None,  # ← user is not a member of attacker_org
            single_org_id=None,  # no auto-resolve fallback
            permissions=set(),
            role_slugs=set(),
        )
        request = _make_request({"X-Organization-Id": str(attacker_org)})
        dep = require_tenant()

        with pytest.raises(TenantMismatch):
            await dep(
                request=request, auth=_auth(), session=session  # type: ignore[arg-type]
            )

    @pytest.mark.asyncio
    async def test_rejects_malformed_org_header(self):
        """Header parser raises before the DB is touched."""
        user_id = uuid.uuid4()
        user = _make_user(user_id=user_id)
        session = _StubAsyncSession(user_row=user)
        request = _make_request({"X-Organization-Id": "not-a-uuid"})
        dep = require_tenant()

        with pytest.raises(MissingTenant) as exc:
            await dep(
                request=request, auth=_auth(), session=session  # type: ignore[arg-type]
            )
        assert "X-Organization-Id" in exc.value.detail

    @pytest.mark.asyncio
    async def test_rejects_brand_not_in_org(self):
        """Brand from a DIFFERENT org passed in the header."""
        user_id = uuid.uuid4()
        org_id = uuid.uuid4()
        other_org_id = uuid.uuid4()
        wrong_brand_id = uuid.uuid4()
        user = _make_user(user_id=user_id)
        member = _make_member(user_id=user_id, org_id=org_id)
        org = _make_org(org_id=org_id)
        wrong_brand = _make_brand(brand_id=wrong_brand_id, org_id=other_org_id)

        session = _StubAsyncSession(
            user_row=user,
            member_row=member,
            org_lookup={org_id: org},
            brand_lookup={wrong_brand_id: wrong_brand},
            single_org_id=org_id,
        )
        request = _make_request(
            {
                "X-Organization-Id": str(org_id),
                "X-Brand-Id": str(wrong_brand_id),
            }
        )
        dep = require_tenant()

        with pytest.raises(BrandNotInOrg):
            await dep(
                request=request, auth=_auth(), session=session  # type: ignore[arg-type]
            )

    @pytest.mark.asyncio
    async def test_rejects_inactive_organization(self):
        """Org deactivated mid-session — next request must 403."""
        user_id = uuid.uuid4()
        org_id = uuid.uuid4()
        user = _make_user(user_id=user_id)
        member = _make_member(user_id=user_id, org_id=org_id)
        inactive_org = _make_org(org_id=org_id, status="suspended")

        session = _StubAsyncSession(
            user_row=user,
            member_row=member,
            org_lookup={org_id: inactive_org},
            single_org_id=org_id,
        )
        request = _make_request({"X-Organization-Id": str(org_id)})
        dep = require_tenant()

        with pytest.raises(OrganizationInactive):
            await dep(
                request=request, auth=_auth(), session=session  # type: ignore[arg-type]
            )


# ---------------------------------------------------------------------
#  require_permission
# ---------------------------------------------------------------------


class TestRequirePermission:
    @pytest.mark.asyncio
    async def test_rejects_when_permission_slug_missing(self):
        """Caller has 'content.create' but route requires 'billing.manage'."""
        user_id = uuid.uuid4()
        org_id = uuid.uuid4()
        brand_id = uuid.uuid4()
        user = _make_user(user_id=user_id)
        member = _make_member(user_id=user_id, org_id=org_id)
        org = _make_org(org_id=org_id)
        brand = _make_brand(brand_id=brand_id, org_id=org_id)

        session = _StubAsyncSession(
            user_row=user,
            member_row=member,
            single_org_id=org_id,
            only_brand_id=brand_id,
            org_lookup={org_id: org},
            brand_lookup={brand_id: brand},
            permissions={"content.create"},  # ← does NOT include billing.manage
            role_slugs={"editor"},
        )
        request = _make_request({})
        dep = require_permission("billing.manage")

        with pytest.raises(NotAuthorized) as exc:
            # require_permission composes require_tenant — invoke through
            # the inner async fn.
            tenant_dep = require_tenant()
            tenant = await tenant_dep(
                request=request, auth=_auth(), session=session  # type: ignore[arg-type]
            )
            await dep(tenant=tenant)  # type: ignore[call-arg]

        assert "billing.manage" in str(exc.value.detail)

    @pytest.mark.asyncio
    async def test_allows_when_slug_present(self):
        user_id = uuid.uuid4()
        org_id = uuid.uuid4()
        brand_id = uuid.uuid4()
        user = _make_user(user_id=user_id)
        member = _make_member(user_id=user_id, org_id=org_id)
        org = _make_org(org_id=org_id)
        brand = _make_brand(brand_id=brand_id, org_id=org_id)

        session = _StubAsyncSession(
            user_row=user,
            member_row=member,
            single_org_id=org_id,
            only_brand_id=brand_id,
            org_lookup={org_id: org},
            brand_lookup={brand_id: brand},
            permissions={"content.create", "billing.manage"},
            role_slugs={"owner"},
        )
        request = _make_request({})

        tenant_dep = require_tenant()
        tenant = await tenant_dep(
            request=request, auth=_auth(), session=session  # type: ignore[arg-type]
        )
        # Should not raise.
        dep = require_permission("billing.manage")
        result = await dep(tenant=tenant)  # type: ignore[call-arg]
        assert result.has_permission("billing.manage")
