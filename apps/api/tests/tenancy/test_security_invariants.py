"""A5 security invariants — pin the trust-boundary guarantees in tests.

Each test name maps 1:1 to a numbered security guarantee in CLAUDE.md
§ "Multi-tenancy (A3)" + § "Tenant switcher UI (A4)". If you change
the resolver, you change one of these tests; if you change one of
these tests, you change the security guarantee. Don't break the chain.
"""

from __future__ import annotations

import uuid
from typing import Any
from unittest.mock import AsyncMock, MagicMock

import pytest

from aicmo.auth.clerk import AuthContext
from aicmo.tenancy.context import TenantContext
from aicmo.tenancy.dependencies import require_permission, require_tenant
from aicmo.tenancy.exceptions import (
    BrandNotInOrg,
    MissingTenant,
    NotAuthorized,
    OrganizationInactive,
    TenantMismatch,
)


# Reuse the lightweight stubs from the resolver smoke test. Keeping them
# inline (instead of importing) so this file is self-contained for an
# external auditor.


def _make_request(headers: dict[str, str]):
    request = MagicMock()
    request.headers.get.side_effect = lambda key: headers.get(key)
    return request


def _auth() -> AuthContext:
    return AuthContext(
        user_id="clerk_security_test",
        session_id=None,
        org_id=None,
        claims={"sub": "clerk_security_test"},
    )


def _stub_session(**kw: Any):
    """Inline copy of the resolver smoke test stub. See its docstring."""

    class S:
        def __init__(self):
            self._user_row = kw.get("user_row")
            self._member_row = kw.get("member_row")
            self._single_org_id = kw.get("single_org_id")
            self._only_brand_id = kw.get("only_brand_id")
            self._org_lookup = kw.get("org_lookup", {})
            self._brand_lookup = kw.get("brand_lookup", {})
            self._permissions = kw.get("permissions", set())
            self._role_slugs = kw.get("role_slugs", set())
            self.flush = AsyncMock()
            self.rollback = AsyncMock()
            self.add = MagicMock()

        async def execute(self, stmt):
            sql = str(stmt).lower()
            if "users" in sql and "clerk_user_id" in sql:
                return _result(scalar_one_or_none=self._user_row)
            if "organization_members" in sql and "select organization_members.organization_id" in sql:
                ids = [self._single_org_id] if self._single_org_id else []
                return _result(scalars_all=ids)
            if "organization_members" in sql and "user_id" in sql:
                return _result(scalar_one_or_none=self._member_row)
            if "brands" in sql and "select brands.id" in sql:
                ids = [self._only_brand_id] if self._only_brand_id else []
                return _result(scalars_all=ids)
            if "permissions.slug" in sql:
                return _result(scalars_all=list(self._permissions))
            if "roles.slug" in sql:
                return _result(scalars_all=list(self._role_slugs))
            return _result(scalar_one_or_none=None, scalars_all=[])

        async def get(self, model, id_):
            name = getattr(model, "__name__", str(model)).lower()
            if "organization" in name:
                return self._org_lookup.get(id_)
            if "brand" in name:
                return self._brand_lookup.get(id_)
            return None

    return S()


def _result(*, scalar_one_or_none=None, scalars_all=None):
    r = MagicMock()
    r.scalar_one_or_none.return_value = scalar_one_or_none
    r.scalars.return_value.all.return_value = scalars_all or []
    r.scalars.return_value.first.return_value = (
        scalars_all[0] if scalars_all else None
    )
    return r


def _row(**attrs):
    m = MagicMock()
    for k, v in attrs.items():
        setattr(m, k, v)
    return m


# =====================================================================
#  Guarantee #1: Users CANNOT access organizations outside memberships
# =====================================================================


class TestNoAccessOutsideMemberships:
    @pytest.mark.asyncio
    async def test_request_with_non_member_org_header_is_403(self):
        user_id = uuid.uuid4()
        user = _row(id=user_id, clerk_user_id="clerk_security_test", status="active")
        attacker_org = uuid.uuid4()

        session = _stub_session(
            user_row=user,
            member_row=None,  # not a member of attacker_org
            single_org_id=None,
        )
        request = _make_request({"X-Organization-Id": str(attacker_org)})

        with pytest.raises(TenantMismatch):
            await require_tenant()(
                request=request, auth=_auth(), session=session  # type: ignore[arg-type]
            )

    @pytest.mark.asyncio
    async def test_request_with_no_header_does_not_auto_grant_any_org(self):
        """If the user has 0 memberships, NO org may be auto-resolved."""
        user_id = uuid.uuid4()
        user = _row(id=user_id, clerk_user_id="clerk_security_test", status="active")

        session = _stub_session(
            user_row=user,
            member_row=None,
            single_org_id=None,  # zero memberships
        )
        request = _make_request({})  # no header

        with pytest.raises(MissingTenant):
            await require_tenant()(
                request=request, auth=_auth(), session=session  # type: ignore[arg-type]
            )


