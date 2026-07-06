"""Lead business logic.

Two surfaces:
1. Public capture — captcha + rate limit + write + counter update. Atomic.
2. Auth'd inbox — list (paginated, filtered, searchable), get, update, delete, CSV.

The capture flow is the most security-sensitive code in the platform —
anonymous internet traffic. Defence in depth:
  - Cloudflare Turnstile token verification
  - Postgres rate limit by (ip_hash, slug)
  - Slug must resolve to a published landing page (else 404)
  - Lead row written before landing_page counter updated, both in one commit
"""

from __future__ import annotations

import csv
import io
import uuid

from fastapi import HTTPException, status
from sqlalchemy import and_, desc, func, or_, select
from sqlalchemy.ext.asyncio import AsyncSession

from aicmo.config import get_settings
from aicmo.modules.landing_pages import service as landing_service
from aicmo.modules.leads.models import Lead
from aicmo.modules.leads.schemas import (
    LeadCapturePayload,
    LeadCaptureResponse,
    LeadCreatePayload,
    LeadImportResult,
    LeadResponse,
    LeadUpdate,
)
from aicmo.modules.onboarding import service as onboarding_service
from aicmo.security import captcha, rate_limit
from aicmo.security.csv_safety import csv_safe_row
from aicmo.tenancy.context import TenantContext

# ---------- public capture ----------


async def capture(
    session: AsyncSession,
    *,
    slug: str,
    payload: LeadCapturePayload,
    ip: str | None,
    user_agent: str | None,
) -> LeadCaptureResponse:
    settings = get_settings()
    ip_hash = rate_limit.hash_ip(ip) if ip else None

    # Layer 1: rate limit by (ip, slug). Cheaper than captcha — runs first.
    if ip_hash:
        await rate_limit.consume(
            session,
            key=f"capture:{ip_hash}:{slug}",
            limit=settings.lead_capture_rate_limit,
        )

    # Layer 2: captcha. Network call to Cloudflare — only after we know
    # the request isn't a flood.
    await captcha.verify(payload.turnstile_token, remote_ip_hash=ip_hash)

    # Layer 3: landing page must exist + be published.
    page = await landing_service.find_published_by_slug(session, slug=slug)
    if page is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail="Page not found"
        )

    row = Lead(
        id=uuid.uuid4(),
        user_id=page.user_id,
        organization_id=page.organization_id,
        brand_id=page.brand_id,
        business_profile_id=page.business_profile_id,
        email=payload.email,
        name=payload.name,
        phone=payload.phone,
        company=payload.company,
        message=payload.message,
        extra_data=payload.extra_data or {},
        landing_page_id=page.id,
        source_asset_type=payload.source_asset_type or "direct",
        source_asset_id=payload.source_asset_id,
        utm_source=payload.utm_source,
        utm_medium=payload.utm_medium,
        utm_campaign=payload.utm_campaign,
        utm_term=payload.utm_term,
        utm_content=payload.utm_content,
        ip_hash=ip_hash,
        user_agent=(user_agent or "")[:512] or None,
        referrer=payload.referrer,
        status="new",
        tags=[],
    )
    session.add(row)
    # Counter bump in the same transaction.
    await landing_service.increment_submission(session, landing_page_id=page.id)
    # Phase 1 — meter the lead (kind="lead"). NO quota gate here: this is
    # a public visitor submission; we never reject an inbound lead because
    # the founder hit a plan limit. Best-effort + same TX.
    from aicmo.modules.billing import billing_live

    await billing_live.record_metered(
        session,
        organization_id=page.organization_id,
        kind="lead",
        brand_id=page.brand_id,
        metadata={"source": row.source_asset_type},
    )
    await session.commit()

    return LeadCaptureResponse(success=True, redirect_url=page.redirect_url)


# ---------- auth'd inbox ----------


