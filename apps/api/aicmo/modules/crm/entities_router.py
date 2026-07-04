"""CRM entities HTTP API (Phase 6.5, Slice 2) — companies, contacts, activities.

Mounted under /crm alongside the core router. Tenant-scoped + RBAC
(crm.view / crm.manage) + audited. Literal collection paths register before the
{id} param routes.
"""

from __future__ import annotations

import uuid

from fastapi import APIRouter, Depends, Query
from sqlalchemy.ext.asyncio import AsyncSession

from aicmo.db.session import get_db
from aicmo.modules.crm import entities_service as svc
from aicmo.modules.crm.schemas import (
    ActivityCreate,
    ActivityList,
    ActivityResponse,
    CompanyCreate,
    CompanyDetail,
    CompanyList,
    CompanyResponse,
    CompanyUpdate,
    ContactCreate,
    ContactDetail,
    ContactList,
    ContactResponse,
    ContactUpdate,
    DuplicateList,
    LinkContactRequest,
    MergeRequest,
)
from aicmo.tenancy.context import TenantContext
from aicmo.tenancy.dependencies import require_permission

router = APIRouter(prefix="/crm", tags=["crm-entities"])

_VIEW = require_permission("crm.view")
_MANAGE = require_permission("crm.manage")


# =====================================================================
#  Companies
# =====================================================================
@router.get("/companies", response_model=CompanyList)
async def list_companies(
    q: str | None = Query(default=None),
    industry: str | None = Query(default=None),
    include_archived: bool = Query(default=False),
    limit: int = Query(default=100, ge=1, le=200),
    offset: int = Query(default=0, ge=0),
    session: AsyncSession = Depends(get_db), tenant: TenantContext = Depends(_VIEW),
) -> CompanyList:
    rows, total = await svc.list_companies(
        session, tenant=tenant, q=q, industry=industry,
        include_archived=include_archived, limit=limit, offset=offset,
    )
    return CompanyList(items=[CompanyResponse.model_validate(r) for r in rows], total=total)


@router.post("/companies", response_model=CompanyResponse, status_code=201)
async def create_company(
    payload: CompanyCreate,
    session: AsyncSession = Depends(get_db), tenant: TenantContext = Depends(_MANAGE),
) -> CompanyResponse:
    return CompanyResponse.model_validate(await svc.create_company(session, tenant=tenant, payload=payload))


@router.get("/companies/{company_id}", response_model=CompanyDetail)
async def get_company(
    company_id: uuid.UUID,
    session: AsyncSession = Depends(get_db), tenant: TenantContext = Depends(_VIEW),
) -> CompanyDetail:
    from aicmo.modules.crm.schemas import DealResponse

    company, contacts, deals = await svc.company_detail(session, tenant=tenant, company_id=company_id)
    return CompanyDetail(
        company=CompanyResponse.model_validate(company),
        contacts=[ContactResponse.model_validate(c) for c in contacts],
        deals=[DealResponse.model_validate(d) for d in deals],
        health_score=company.health_score,
    )


@router.patch("/companies/{company_id}", response_model=CompanyResponse)
async def update_company(
    company_id: uuid.UUID, payload: CompanyUpdate,
    session: AsyncSession = Depends(get_db), tenant: TenantContext = Depends(_MANAGE),
) -> CompanyResponse:
    return CompanyResponse.model_validate(
        await svc.update_company(session, tenant=tenant, company_id=company_id, payload=payload)
    )


@router.delete("/companies/{company_id}", status_code=204)
async def delete_company(
    company_id: uuid.UUID,
    session: AsyncSession = Depends(get_db), tenant: TenantContext = Depends(_MANAGE),
) -> None:
    await svc.delete_company(session, tenant=tenant, company_id=company_id)


@router.get("/companies/{company_id}/duplicates", response_model=DuplicateList)
async def company_duplicates(
    company_id: uuid.UUID,
    session: AsyncSession = Depends(get_db), tenant: TenantContext = Depends(_VIEW),
) -> DuplicateList:
    return DuplicateList(items=await svc.company_duplicates(session, tenant=tenant, company_id=company_id))


@router.post("/companies/{company_id}/merge", response_model=CompanyResponse)
async def merge_companies(
    company_id: uuid.UUID, payload: MergeRequest,
    session: AsyncSession = Depends(get_db), tenant: TenantContext = Depends(_MANAGE),
) -> CompanyResponse:
    return CompanyResponse.model_validate(
        await svc.merge_companies(session, tenant=tenant, survivor_id=company_id, duplicate_id=payload.duplicate_id)
    )


@router.post("/companies/{company_id}/health", response_model=CompanyResponse)
async def company_health(
    company_id: uuid.UUID,
    session: AsyncSession = Depends(get_db), tenant: TenantContext = Depends(_MANAGE),
) -> CompanyResponse:
    await svc.company_health(session, tenant=tenant, company_id=company_id)
    return CompanyResponse.model_validate(
        await svc._owned_company(session, tenant=tenant, company_id=company_id)
    )


@router.post("/companies/{company_id}/summary", response_model=CompanyResponse)
async def company_summary(
    company_id: uuid.UUID,
    session: AsyncSession = Depends(get_db), tenant: TenantContext = Depends(_MANAGE),
) -> CompanyResponse:
    return CompanyResponse.model_validate(
        await svc.generate_company_summary(session, tenant=tenant, company_id=company_id)
    )


@router.get("/companies/{company_id}/activities", response_model=ActivityList)
async def company_activities(
    company_id: uuid.UUID,
    session: AsyncSession = Depends(get_db), tenant: TenantContext = Depends(_VIEW),
) -> ActivityList:
    rows = await svc.list_activities(session, tenant=tenant, company_id=company_id)
    return ActivityList(items=[ActivityResponse.model_validate(a) for a in rows])


