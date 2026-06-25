"""TenantContext invariants — immutability + permission lookup.

The dataclass is `frozen=True` so the resolver can't be tricked into
mutating the bundle mid-request. These tests document and pin that.
"""

from __future__ import annotations

import dataclasses
import uuid

import pytest

from aicmo.tenancy.context import TenantContext


def _make(**over: object) -> TenantContext:
    defaults = dict(
        user_id="clerk_user_123",
        user_uuid=uuid.uuid4(),
        organization_id=uuid.uuid4(),
        brand_id=uuid.uuid4(),
        member_id=uuid.uuid4(),
        role_slugs=frozenset({"admin"}),
        permissions=frozenset({"content.create", "ads.create"}),
    )
    defaults.update(over)
    return TenantContext(**defaults)  # type: ignore[arg-type]


def test_has_permission_true_when_present() -> None:
    ctx = _make()
    assert ctx.has_permission("content.create") is True


def test_has_permission_false_when_absent() -> None:
    ctx = _make()
    assert ctx.has_permission("billing.manage") is False


def test_has_permission_false_on_empty_set() -> None:
    ctx = _make(permissions=frozenset())
    assert ctx.has_permission("content.create") is False


def test_context_is_frozen() -> None:
    ctx = _make()
    with pytest.raises(dataclasses.FrozenInstanceError):
        # Type-checker would also catch this — `# type: ignore` so the
        # runtime test still runs.
        ctx.organization_id = uuid.uuid4()  # type: ignore[misc]


def test_brand_id_can_be_none_for_org_routes() -> None:
    # Org-level endpoints (e.g. /api/v1/orgs/members) resolve with no brand.
    ctx = _make(brand_id=None)
    assert ctx.brand_id is None
    assert ctx.has_permission("content.create")


def test_permissions_are_a_set_not_a_list() -> None:
    # We rely on O(1) lookup. If this assertion fails, the slug-string
    # `in` check becomes O(n) per request.
    ctx = _make()
    assert isinstance(ctx.permissions, frozenset)
    assert isinstance(ctx.role_slugs, frozenset)