async def list_leads(
    session: AsyncSession,
    *,
    tenant: TenantContext,
    search: str | None,
    status_filter: str | None,
    landing_page_id: uuid.UUID | None,
    limit: int,
    offset: int,
) -> tuple[list[LeadResponse], int]:
    base = select(Lead).where(Lead.brand_id == tenant.brand_id)
    if status_filter:
        base = base.where(Lead.status == status_filter)
    if landing_page_id:
        base = base.where(Lead.landing_page_id == landing_page_id)
    if search:
        like = f"%{search.lower()}%"
        base = base.where(
            or_(
                func.lower(Lead.email).like(like),
                func.lower(func.coalesce(Lead.name, "")).like(like),
                func.lower(func.coalesce(Lead.company, "")).like(like),
            )
        )

    count_stmt = select(func.count()).select_from(base.subquery())
    total = (await session.execute(count_stmt)).scalar_one()

    rows_stmt = (
        base.order_by(desc(Lead.created_at))
        .limit(min(max(limit, 1), 200))
        .offset(max(offset, 0))
    )
    rows = (await session.execute(rows_stmt)).scalars().all()
    return [_to_response(r) for r in rows], int(total)


async def get_lead(
    session: AsyncSession, *, tenant: TenantContext, lead_id: uuid.UUID
) -> LeadResponse:
    row = await _load_owned(session, brand_id=tenant.brand_id, lead_id=lead_id)
    return _to_response(row)


async def create_lead(
    session: AsyncSession,
    *,
    tenant: TenantContext,
    payload: LeadCreatePayload,
) -> LeadResponse:
    profile = await onboarding_service.get_profile_or_none(
        session, tenant.brand_id
    )
    if profile is None:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="Complete business onboarding before adding leads.",
        )

    row = Lead(
        id=uuid.uuid4(),
        user_id=tenant.user_id,
        organization_id=tenant.organization_id,
        brand_id=tenant.brand_id,
        business_profile_id=profile.id,
        email=payload.email,
        name=payload.name,
        phone=payload.phone,
        company=payload.company,
        message=payload.message,
        extra_data={},
        landing_page_id=None,
        source_asset_type=payload.source_asset_type,
        source_asset_id=None,
        status=payload.status,
        tags=list(payload.tags),
        notes=payload.notes,
    )
    session.add(row)
    await session.commit()
    await session.refresh(row)
    return _to_response(row)


async def import_csv(
    session: AsyncSession,
    *,
    tenant: TenantContext,
    csv_text: str,
) -> LeadImportResult:
    profile = await onboarding_service.get_profile_or_none(
        session, tenant.brand_id
    )
    if profile is None:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="Complete business onboarding before importing leads.",
        )

    reader = csv.DictReader(io.StringIO(csv_text))
    if not reader.fieldnames:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="CSV is empty or missing a header row.",
        )

    inserted = 0
    skipped = 0
    errors: list[str] = []

    for idx, row in enumerate(reader, start=2):
        email = (row.get("email") or "").strip()
        if not email:
            skipped += 1
            errors.append(f"Row {idx}: missing email — skipped.")
            continue

        status_val = (row.get("status") or "new").strip().lower()
        if status_val not in ("new", "hot", "warm", "cold", "archived"):
            status_val = "new"

        tags_raw = row.get("tags") or ""
        tags = [t.strip() for t in tags_raw.split(",") if t.strip()]

        landing_page_id: uuid.UUID | None = None
        lp_raw = (row.get("landing_page_id") or "").strip()
        if lp_raw:
            try:
                landing_page_id = uuid.UUID(lp_raw)
            except ValueError:
                errors.append(f"Row {idx}: invalid landing_page_id — ignored.")

        source_type = (row.get("source_asset_type") or "import").strip() or "import"

        session.add(
            Lead(
                id=uuid.uuid4(),
                user_id=tenant.user_id,
                organization_id=tenant.organization_id,
                brand_id=tenant.brand_id,
                business_profile_id=profile.id,
                email=email,
                name=(row.get("name") or "").strip() or None,
                phone=(row.get("phone") or "").strip() or None,
                company=(row.get("company") or "").strip() or None,
                message=(row.get("message") or "").strip() or None,
                extra_data={},
                landing_page_id=landing_page_id,
                source_asset_type=source_type,
                source_asset_id=(row.get("source_asset_id") or "").strip() or None,
                utm_source=(row.get("utm_source") or "").strip() or None,
                utm_medium=(row.get("utm_medium") or "").strip() or None,
                utm_campaign=(row.get("utm_campaign") or "").strip() or None,
                utm_content=(row.get("utm_content") or "").strip() or None,
                status=status_val,
                tags=tags,
                notes=(row.get("notes") or "").strip() or None,
            )
        )
        inserted += 1

    await session.commit()
    return LeadImportResult(inserted=inserted, skipped=skipped, errors=errors[:20])


