"""Danger-zone service guards — reset & purge (pure logic, no DB).

The destructive row-deletion paths themselves are exercised live against
Postgres (see the CLAUDE.md verification notes); here we pin the cheap
invariants that must hold regardless of the database:

  - reset / purge refuse a missing or already-deleted org (404)
  - the preserve set keeps the workspace shell but never shields content
  - member_is_owner is null-safe and delegates to the owner check
"""

from __future__ import annotations

import uuid
from datetime import datetime, timezone
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from aicmo.modules.orgs import service


def _org_row(**overrides):
    org = MagicMock()
    org.id = overrides.get("id", uuid.uuid4())
    org.slug = overrides.get("slug", "acme")
    org.name = overrides.get("name", "Acme")
    org.status = overrides.get("status", "active")
    org.created_at = overrides.get("created_at", datetime.now(timezone.utc))
    return org


# ---------------------------------------------------------------------
#  Preserve-set invariants
# ---------------------------------------------------------------------


def test_preserve_set_keeps_workspace_shell() -> None:
    """The reset must NOT wipe the structural / billing / connection
    tables — otherwise it'd be a delete, not a reset."""
    keep = service.RESET_PRESERVE_TABLES
    for tbl in (
        "organizations",
        "organization_members",
        "roles",
        "brands",
        "subscription",
        "invoice",
        "integration_connection",
        "notification_preference",
        "audit_events",
    ):
        assert tbl in keep, f"{tbl} must survive a reset"


def test_preserve_set_never_shields_user_content() -> None:
    """Content the user provides / the AI generates MUST be wiped — so it
    must never sneak into the preserve set."""
    keep = service.RESET_PRESERVE_TABLES
    for tbl in (
        "business_profiles",
        "leads",
        "campaign_plans",
        "generated_content",
        "generated_ads",
        "generated_visuals",
        "creative_design",
        "video_render",
        "trend_reports",
        "learning_events",
    ):
        assert tbl not in keep, f"{tbl} must be cleared by a reset"


# ---------------------------------------------------------------------
#  reset_organization_data — guards
# ---------------------------------------------------------------------


@pytest.mark.asyncio
async def test_reset_404_on_deleted_org() -> None:
    from fastapi import HTTPException

    org = _org_row(status="deleted")
    session = MagicMock()
    session.get = AsyncMock(return_value=org)
    with patch(
        "aicmo.db.rls.set_bypass", new=AsyncMock()
    ), pytest.raises(HTTPException) as exc:
        await service.reset_organization_data(
            session, actor_user_id=uuid.uuid4(), org_id=org.id
        )
    assert exc.value.status_code == 404


@pytest.mark.asyncio
async def test_reset_404_when_missing() -> None:
    from fastapi import HTTPException

    session = MagicMock()
    session.get = AsyncMock(return_value=None)
    with patch(
        "aicmo.db.rls.set_bypass", new=AsyncMock()
    ), pytest.raises(HTTPException) as exc:
        await service.reset_organization_data(
            session, actor_user_id=uuid.uuid4(), org_id=uuid.uuid4()
        )
    assert exc.value.status_code == 404


# ---------------------------------------------------------------------
#  purge_organization — guards
# ---------------------------------------------------------------------


@pytest.mark.asyncio
async def test_purge_404_when_missing() -> None:
    from fastapi import HTTPException

    session = MagicMock()
    session.get = AsyncMock(return_value=None)
    with patch(
        "aicmo.db.rls.set_bypass", new=AsyncMock()
    ), pytest.raises(HTTPException) as exc:
        await service.purge_organization(
            session, actor_user_id=uuid.uuid4(), org_id=uuid.uuid4()
        )
    assert exc.value.status_code == 404


@pytest.mark.asyncio
async def test_purge_issues_cascade_delete_and_expunges() -> None:
    """Happy path: existing org → expunged from the identity map and a
    raw cascade DELETE executed against `organizations`."""
    org = _org_row()
    session = MagicMock()
    session.get = AsyncMock(return_value=org)
    session.expunge = MagicMock()
    session.execute = AsyncMock()
    with patch("aicmo.db.rls.set_bypass", new=AsyncMock()):
        await service.purge_organization(
            session, actor_user_id=uuid.uuid4(), org_id=org.id
        )
    session.expunge.assert_called_once_with(org)
    session.execute.assert_awaited_once()
    # The statement is a DELETE on organizations bound to this org id.
    sql = str(session.execute.await_args.args[0]).lower()
    assert "delete from organizations" in sql


# ---------------------------------------------------------------------
#  member_is_owner — null safety
# ---------------------------------------------------------------------


@pytest.mark.asyncio
async def test_member_is_owner_none_is_false() -> None:
    assert await service.member_is_owner(MagicMock(), None) is False


@pytest.mark.asyncio
async def test_member_is_owner_delegates() -> None:
    mid = uuid.uuid4()
    with patch(
        "aicmo.modules.orgs.service._is_owner",
        new=AsyncMock(return_value=True),
    ) as is_owner:
        assert await service.member_is_owner(MagicMock(), mid) is True
    is_owner.assert_awaited_once()
