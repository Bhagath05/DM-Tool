from __future__ import annotations

import uuid

from fastapi import APIRouter, Depends, HTTPException, Query, Request, Response, status
from sqlalchemy.ext.asyncio import AsyncSession

from aicmo.db.session import get_db
from aicmo.modules.leads import service
from aicmo.modules.leads.intelligence import build_lead_intelligence
from aicmo.modules.leads.schemas import (
    LeadCapturePayload,
    LeadCaptureResponse,
    LeadCreatePayload,
    LeadImportPayload,
    LeadImportResult,
    LeadIntelligenceReport,
    LeadList,
    LeadResponse,
    LeadUpdate,
)
from aicmo.modules.onboarding import service as onboarding_service
from aicmo.modules.onboarding.schemas import BusinessProfileResponse
from aicmo.tenancy.context import TenantContext
from aicmo.tenancy.dependencies import require_permission

# ---------- public capture (no auth) ----------

public_router = APIRouter(prefix="/public/leads", tags=["public"])


def _client_ip(request: Request) -> str | None:
    fwd = request.headers.get("x-forwarded-for")
    if fwd:
        return fwd.split(",", 1)[0].strip()
    if request.client:
        return request.client.host
    return None


@public_router.post(
    "/capture/{slug}",
    response_model=LeadCaptureResponse,
    status_code=status.HTTP_201_CREATED,
)
async def capture_lead(
    slug: str,
    payload: LeadCapturePayload,
    request: Request,
    session: AsyncSession = Depends(get_db),
) -> LeadCaptureResponse:
    return await service.capture(
        session,
        slug=slug,
        payload=payload,
        ip=_client_ip(request),
        user_agent=request.headers.get("user-agent"),
    )


# ---------- auth'd inbox ----------

router = APIRouter(prefix="/leads", tags=["leads"])


@router.get("", response_model=LeadList)
async def list_leads(
    search: str | None = Query(default=None, max_length=120),
    status_filter: str | None = Query(default=None, alias="status"),
    landing_page_id: uuid.UUID | None = Query(default=None),
    limit: int = Query(default=50, ge=1, le=200),
    offset: int = Query(default=0, ge=0),
    session: AsyncSession = Depends(get_db),
    tenant: TenantContext = Depends(require_permission("lead.view")),
) -> LeadList:
    items, total = await service.list_leads(
        session,
        tenant=tenant,
        search=search,
        status_filter=status_filter,
        landing_page_id=landing_page_id,
        limit=limit,
        offset=offset,
    )
    return LeadList(items=items, total=total)


@router.post("", response_model=LeadResponse, status_code=status.HTTP_201_CREATED)
async def create_lead(
    payload: LeadCreatePayload,
    session: AsyncSession = Depends(get_db),
    tenant: TenantContext = Depends(require_permission("lead.view")),
) -> LeadResponse:
    return await service.create_lead(session, tenant=tenant, payload=payload)


@router.post("/import", response_model=LeadImportResult)
async def import_leads_csv(
    payload: LeadImportPayload,
    session: AsyncSession = Depends(get_db),
    tenant: TenantContext = Depends(require_permission("lead.view")),
) -> LeadImportResult:
    return await service.import_csv(session, tenant=tenant, csv_text=payload.csv)


@router.get("/intelligence", response_model=LeadIntelligenceReport)
async def get_intelligence(
    session: AsyncSession = Depends(get_db),
    tenant: TenantContext = Depends(require_permission("lead.view")),
) -> LeadIntelligenceReport:
    """Phase 5 — Lead Intelligence.

    Returns the ranked "who to contact first" advisor card + per-lead
    priorities for the inbox. One LLM call per request; the frontend
    caches for 30 minutes via localStorage so a refreshing founder
    doesn't re-bill.

    409 when business onboarding hasn't been completed — every
    recommendation depends on stage + audience signals from the profile.
    """
    profile_row = await onboarding_service.get_profile_or_none(
        session, tenant.brand_id
    )
    if profile_row is None:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="Complete business onboarding before using lead intelligence",
        )
    profile = BusinessProfileResponse.model_validate(profile_row)
    return await build_lead_intelligence(session, profile=profile)


@router.get("/export.csv")
async def export_leads_csv(
    status_filter: str | None = Query(default=None, alias="status"),
    landing_page_id: uuid.UUID | None = Query(default=None),
    session: AsyncSession = Depends(get_db),
    tenant: TenantContext = Depends(require_permission("lead.export")),
) -> Response:
    csv_text = await service.export_csv(
        session,
        tenant=tenant,
        status_filter=status_filter,
        landing_page_id=landing_page_id,
    )
    return Response(
        content=csv_text,
        media_type="text/csv",
        headers={"Content-Disposition": 'attachment; filename="leads.csv"'},
    )


@router.get("/{lead_id}", response_model=LeadResponse)
async def get_lead(
    lead_id: uuid.UUID,
    session: AsyncSession = Depends(get_db),
    tenant: TenantContext = Depends(require_permission("lead.view")),
) -> LeadResponse:
    return await service.get_lead(session, tenant=tenant, lead_id=lead_id)


@router.patch("/{lead_id}", response_model=LeadResponse)
async def update_lead(
    lead_id: uuid.UUID,
    payload: LeadUpdate,
    session: AsyncSession = Depends(get_db),
    tenant: TenantContext = Depends(require_permission("lead.view")),
) -> LeadResponse:
    return await service.update_lead(
        session, tenant=tenant, lead_id=lead_id, payload=payload
    )


@router.delete("/{lead_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_lead(
    lead_id: uuid.UUID,
    session: AsyncSession = Depends(get_db),
    tenant: TenantContext = Depends(require_permission("lead.export")),
) -> None:
    await service.delete_lead(session, tenant=tenant, lead_id=lead_id)