async def update_lead(
    session: AsyncSession,
    *,
    tenant: TenantContext,
    lead_id: uuid.UUID,
    payload: LeadUpdate,
) -> LeadResponse:
    row = await _load_owned(session, brand_id=tenant.brand_id, lead_id=lead_id)
    changes = payload.model_dump(exclude_unset=True)
    for k, v in changes.items():
        setattr(row, k, v)
    await session.commit()
    await session.refresh(row)
    return _to_response(row)


async def delete_lead(
    session: AsyncSession, *, tenant: TenantContext, lead_id: uuid.UUID
) -> None:
    row = await _load_owned(session, brand_id=tenant.brand_id, lead_id=lead_id)
    await session.delete(row)
    await session.commit()


async def export_csv(
    session: AsyncSession,
    *,
    tenant: TenantContext,
    status_filter: str | None,
    landing_page_id: uuid.UUID | None,
) -> str:
    stmt = select(Lead).where(Lead.brand_id == tenant.brand_id).order_by(desc(Lead.created_at))
    if status_filter:
        stmt = stmt.where(Lead.status == status_filter)
    if landing_page_id:
        stmt = stmt.where(Lead.landing_page_id == landing_page_id)
    rows = (await session.execute(stmt)).scalars().all()

    buf = io.StringIO()
    writer = csv.writer(buf)
    writer.writerow(
        [
            "captured_at",
            "email",
            "name",
            "phone",
            "company",
            "status",
            "tags",
            "source_asset_type",
            "source_asset_id",
            "utm_source",
            "utm_medium",
            "utm_campaign",
            "utm_content",
            "landing_page_id",
            "message",
            "notes",
        ]
    )
    for r in rows:
        # Formula-injection-safe: every field below is user/visitor-controlled.
        writer.writerow(
            csv_safe_row(
                [
                    r.created_at.isoformat(),
                    r.email,
                    r.name or "",
                    r.phone or "",
                    r.company or "",
                    r.status,
                    ", ".join(r.tags or []),
                    r.source_asset_type or "",
                    r.source_asset_id or "",
                    r.utm_source or "",
                    r.utm_medium or "",
                    r.utm_campaign or "",
                    r.utm_content or "",
                    str(r.landing_page_id) if r.landing_page_id else "",
                    (r.message or "").replace("\n", " "),
                    (r.notes or "").replace("\n", " "),
                ]
            )
        )
    return buf.getvalue()


# ---------- internals ----------


async def _load_owned(
    session: AsyncSession, *, brand_id: uuid.UUID, lead_id: uuid.UUID
) -> Lead:
    stmt = select(Lead).where(and_(Lead.id == lead_id, Lead.brand_id == brand_id))
    row = (await session.execute(stmt)).scalar_one_or_none()
    if row is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail="Lead not found"
        )
    return row


def _to_response(row: Lead) -> LeadResponse:
    return LeadResponse.model_validate(row)
