"""Phase 10.2f — Org profile service logic (no DB).

Pin the pure-logic invariants of `update_org_profile`:

  - exclude_unset: absent keys leave fields unchanged
  - empty-string clears (→ NULL) for nullable fields
  - cannot clear `name` (it's required)
  - audit row only fires when something actually changed
  - 404 on unknown / deleted org

Full DB-backed paths (get_org_analytics joining audit_events +
organization_invite) get exercised in 10.2f-7 via the running app.
"""

from __future__ import annotations

import uuid
from datetime import datetime, timezone
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from aicmo.modules.orgs import service
from aicmo.modules.orgs.schemas import OrganizationProfileUpdate


def _org_row(**overrides):
    org = MagicMock()
    org.id = overrides.get("id", uuid.uuid4())
    org.slug = overrides.get("slug", "acme")
    org.name = overrides.get("name", "Acme")
    org.owner_user_id = overrides.get("owner_user_id", uuid.uuid4())
    org.status = overrides.get("status", "active")
    org.member_count = overrides.get("member_count", 1)
    org.brand_count = overrides.get("brand_count", 1)
    org.created_at = overrides.get("created_at", datetime.now(timezone.utc))
    org.updated_at = overrides.get("updated_at", datetime.now(timezone.utc))
    org.logo_url = overrides.get("logo_url", None)
    org.website = overrides.get("website", None)
    org.industry = overrides.get("industry", None)
    org.timezone = overrides.get("timezone", None)
    org.country = overrides.get("country", None)
    return org


def _session_with(org):
    """Build a MagicMock session whose `.get(Organization, id)` returns
    the given org (or None for deleted/missing) and that pretends to
    flush without error."""
    session = MagicMock()
    session.get = AsyncMock(return_value=org)
    session.flush = AsyncMock(return_value=None)
    return session


# ---------------------------------------------------------------------
#  update_org_profile — empty-string + exclude_unset semantics
# ---------------------------------------------------------------------


@pytest.mark.asyncio
async def test_update_profile_empty_string_clears_to_null() -> None:
    org = _org_row(industry="SaaS", website="https://x.test")
    session = _session_with(org)
    with patch(
        "aicmo.modules.orgs.service.audit_service.record",
        new=AsyncMock(),
    ) as rec:
        result = await service.update_org_profile(
            session,
            actor_user_id=uuid.uuid4(),
            org_id=org.id,
            payload=OrganizationProfileUpdate(industry="", website=""),
        )
    assert result.industry is None
    assert result.website is None
    assert org.industry is None
    assert org.website is None
    rec.assert_awaited_once()  # something changed → audit fires


@pytest.mark.asyncio
async def test_update_profile_absent_key_leaves_unchanged() -> None:
    """Sending only `industry` must NOT touch `website` even though
    `website` defaults to None on the model."""
    org = _org_row(industry="old", website="https://keepme.test")
    session = _session_with(org)
    with patch(
        "aicmo.modules.orgs.service.audit_service.record",
        new=AsyncMock(),
    ):
        await service.update_org_profile(
            session,
            actor_user_id=uuid.uuid4(),
            org_id=org.id,
            payload=OrganizationProfileUpdate(industry="new"),
        )
    assert org.industry == "new"
    # Untouched:
    assert org.website == "https://keepme.test"


@pytest.mark.asyncio
async def test_update_profile_refuses_to_clear_name() -> None:
    """Pydantic's `min_length=1` blocks empty strings at the schema layer.
    Whitespace-only strings PASS Pydantic but the service strips them
    and refuses with a 400 — defense-in-depth against the founder
    accidentally clearing their org name.
    """
    from fastapi import HTTPException

    org = _org_row(name="Acme")
    session = _session_with(org)
    with pytest.raises(HTTPException) as exc:
        await service.update_org_profile(
            session,
            actor_user_id=uuid.uuid4(),
            org_id=org.id,
            payload=OrganizationProfileUpdate(name="   "),
        )
    assert exc.value.status_code == 400
    # Name unchanged
    assert org.name == "Acme"


@pytest.mark.asyncio
async def test_update_profile_empty_name_rejected_by_schema() -> None:
    """Belt: the schema layer rejects empty name before the service runs."""
    from pydantic import ValidationError

    with pytest.raises(ValidationError):
        OrganizationProfileUpdate(name="")


@pytest.mark.asyncio
async def test_update_profile_noop_no_audit_row() -> None:
    """If the PATCH body matches current values, no audit row is created.
    Avoids polluting the audit log with cosmetic 'save' clicks."""
    org = _org_row(industry="SaaS")
    session = _session_with(org)
    with patch(
        "aicmo.modules.orgs.service.audit_service.record",
        new=AsyncMock(),
    ) as rec:
        await service.update_org_profile(
            session,
            actor_user_id=uuid.uuid4(),
            org_id=org.id,
            payload=OrganizationProfileUpdate(industry="SaaS"),
        )
    rec.assert_not_awaited()


@pytest.mark.asyncio
async def test_update_profile_404_on_deleted_org() -> None:
    from fastapi import HTTPException

    org = _org_row(status="deleted")
    session = _session_with(org)
    with pytest.raises(HTTPException) as exc:
        await service.update_org_profile(
            session,
            actor_user_id=uuid.uuid4(),
            org_id=org.id,
            payload=OrganizationProfileUpdate(industry="x"),
        )
    assert exc.value.status_code == 404


@pytest.mark.asyncio
async def test_update_profile_404_when_org_missing() -> None:
    from fastapi import HTTPException

    session = MagicMock()
    session.get = AsyncMock(return_value=None)
    session.flush = AsyncMock()
    with pytest.raises(HTTPException) as exc:
        await service.update_org_profile(
            session,
            actor_user_id=uuid.uuid4(),
            org_id=uuid.uuid4(),
            payload=OrganizationProfileUpdate(industry="x"),
        )
    assert exc.value.status_code == 404


# ---------------------------------------------------------------------
#  get_org_profile — projection
# ---------------------------------------------------------------------


@pytest.mark.asyncio
async def test_get_profile_returns_extended_projection() -> None:
    org = _org_row(
        industry="SaaS",
        website="https://x.test",
        country="US",
        timezone="UTC",
    )
    session = _session_with(org)
    result = await service.get_org_profile(session, org_id=org.id)
    assert result.industry == "SaaS"
    assert result.website == "https://x.test"
    assert result.country == "US"
    assert result.timezone == "UTC"


@pytest.mark.asyncio
async def test_get_profile_404_on_deleted() -> None:
    from fastapi import HTTPException

    org = _org_row(status="deleted")
    session = _session_with(org)
    with pytest.raises(HTTPException) as exc:
        await service.get_org_profile(session, org_id=org.id)
    assert exc.value.status_code == 404
