"""Brands service.

Brand-level data lifecycle. Org's last active brand cannot be archived
(every active org must have at least one active brand — onboarding
guarantees this).
"""

from __future__ import annotations

import re
import secrets
import uuid

import structlog
from fastapi import HTTPException, status
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from aicmo.modules.audit import service as audit_service
from aicmo.modules.brands.models import Brand
from aicmo.modules.brands.schemas import (
    BrandActivateResult,
    BrandCreate,
    BrandProfileRead,
    BrandProfileUpdate,
    BrandResponse,
    BrandSetDefaultResult,
    BrandUpdate,
)
from aicmo.modules.orgs.models import Organization, OrganizationMember

log = structlog.get_logger()


_SLUG_RX = re.compile(r"[^a-z0-9]+")


def _slugify(name: str) -> str:
    base = _SLUG_RX.sub("-", name.lower()).strip("-")
    base = base[:32] or "brand"
    return f"{base}-{secrets.token_hex(2)}"


async def create_brand(
    session: AsyncSession,
    *,
    actor_user_id: uuid.UUID,
    organization_id: uuid.UUID,
    payload: BrandCreate,
) -> BrandResponse:
    org = await session.get(Organization, organization_id)
    if org is None or org.status != "active":
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Organization not found")

    slug = payload.slug or _slugify(payload.name)

    row = Brand(
        organization_id=organization_id,
        slug=slug,
        name=payload.name.strip(),
        description=payload.description,
        status="active",
        created_by_user_id=actor_user_id,
    )
    session.add(row)
    try:
        await session.flush()
    except Exception as e:  # noqa: BLE001
        # Partial unique index conflict (org_id, slug among active brands)
        await session.rollback()
        raise HTTPException(
            status.HTTP_409_CONFLICT, f"Brand slug '{slug}' already exists in this org"
        ) from e

    # Bump denormalised count.
    org.brand_count = (org.brand_count or 0) + 1
    await session.flush()

    await audit_service.record(
        session,
        organization_id=organization_id,
        brand_id=row.id,
        actor_user_id=actor_user_id,
        action="brand.created",
        target_type="brand",
        target_id=row.id,
        after={"slug": row.slug, "name": row.name},
    )
    return BrandResponse.model_validate(row)


async def list_brands(
    session: AsyncSession,
    *,
    organization_id: uuid.UUID,
    include_archived: bool = False,
) -> list[BrandResponse]:
    stmt = (
        select(Brand)
        .where(Brand.organization_id == organization_id)
        .order_by(Brand.created_at)
    )
    if not include_archived:
        stmt = stmt.where(Brand.status == "active")
    rows = (await session.execute(stmt)).scalars().all()
    return [BrandResponse.model_validate(r) for r in rows]


async def get_brand(
    session: AsyncSession,
    *,
    organization_id: uuid.UUID,
    brand_id: uuid.UUID,
) -> BrandResponse:
    row = await session.get(Brand, brand_id)
    if (
        row is None
        or row.organization_id != organization_id
        or row.status == "deleted"
    ):
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Brand not found")
    return BrandResponse.model_validate(row)


async def update_brand(
    session: AsyncSession,
    *,
    actor_user_id: uuid.UUID,
    organization_id: uuid.UUID,
    brand_id: uuid.UUID,
    payload: BrandUpdate,
) -> BrandResponse:
    row = await session.get(Brand, brand_id)
    if row is None or row.organization_id != organization_id or row.status == "deleted":
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Brand not found")

    before = {"name": row.name, "description": row.description}
    if payload.name is not None:
        row.name = payload.name.strip()
    if payload.description is not None:
        row.description = payload.description
    await session.flush()

    await audit_service.record(
        session,
        organization_id=organization_id,
        brand_id=brand_id,
        actor_user_id=actor_user_id,
        action="brand.updated",
        target_type="brand",
        target_id=brand_id,
        before=before,
        after={"name": row.name, "description": row.description},
    )
    return BrandResponse.model_validate(row)