# =====================================================================
#  Guarantee #2: Users CANNOT access brands outside the active org
# =====================================================================


class TestNoCrossOrgBrandAccess:
    @pytest.mark.asyncio
    async def test_brand_from_a_different_org_is_403(self):
        user_id = uuid.uuid4()
        my_org = uuid.uuid4()
        other_org = uuid.uuid4()
        wrong_brand = uuid.uuid4()
        user = _row(id=user_id, clerk_user_id="clerk_security_test", status="active")
        member = _row(
            id=uuid.uuid4(),
            user_id=user_id,
            organization_id=my_org,
            status="active",
            last_active_brand_id=None,
        )
        org = _row(id=my_org, status="active")
        brand = _row(id=wrong_brand, organization_id=other_org, status="active")

        session = _stub_session(
            user_row=user,
            member_row=member,
            single_org_id=my_org,
            org_lookup={my_org: org},
            brand_lookup={wrong_brand: brand},
        )
        request = _make_request(
            {"X-Organization-Id": str(my_org), "X-Brand-Id": str(wrong_brand)}
        )

        with pytest.raises(BrandNotInOrg):
            await require_tenant()(
                request=request, auth=_auth(), session=session  # type: ignore[arg-type]
            )


# =====================================================================
#  Guarantee #3: Header tampering is rejected by backend
# =====================================================================


class TestHeaderTampering:
    @pytest.mark.asyncio
    async def test_garbage_org_header_is_400(self):
        session = _stub_session(
            user_row=_row(id=uuid.uuid4(), clerk_user_id="clerk_security_test", status="active"),
        )
        request = _make_request({"X-Organization-Id": "<script>alert(1)</script>"})

        with pytest.raises(MissingTenant) as exc:
            await require_tenant()(
                request=request, auth=_auth(), session=session  # type: ignore[arg-type]
            )
        assert "X-Organization-Id" in exc.value.detail

    @pytest.mark.asyncio
    async def test_garbage_brand_header_is_400(self):
        user_id = uuid.uuid4()
        my_org = uuid.uuid4()
        user = _row(id=user_id, clerk_user_id="clerk_security_test", status="active")
        member = _row(
            id=uuid.uuid4(),
            user_id=user_id,
            organization_id=my_org,
            status="active",
            last_active_brand_id=None,
        )

        session = _stub_session(
            user_row=user,
            member_row=member,
            single_org_id=my_org,
            org_lookup={my_org: _row(id=my_org, status="active")},
        )
        request = _make_request(
            {
                "X-Organization-Id": str(my_org),
                "X-Brand-Id": "../../etc/passwd",
            }
        )

        with pytest.raises(MissingTenant) as exc:
            await require_tenant()(
                request=request, auth=_auth(), session=session  # type: ignore[arg-type]
            )
        assert "X-Brand-Id" in exc.value.detail


# =====================================================================
#  Guarantee #4: Tenant isolation enforced at the dependency layer
# =====================================================================


class TestTenantIsolation:
    @pytest.mark.asyncio
    async def test_resolver_returns_only_the_active_brand_id(self):
        """The resolved TenantContext carries exactly ONE brand_id, not
        the user's full brand list. Downstream service code uses this
        one ID for filtering — never iterates `memberships`."""
        user_id = uuid.uuid4()
        org_id = uuid.uuid4()
        brand_id = uuid.uuid4()
        user = _row(id=user_id, clerk_user_id="clerk_security_test", status="active")
        member = _row(
            id=uuid.uuid4(),
            user_id=user_id,
            organization_id=org_id,
            status="active",
            last_active_brand_id=brand_id,
        )

        session = _stub_session(
            user_row=user,
            member_row=member,
            single_org_id=org_id,
            only_brand_id=brand_id,
            org_lookup={org_id: _row(id=org_id, status="active")},
            brand_lookup={
                brand_id: _row(id=brand_id, organization_id=org_id, status="active")
            },
            permissions={"content.create"},
            role_slugs={"editor"},
        )
        request = _make_request({})

        ctx = await require_tenant()(
            request=request, auth=_auth(), session=session  # type: ignore[arg-type]
        )
        assert ctx.brand_id == brand_id
        assert ctx.organization_id == org_id
        # No "all brands" attribute on the context — would be a leak.
        assert not hasattr(ctx, "all_brands")
        assert not hasattr(ctx, "memberships")


# =====================================================================
#  Guarantee #5: Role escalation is impossible from frontend
# =====================================================================