# =====================================================================
#  Contacts
# =====================================================================
@router.get("/contacts", response_model=ContactList)
async def list_contacts(
    q: str | None = Query(default=None),
    company_id: uuid.UUID | None = Query(default=None),
    include_archived: bool = Query(default=False),
    limit: int = Query(default=100, ge=1, le=200),
    offset: int = Query(default=0, ge=0),
    session: AsyncSession = Depends(get_db), tenant: TenantContext = Depends(_VIEW),
) -> ContactList:
    rows, total = await svc.list_contacts(
        session, tenant=tenant, q=q, company_id=company_id,
        include_archived=include_archived, limit=limit, offset=offset,
    )
    return ContactList(items=[ContactResponse.model_validate(r) for r in rows], total=total)


@router.post("/contacts", response_model=ContactResponse, status_code=201)
async def create_contact(
    payload: ContactCreate,
    session: AsyncSession = Depends(get_db), tenant: TenantContext = Depends(_MANAGE),
) -> ContactResponse:
    return ContactResponse.model_validate(await svc.create_contact(session, tenant=tenant, payload=payload))


@router.get("/contacts/{contact_id}", response_model=ContactDetail)
async def get_contact(
    contact_id: uuid.UUID,
    session: AsyncSession = Depends(get_db), tenant: TenantContext = Depends(_VIEW),
) -> ContactDetail:
    from aicmo.modules.crm.schemas import DealResponse

    contact, company, deals = await svc.contact_detail(session, tenant=tenant, contact_id=contact_id)
    return ContactDetail(
        contact=ContactResponse.model_validate(contact),
        company=CompanyResponse.model_validate(company) if company else None,
        deals=[DealResponse.model_validate(d) for d in deals],
    )


@router.patch("/contacts/{contact_id}", response_model=ContactResponse)
async def update_contact(
    contact_id: uuid.UUID, payload: ContactUpdate,
    session: AsyncSession = Depends(get_db), tenant: TenantContext = Depends(_MANAGE),
) -> ContactResponse:
    return ContactResponse.model_validate(
        await svc.update_contact(session, tenant=tenant, contact_id=contact_id, payload=payload)
    )


@router.delete("/contacts/{contact_id}", status_code=204)
async def delete_contact(
    contact_id: uuid.UUID,
    session: AsyncSession = Depends(get_db), tenant: TenantContext = Depends(_MANAGE),
) -> None:
    await svc.delete_contact(session, tenant=tenant, contact_id=contact_id)


@router.get("/contacts/{contact_id}/duplicates", response_model=DuplicateList)
async def contact_duplicates(
    contact_id: uuid.UUID,
    session: AsyncSession = Depends(get_db), tenant: TenantContext = Depends(_VIEW),
) -> DuplicateList:
    return DuplicateList(items=await svc.contact_duplicates(session, tenant=tenant, contact_id=contact_id))


@router.post("/contacts/{contact_id}/merge", response_model=ContactResponse)
async def merge_contacts(
    contact_id: uuid.UUID, payload: MergeRequest,
    session: AsyncSession = Depends(get_db), tenant: TenantContext = Depends(_MANAGE),
) -> ContactResponse:
    return ContactResponse.model_validate(
        await svc.merge_contacts(session, tenant=tenant, survivor_id=contact_id, duplicate_id=payload.duplicate_id)
    )


@router.post("/contacts/{contact_id}/summary", response_model=ContactResponse)
async def contact_summary(
    contact_id: uuid.UUID,
    session: AsyncSession = Depends(get_db), tenant: TenantContext = Depends(_MANAGE),
) -> ContactResponse:
    return ContactResponse.model_validate(
        await svc.generate_contact_summary(session, tenant=tenant, contact_id=contact_id)
    )


@router.get("/contacts/{contact_id}/activities", response_model=ActivityList)
async def contact_activities(
    contact_id: uuid.UUID,
    session: AsyncSession = Depends(get_db), tenant: TenantContext = Depends(_VIEW),
) -> ActivityList:
    rows = await svc.list_activities(session, tenant=tenant, contact_id=contact_id)
    return ActivityList(items=[ActivityResponse.model_validate(a) for a in rows])


# =====================================================================
#  Activities + deal ↔ contact links
# =====================================================================
@router.post("/activities", response_model=ActivityResponse, status_code=201)
async def create_activity(
    payload: ActivityCreate,
    session: AsyncSession = Depends(get_db), tenant: TenantContext = Depends(_MANAGE),
) -> ActivityResponse:
    return ActivityResponse.model_validate(await svc.create_activity(session, tenant=tenant, payload=payload))


@router.get("/deals/{deal_id}/contacts", response_model=ContactList)
async def deal_contacts(
    deal_id: uuid.UUID,
    session: AsyncSession = Depends(get_db), tenant: TenantContext = Depends(_VIEW),
) -> ContactList:
    rows = await svc.deal_contacts(session, tenant=tenant, deal_id=deal_id)
    return ContactList(items=[ContactResponse.model_validate(r) for r in rows], total=len(rows))


@router.post("/deals/{deal_id}/contacts", status_code=204)
async def link_deal_contact(
    deal_id: uuid.UUID, payload: LinkContactRequest,
    session: AsyncSession = Depends(get_db), tenant: TenantContext = Depends(_MANAGE),
) -> None:
    await svc.link_contact_to_deal(
        session, tenant=tenant, deal_id=deal_id, contact_id=payload.contact_id, role=payload.role
    )