async def archive_brand(
    session: AsyncSession,
    *,
    actor_user_id: uuid.UUID,
    organization_id: uuid.UUID,
    brand_id: uuid.UUID,
) -> BrandResponse:
    row = await session.get(Brand, brand_id)
    if row is None or row.organization_id != organization_id or row.status == "deleted":
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Brand not found")

    # Refuse if this is the org's only active brand.
    active_count = (
        await session.execute(
            select(func.count(Brand.id)).where(
                Brand.organization_id == organization_id,
                Brand.status == "active",
            )
        )
    ).scalar_one()
    if active_count <= 1:
        raise HTTPException(
            status.HTTP_409_CONFLICT,
            "Cannot archive the org's only active brand. Create another brand first.",
        )

    row.status = "archived"
    # Phase 10.2f — archiving a default brand clears the default flag so
    # the partial unique index doesn't permanently occupy the "default
    # slot" with a non-active brand. After this, `set_default_brand`
    # can promote a different active brand without conflict.
    cleared_default = False
    if row.is_default:
        row.is_default = False
        cleared_default = True
    # Decrement count.
    org = await session.get(Organization, organization_id)
    if org and org.brand_count > 0:
        org.brand_count -= 1
    await session.flush()

    await audit_service.record(
        session,
        organization_id=organization_id,
        brand_id=brand_id,
        actor_user_id=actor_user_id,
        action="brand.archived",
        target_type="brand",
        target_id=brand_id,
        before={"is_default": True} if cleared_default else None,
        after={"is_default": False} if cleared_default else None,
    )
    return BrandResponse.model_validate(row)


# =====================================================================
#  Phase 10.2f — Profile, default, activate
# =====================================================================
#
# Three new public functions:
#
#   update_brand_profile(...)             → patch logo/website + name/desc
#   set_default_brand(...)                → org-wide default brand
#                                           (atomic: clears prior default)
#   activate_brand_for_member(...)        → per-user sticky last-active
#                                           (writes OrganizationMember.
#                                            last_active_brand_id)
#
# Default-vs-active semantics:
#
#   `is_default` is a property of the BRAND (one per org), used when a
#   new member's `last_active_brand_id` is NULL — they land on the org
#   default rather than picking randomly.
#
#   `OrganizationMember.last_active_brand_id` is per-user, persisted
#   across sessions, and what the tenant resolver actually returns when
#   the X-Brand-Id header is absent.
#
# Why both: a freshly-invited user has no last-active brand yet; the
# default flag tells the resolver what to start them on. An existing
# user who has been working in Brand B keeps landing on B even if the
# org default is A.


async def get_brand_profile(
    session: AsyncSession,
    *,
    organization_id: uuid.UUID,
    brand_id: uuid.UUID,
) -> BrandProfileRead:
    row = await session.get(Brand, brand_id)
    if (
        row is None
        or row.organization_id != organization_id
        or row.status == "deleted"
    ):
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Brand not found")
    return _to_profile_read(row)


async def update_brand_profile(
    session: AsyncSession,
    *,
    actor_user_id: uuid.UUID,
    organization_id: uuid.UUID,
    brand_id: uuid.UUID,
    payload: BrandProfileUpdate,
) -> BrandProfileRead:
    """PATCH name + description + logo + website. Empty-string → NULL
    (same opt-in 'clear this field' semantics as the org profile)."""
    row = await session.get(Brand, brand_id)
    if (
        row is None
        or row.organization_id != organization_id
        or row.status == "deleted"
    ):
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Brand not found")

    sent = payload.model_dump(exclude_unset=True)
    before: dict[str, str | None] = {}
    after: dict[str, str | None] = {}

    def _normalise(val: str | None) -> str | None:
        if val is None:
            return None
        s = val.strip()
        return s or None

    # `name` is required on brand. Refuse to clear.
    if "name" in sent:
        new_name = _normalise(sent["name"])
        if not new_name:
            raise HTTPException(
                status.HTTP_400_BAD_REQUEST, "Brand name cannot be empty"
            )
        if new_name != row.name:
            before["name"] = row.name
            row.name = new_name
            after["name"] = new_name

    # description + url fields: nullable, "" clears.
    for field in ("description", "logo_url", "website"):
        if field in sent:
            new_val = _normalise(sent[field])
            current = getattr(row, field)
            if new_val != current:
                before[field] = current
                setattr(row, field, new_val)
                after[field] = new_val

    if after:
        await session.flush()
        await audit_service.record(
            session,
            organization_id=organization_id,
            brand_id=brand_id,
            actor_user_id=actor_user_id,
            action="brand.profile_updated",
            target_type="brand",
            target_id=brand_id,
            before=before,
            after=after,
        )
    return _to_profile_read(row)