class TestNoRoleEscalation:
    @pytest.mark.asyncio
    async def test_permissions_come_from_db_not_request(self):
        """A request CANNOT set its own permissions. The resolver
        computes them server-side from MemberRole → RolePermission →
        Permission. No header / body field can influence the set."""
        user_id = uuid.uuid4()
        org_id = uuid.uuid4()
        brand_id = uuid.uuid4()
        user = _row(id=user_id, clerk_user_id="clerk_security_test", status="active")
        member = _row(
            id=uuid.uuid4(),
            user_id=user_id,
            organization_id=org_id,
            status="active",
            last_active_brand_id=brand_id,
        )

        session = _stub_session(
            user_row=user,
            member_row=member,
            single_org_id=org_id,
            only_brand_id=brand_id,
            org_lookup={org_id: _row(id=org_id, status="active")},
            brand_lookup={
                brand_id: _row(id=brand_id, organization_id=org_id, status="active")
            },
            permissions={"content.create"},  # DB says one perm
            role_slugs={"viewer"},
        )
        # Attacker tries to smuggle elevated perms via header.
        request = _make_request(
            {
                "X-Permissions": "billing.manage,owner.everything",
                "X-Role": "owner",
            }
        )

        ctx = await require_tenant()(
            request=request, auth=_auth(), session=session  # type: ignore[arg-type]
        )
        # Smuggled headers were ignored; perms reflect DB state.
        assert ctx.permissions == frozenset({"content.create"})
        assert ctx.role_slugs == frozenset({"viewer"})
        assert "billing.manage" not in ctx.permissions

    @pytest.mark.asyncio
    async def test_require_permission_blocks_when_db_denies(self):
        """Even if a viewer claims they need `billing.manage`, the
        permission check fails — proving the FE can't bypass."""
        user_id = uuid.uuid4()
        org_id = uuid.uuid4()
        brand_id = uuid.uuid4()
        user = _row(id=user_id, clerk_user_id="clerk_security_test", status="active")
        member = _row(
            id=uuid.uuid4(),
            user_id=user_id,
            organization_id=org_id,
            status="active",
            last_active_brand_id=brand_id,
        )

        session = _stub_session(
            user_row=user,
            member_row=member,
            single_org_id=org_id,
            only_brand_id=brand_id,
            org_lookup={org_id: _row(id=org_id, status="active")},
            brand_lookup={
                brand_id: _row(id=brand_id, organization_id=org_id, status="active")
            },
            permissions={"content.read"},  # viewer-style
            role_slugs={"viewer"},
        )

        tenant = await require_tenant()(
            request=_make_request({}), auth=_auth(), session=session  # type: ignore[arg-type]
        )

        with pytest.raises(NotAuthorized) as exc:
            await require_permission("billing.manage")(tenant=tenant)  # type: ignore[call-arg]

        assert "billing.manage" in str(exc.value.detail)


# =====================================================================
#  Guarantee #6: Tenant context survives refresh without privilege gain
# =====================================================================


class TestRefreshIntegrity:
    @pytest.mark.asyncio
    async def test_repeated_resolve_yields_same_permission_set(self):
        """Two resolves in a row (simulating page refresh) yield the
        SAME permissions. Front-end "refresh" can't re-prompt a higher
        permission set."""
        user_id = uuid.uuid4()
        org_id = uuid.uuid4()
        brand_id = uuid.uuid4()
        user = _row(id=user_id, clerk_user_id="clerk_security_test", status="active")
        member = _row(
            id=uuid.uuid4(),
            user_id=user_id,
            organization_id=org_id,
            status="active",
            last_active_brand_id=brand_id,
        )

        def fresh_session():
            return _stub_session(
                user_row=user,
                member_row=member,
                single_org_id=org_id,
                only_brand_id=brand_id,
                org_lookup={org_id: _row(id=org_id, status="active")},
                brand_lookup={
                    brand_id: _row(
                        id=brand_id, organization_id=org_id, status="active"
                    )
                },
                permissions={"content.create"},
                role_slugs={"editor"},
            )

        ctx_a: TenantContext = await require_tenant()(
            request=_make_request({}), auth=_auth(), session=fresh_session()  # type: ignore[arg-type]
        )
        ctx_b: TenantContext = await require_tenant()(
            request=_make_request({}), auth=_auth(), session=fresh_session()  # type: ignore[arg-type]
        )

        assert ctx_a.permissions == ctx_b.permissions
        assert ctx_a.role_slugs == ctx_b.role_slugs
        # Frozen — neither resolve produced a mutable bag.
        assert isinstance(ctx_a.permissions, frozenset)

    @pytest.mark.asyncio
    async def test_inactive_org_blocks_even_with_valid_cached_headers(self):
        """If the org is suspended between sign-in and the next request,
        cached headers from the frontend MUST NOT bypass the check."""
        user_id = uuid.uuid4()
        org_id = uuid.uuid4()
        user = _row(id=user_id, clerk_user_id="clerk_security_test", status="active")
        member = _row(
            id=uuid.uuid4(),
            user_id=user_id,
            organization_id=org_id,
            status="active",
            last_active_brand_id=None,
        )

        session = _stub_session(
            user_row=user,
            member_row=member,
            single_org_id=org_id,
            org_lookup={org_id: _row(id=org_id, status="suspended")},
        )
        request = _make_request({"X-Organization-Id": str(org_id)})

        with pytest.raises(OrganizationInactive):
            await require_tenant()(
                request=request, auth=_auth(), session=session  # type: ignore[arg-type]
            )
