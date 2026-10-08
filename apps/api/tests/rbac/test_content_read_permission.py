"""Phase 6.7 — the content.read permission gate.

The Creative Studio's brief + design READ routes require `content.read`
(aicmo/modules/creative/brief_router.py, aicmo/modules/creative/design/router.py).
That slug was never seeded, so owner/admin — who get "every permission" via a
CROSS JOIN over the catalog — still didn't have it, and every role was denied.

Migration 0080 seeds `content.read` and grants it to the content-capable roles
(owner, admin, marketing_manager, content_creator, designer, editor). These
tests pin:

  1. the enforcement contract — a member holding content.read is allowed, a
     member without it is denied (unauthorized users stay denied); and
  2. the migration intent — content.read is added to the catalog and granted to
     roles that already hold a content WRITE permission (least privilege).
"""

from __future__ import annotations

import uuid
from pathlib import Path

import pytest

from aicmo.tenancy.context import TenantContext
from aicmo.tenancy.dependencies import require_permission
from aicmo.tenancy.exceptions import NotAuthorized

_MIGRATION = (
    Path(__file__).resolve().parents[2]
    / "alembic"
    / "versions"
    / "0080_content_read_permission.py"
)


def _ctx(permissions: frozenset[str], *, role: str) -> TenantContext:
    return TenantContext(
        user_id="user_123",
        user_uuid=uuid.uuid4(),
        organization_id=uuid.uuid4(),
        brand_id=uuid.uuid4(),
        member_id=uuid.uuid4(),
        role_slugs=frozenset({role}),
        permissions=permissions,
    )


# --- enforcement ------------------------------------------------------------
@pytest.mark.asyncio
async def test_owner_with_content_read_is_allowed() -> None:
    """A member carrying content.read (owner, per migration 0080) passes the
    Creative Studio read gate and gets the tenant context back."""
    dep = require_permission("content.read")
    ctx = _ctx(
        frozenset({"content.create", "content.edit", "content.read"}),
        role="owner",
    )
    returned = await dep(tenant=ctx)
    assert returned is ctx


@pytest.mark.asyncio
async def test_member_without_content_read_is_denied() -> None:
    """A read-only member (e.g. viewer) that was NOT granted content.read is
    still denied — the gate is not a broad bypass."""
    dep = require_permission("content.read")
    ctx = _ctx(
        frozenset({"analytics.view", "library.view", "lead.view"}),
        role="viewer",
    )
    with pytest.raises(NotAuthorized) as ei:
        await dep(tenant=ctx)
    assert ei.value.status_code == 403
    assert "content.read" in ei.value.detail


# --- migration intent -------------------------------------------------------
def test_migration_seeds_content_read_into_the_catalog() -> None:
    src = _MIGRATION.read_text()
    assert "INSERT INTO permissions" in src
    assert "content.read" in src
    assert "'content'" in src  # seeded under the content category


def test_migration_grants_only_to_content_write_roles() -> None:
    """The grant is derived from roles that already hold a content WRITE
    permission — never a blanket grant to every role."""
    src = _MIGRATION.read_text()
    assert "content.create" in src
    assert "content.edit" in src
    assert "content.delete" in src
    # Derived from existing write grants, not a CROSS JOIN over all roles.
    assert "FROM role_permissions rp" in src
