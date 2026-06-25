"""Landing-page business logic.

Auth'd CRUD for the customer + unauthenticated read for `/p/{slug}`.
Counters (view_count / submission_count) are denormalized for fast inbox
queries; the leads table is the source of truth.

Post W1-12: scoped by brand_id. Public reads stay slug-only.
"""

from __future__ import annotations

import re
import secrets
import uuid

from fastapi import HTTPException, status
from sqlalchemy import desc, select, update
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from aicmo.config import get_settings
from aicmo.modules.landing_pages.models import LandingPage
from aicmo.modules.landing_pages.schemas import (
    LandingPageContent,
    LandingPageCreate,
    LandingPageResponse,
    LandingPageUpdate,
    PublicLandingPage,
)
from aicmo.tenancy.context import TenantContext

_SLUG_CHARS = re.compile(r"[^a-z0-9]+")


def _slugify(title: str) -> str:
    base = _SLUG_CHARS.sub("-", title.lower()).strip("-")
    base = base[:50] or "page"
    return f"{base}-{secrets.token_urlsafe(4).lower().replace('_', '').replace('-', '')[:6]}"


# ---------- auth'd surfaces ----------


async def create_page(
    session: AsyncSession,
    *,
    tenant: TenantContext,
    business_profile_id: uuid.UUID,
    payload: LandingPageCreate,
) -> LandingPageResponse:
    slug = payload.slug or _slugify(payload.title)

    row = LandingPage(
        id=uuid.uuid4(),
        user_id=tenant.user_id,
        organization_id=tenant.organization_id,
        brand_id=tenant.brand_id,
        business_profile_id=business_profile_id,
        slug=slug,
        title=payload.title,
        status="draft",
        preview_token=secrets.token_urlsafe(24),
        content=payload.content.model_dump(mode="json"),
        redirect_url=str(payload.redirect_url) if payload.redirect_url else None,
    )
    session.add(row)
    try:
        await session.commit()
    except IntegrityError as e:
        await session.rollback()
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="That slug is taken — pick another.",
        ) from e
    await session.refresh(row)
    return _to_response(row)


async def update_page(
    session: AsyncSession,
    *,
    tenant: TenantContext,
    page_id: uuid.UUID,
    payload: LandingPageUpdate,
) -> LandingPageResponse:
    row = await _load_owned(session, brand_id=tenant.brand_id, page_id=page_id)

    changes = payload.model_dump(exclude_unset=True, mode="json")
    if "redirect_url" in changes and changes["redirect_url"] is not None:
        changes["redirect_url"] = str(changes["redirect_url"])
    for key, value in changes.items():
        setattr(row, key, value)

    try:
        await session.commit()
    except IntegrityError as e:
        await session.rollback()
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="That slug is taken — pick another.",
        ) from e
    await session.refresh(row)
    return _to_response(row)


async def list_pages(
    session: AsyncSession,
    *,
    tenant: TenantContext,
    include_archived: bool,
) -> list[LandingPageResponse]:
    stmt = (
        select(LandingPage)
        .where(LandingPage.brand_id == tenant.brand_id)
        .order_by(desc(LandingPage.created_at))
    )
    if not include_archived:
        stmt = stmt.where(LandingPage.is_archived.is_(False))
    rows = (await session.execute(stmt)).scalars().all()
    return [_to_response(r) for r in rows]


async def get_page(
    session: AsyncSession, *, tenant: TenantContext, page_id: uuid.UUID
) -> LandingPageResponse:
    row = await _load_owned(session, brand_id=tenant.brand_id, page_id=page_id)
    return _to_response(row)


async def delete_page(
    session: AsyncSession, *, tenant: TenantContext, page_id: uuid.UUID
) -> None:
    row = await _load_owned(session, brand_id=tenant.brand_id, page_id=page_id)
    await session.delete(row)
    await session.commit()


# ---------- public surfaces (unauthenticated) ----------


async def get_public(
    session: AsyncSession, *, slug: str, preview_token: str | None
) -> PublicLandingPage:
    stmt = select(LandingPage).where(LandingPage.slug == slug)
    row = (await session.execute(stmt)).scalar_one_or_none()
    if row is None or row.is_archived:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail="Page not found"
        )
    if row.status != "published":
        if not preview_token or preview_token != row.preview_token:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND, detail="Page not found"
            )
    settings = get_settings()
    return PublicLandingPage(
        slug=row.slug,
        title=row.title,
        content=LandingPageContent.model_validate(row.content),
        redirect_url=row.redirect_url,
        turnstile_site_key=settings.turnstile_site_key or None,
    )


async def record_view(session: AsyncSession, *, slug: str) -> None:
    await session.execute(
        update(LandingPage)
        .where(LandingPage.slug == slug, LandingPage.status == "published")
        .values(view_count=LandingPage.view_count + 1)
    )
    await session.commit()


async def increment_submission(
    session: AsyncSession, *, landing_page_id: uuid.UUID
) -> None:
    await session.execute(
        update(LandingPage)
        .where(LandingPage.id == landing_page_id)
        .values(submission_count=LandingPage.submission_count + 1)
    )


async def find_published_by_slug(
    session: AsyncSession, *, slug: str
) -> LandingPage | None:
    stmt = select(LandingPage).where(
        LandingPage.slug == slug, LandingPage.status == "published"
    )
    return (await session.execute(stmt)).scalar_one_or_none()


async def get_owned_slug(
    session: AsyncSession, *, brand_id: uuid.UUID, page_id: uuid.UUID
) -> str | None:
    """Look up a landing page's slug, scoped to the brand."""
    stmt = select(LandingPage.slug, LandingPage.is_archived).where(
        LandingPage.id == page_id,
        LandingPage.brand_id == brand_id,
    )
    row = (await session.execute(stmt)).first()
    if row is None or row.is_archived:
        return None
    return row.slug


# ---------- internals ----------


async def _load_owned(
    session: AsyncSession, *, brand_id: uuid.UUID, page_id: uuid.UUID
) -> LandingPage:
    stmt = select(LandingPage).where(
        LandingPage.id == page_id, LandingPage.brand_id == brand_id
    )
    row = (await session.execute(stmt)).scalar_one_or_none()
    if row is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail="Landing page not found"
        )
    return row


def _to_response(row: LandingPage) -> LandingPageResponse:
    return LandingPageResponse.model_validate(row)