async def set_default_brand(
    session: AsyncSession,
    *,
    actor_user_id: uuid.UUID,
    organization_id: uuid.UUID,
    brand_id: uuid.UUID,
) -> BrandSetDefaultResult:
    """Atomically promote `brand_id` to be the org default.

    Steps inside ONE transaction:
      1. Locate the target brand; refuse if archived/deleted or wrong org.
      2. Find any existing default in this org; clear its flag.
      3. Set target's `is_default = true`.

    The partial unique index `uq_brands_one_default_per_org` (migration
    0029) is the actual invariant — this service-layer ordering is the
    optimisation that prevents the index from raising IntegrityError on
    the happy path.
    """
    target = await session.get(Brand, brand_id)
    if (
        target is None
        or target.organization_id != organization_id
        or target.status == "deleted"
    ):
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Brand not found")
    if target.status != "active":
        raise HTTPException(
            status.HTTP_409_CONFLICT,
            "Cannot set an archived brand as default. Reactivate it first.",
        )

    # Find and clear current default (could be None).
    prior_stmt = select(Brand).where(
        Brand.organization_id == organization_id,
        Brand.is_default.is_(True),
    )
    prior = (await session.execute(prior_stmt)).scalars().first()
    prior_id: uuid.UUID | None = None

    if prior is not None and prior.id == brand_id:
        # Idempotent — already the default. No-op, no audit row.
        return BrandSetDefaultResult(
            organization_id=organization_id,
            brand_id=brand_id,
            previous_default_brand_id=brand_id,
        )

    if prior is not None:
        prior.is_default = False
        prior_id = prior.id

    target.is_default = True
    await session.flush()

    await audit_service.record(
        session,
        organization_id=organization_id,
        brand_id=brand_id,
        actor_user_id=actor_user_id,
        action="brand.default_set",
        target_type="brand",
        target_id=brand_id,
        before={"previous_default_brand_id": str(prior_id) if prior_id else None},
        after={"is_default": True},
    )

    return BrandSetDefaultResult(
        organization_id=organization_id,
        brand_id=brand_id,
        previous_default_brand_id=prior_id,
    )


async def activate_brand_for_member(
    session: AsyncSession,
    *,
    actor_user_id: uuid.UUID,
    actor_member_id: uuid.UUID,
    organization_id: uuid.UUID,
    brand_id: uuid.UUID,
) -> BrandActivateResult:
    """Persist the caller's `last_active_brand_id`.

    Per-user, not org-wide. The tenant resolver returns this brand on
    the next request when X-Brand-Id is absent — so the user lands back
    on the brand they were working on.

    Distinct from `set_default_brand`:
      - default = org-wide initial brand for new members
      - active = this specific user's sticky pick
    """
    target = await session.get(Brand, brand_id)
    if (
        target is None
        or target.organization_id != organization_id
        or target.status != "active"
    ):
        raise HTTPException(
            status.HTTP_404_NOT_FOUND, "Active brand not found in this org"
        )

    member = await session.get(OrganizationMember, actor_member_id)
    if (
        member is None
        or member.organization_id != organization_id
        or member.status != "active"
    ):
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Member not found")

    previous = member.last_active_brand_id
    if previous == brand_id:
        # Idempotent — no-op, no audit row.
        return BrandActivateResult(
            member_id=actor_member_id,
            organization_id=organization_id,
            brand_id=brand_id,
            previous_active_brand_id=previous,
        )

    member.last_active_brand_id = brand_id
    await session.flush()

    await audit_service.record(
        session,
        organization_id=organization_id,
        brand_id=brand_id,
        actor_user_id=actor_user_id,
        action="member.active_brand_changed",
        target_type="member",
        target_id=actor_member_id,
        before={"last_active_brand_id": str(previous) if previous else None},
        after={"last_active_brand_id": str(brand_id)},
    )

    return BrandActivateResult(
        member_id=actor_member_id,
        organization_id=organization_id,
        brand_id=brand_id,
        previous_active_brand_id=previous,
    )


# ---------------------------------------------------------------------
#  Internal projection helpers
# ---------------------------------------------------------------------


def _to_profile_read(row: Brand) -> BrandProfileRead:
    """Build the extended GET projection — `active` derives from
    `status`, never persisted."""
    return BrandProfileRead(
        id=row.id,
        organization_id=row.organization_id,
        slug=row.slug,
        name=row.name,
        description=row.description,
        status=row.status,
        created_by_user_id=row.created_by_user_id,
        created_at=row.created_at,
        updated_at=row.updated_at,
        logo_url=row.logo_url,
        website=row.website,
        is_default=row.is_default,
        active=row.is_active,
    )
