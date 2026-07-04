"""CRM Email Platform HTTP API (Phase 6.5, Slice 4). Mounted under /crm/email.
Tenant-scoped + RBAC (crm.view / crm.manage) + audited + ownership-validated."""

from __future__ import annotations

import uuid

from fastapi import APIRouter, Depends, Query
from sqlalchemy.ext.asyncio import AsyncSession

from aicmo.db.session import get_db
from aicmo.modules.crm import email_service as svc
from aicmo.modules.crm.email_schemas import (
    BulkEnrollRequest,
    EmailList,
    EmailResponse,
    EmailStats,
    EnrollmentList,
    EnrollmentResponse,
    EnrollRequest,
    FolderCreate,
    FolderList,
    FolderResponse,
    RenderedEmail,
    RenderRequest,
    SendEmailRequest,
    SequenceCreate,
    SequenceList,
    SequenceResponse,
    SequenceUpdate,
    StepResponse,
    TemplateCreate,
    TemplateList,
    TemplateResponse,
    TemplateUpdate,
    TemplateVersionList,
    TemplateVersionResponse,
)
from aicmo.tenancy.context import TenantContext
from aicmo.tenancy.dependencies import require_permission

router = APIRouter(prefix="/crm/email", tags=["crm-email"])

_VIEW = require_permission("crm.view")
_MANAGE = require_permission("crm.manage")


def _seq_response(seq, steps) -> SequenceResponse:
    r = SequenceResponse.model_validate(seq)
    r.steps = [StepResponse.model_validate(s) for s in steps]
    return r


# ---- folders ----
@router.get("/folders", response_model=FolderList)
async def list_folders(session: AsyncSession = Depends(get_db), tenant: TenantContext = Depends(_VIEW)) -> FolderList:
    rows = await svc.list_folders(session, tenant=tenant)
    return FolderList(items=[FolderResponse.model_validate(r) for r in rows])


@router.post("/folders", response_model=FolderResponse, status_code=201)
async def create_folder(payload: FolderCreate, session: AsyncSession = Depends(get_db),
                        tenant: TenantContext = Depends(_MANAGE)) -> FolderResponse:
    row = await svc.create_folder(session, tenant=tenant, name=payload.name, parent_id=payload.parent_id)
    return FolderResponse.model_validate(row)


# ---- templates ----
@router.get("/templates", response_model=TemplateList)
async def list_templates(
    category: str | None = Query(default=None), folder_id: uuid.UUID | None = Query(default=None),
    q: str | None = Query(default=None), active_only: bool = Query(default=False),
    limit: int = Query(default=100, ge=1, le=200), offset: int = Query(default=0, ge=0),
    session: AsyncSession = Depends(get_db), tenant: TenantContext = Depends(_VIEW),
) -> TemplateList:
    rows, total = await svc.list_templates(session, tenant=tenant, category=category, folder_id=folder_id,
                                           q=q, active_only=active_only, limit=limit, offset=offset)
    return TemplateList(items=[TemplateResponse.model_validate(r) for r in rows], total=total)


@router.post("/templates", response_model=TemplateResponse, status_code=201)
async def create_template(payload: TemplateCreate, session: AsyncSession = Depends(get_db),
                          tenant: TenantContext = Depends(_MANAGE)) -> TemplateResponse:
    return TemplateResponse.model_validate(await svc.create_template(session, tenant=tenant, payload=payload))


@router.get("/templates/{template_id}", response_model=TemplateResponse)
async def get_template(template_id: uuid.UUID, session: AsyncSession = Depends(get_db),
                       tenant: TenantContext = Depends(_VIEW)) -> TemplateResponse:
    return TemplateResponse.model_validate(await svc.get_template(session, tenant=tenant, template_id=template_id))


@router.patch("/templates/{template_id}", response_model=TemplateResponse)
async def update_template(template_id: uuid.UUID, payload: TemplateUpdate, session: AsyncSession = Depends(get_db),
                          tenant: TenantContext = Depends(_MANAGE)) -> TemplateResponse:
    return TemplateResponse.model_validate(
        await svc.update_template(session, tenant=tenant, template_id=template_id, payload=payload)
    )


@router.delete("/templates/{template_id}", status_code=204)
async def delete_template(template_id: uuid.UUID, session: AsyncSession = Depends(get_db),
                          tenant: TenantContext = Depends(_MANAGE)) -> None:
    await svc.delete_template(session, tenant=tenant, template_id=template_id)


@router.get("/templates/{template_id}/versions", response_model=TemplateVersionList)
async def template_versions(template_id: uuid.UUID, session: AsyncSession = Depends(get_db),
                            tenant: TenantContext = Depends(_VIEW)) -> TemplateVersionList:
    rows = await svc.template_versions(session, tenant=tenant, template_id=template_id)
    return TemplateVersionList(items=[TemplateVersionResponse.model_validate(r) for r in rows])


@router.post("/templates/{template_id}/render", response_model=RenderedEmail)
async def render_template(template_id: uuid.UUID, payload: RenderRequest, session: AsyncSession = Depends(get_db),
                          tenant: TenantContext = Depends(_VIEW)) -> RenderedEmail:
    subject, body, unresolved = await svc.render_template(
        session, tenant=tenant, template_id=template_id, variables=payload.variables, contact_id=payload.contact_id
    )
    return RenderedEmail(subject=subject, body=body, unresolved=unresolved)


# ---- sequences ----
@router.get("/sequences", response_model=SequenceList)
async def list_sequences(session: AsyncSession = Depends(get_db), tenant: TenantContext = Depends(_VIEW)) -> SequenceList:
    rows = await svc.list_sequences(session, tenant=tenant)
    return SequenceList(items=[_seq_response(s, steps) for s, steps in rows])


@router.post("/sequences", response_model=SequenceResponse, status_code=201)
async def create_sequence(payload: SequenceCreate, session: AsyncSession = Depends(get_db),
                          tenant: TenantContext = Depends(_MANAGE)) -> SequenceResponse:
    seq, steps = await svc.create_sequence(session, tenant=tenant, payload=payload)
    return _seq_response(seq, steps)


@router.get("/sequences/{sequence_id}", response_model=SequenceResponse)
async def get_sequence(sequence_id: uuid.UUID, session: AsyncSession = Depends(get_db),
                       tenant: TenantContext = Depends(_VIEW)) -> SequenceResponse:
    seq, steps = await svc.get_sequence(session, tenant=tenant, sequence_id=sequence_id)
    return _seq_response(seq, steps)


@router.patch("/sequences/{sequence_id}", response_model=SequenceResponse)
async def update_sequence(sequence_id: uuid.UUID, payload: SequenceUpdate, session: AsyncSession = Depends(get_db),
                          tenant: TenantContext = Depends(_MANAGE)) -> SequenceResponse:
    seq, steps = await svc.update_sequence(
        session, tenant=tenant, sequence_id=sequence_id, name=payload.name,
        description=payload.description, seq_status=payload.status,
    )
    return _seq_response(seq, steps)


@router.post("/sequences/run")
async def run_sequences(session: AsyncSession = Depends(get_db), tenant: TenantContext = Depends(_MANAGE)) -> dict:
    """Advance this brand's due enrollments (send due steps). Callable by an
    operator; a system cron can drive it across tenants later."""
    processed = await svc.run_due_enrollments(session, tenant=tenant)
    return {"processed": processed}


# ---- enrollments ----
@router.post("/sequences/{sequence_id}/enroll", response_model=EnrollmentResponse, status_code=201)
async def enroll(sequence_id: uuid.UUID, payload: EnrollRequest, session: AsyncSession = Depends(get_db),
                 tenant: TenantContext = Depends(_MANAGE)) -> EnrollmentResponse:
    row = await svc.enroll(
        session, tenant=tenant, sequence_id=sequence_id, contact_id=payload.contact_id,
        to_email=payload.to_email, lead_id=payload.lead_id, company_id=payload.company_id,
        deal_id=payload.deal_id, campaign_id=payload.campaign_id,
    )
    return EnrollmentResponse.model_validate(row)


@router.post("/sequences/{sequence_id}/bulk-enroll", response_model=EnrollmentList, status_code=201)
async def bulk_enroll(sequence_id: uuid.UUID, payload: BulkEnrollRequest, session: AsyncSession = Depends(get_db),
                      tenant: TenantContext = Depends(_MANAGE)) -> EnrollmentList:
    rows = await svc.bulk_enroll(session, tenant=tenant, sequence_id=sequence_id, contact_ids=payload.contact_ids)
    return EnrollmentList(items=[EnrollmentResponse.model_validate(r) for r in rows], total=len(rows))


@router.get("/enrollments", response_model=EnrollmentList)
async def list_enrollments(
    sequence_id: uuid.UUID | None = Query(default=None), status: str | None = Query(default=None),
    limit: int = Query(default=100, ge=1, le=200), offset: int = Query(default=0, ge=0),
    session: AsyncSession = Depends(get_db), tenant: TenantContext = Depends(_VIEW),
) -> EnrollmentList:
    rows, total = await svc.list_enrollments(session, tenant=tenant, sequence_id=sequence_id,
                                             enrollment_status=status, limit=limit, offset=offset)
    return EnrollmentList(items=[EnrollmentResponse.model_validate(r) for r in rows], total=total)


@router.post("/enrollments/{enrollment_id}/{action}", response_model=EnrollmentResponse)
async def enrollment_action(enrollment_id: uuid.UUID, action: str, session: AsyncSession = Depends(get_db),
                            tenant: TenantContext = Depends(_MANAGE)) -> EnrollmentResponse:
    mapping = {"pause": "paused", "resume": "active", "cancel": "cancelled"}
    from fastapi import HTTPException
    from fastapi import status as st
    if action not in mapping:
        raise HTTPException(st.HTTP_400_BAD_REQUEST, "Unknown action.")
    row = await svc.set_enrollment_status(session, tenant=tenant, enrollment_id=enrollment_id, new_status=mapping[action])
    return EnrollmentResponse.model_validate(row)


# ---- emails ----
@router.post("/send", response_model=EmailResponse, status_code=201)
async def send_email(payload: SendEmailRequest, session: AsyncSession = Depends(get_db),
                     tenant: TenantContext = Depends(_MANAGE)) -> EmailResponse:
    return EmailResponse.model_validate(await svc.send_email(session, tenant=tenant, payload=payload))


@router.get("/emails", response_model=EmailList)
async def list_emails(
    contact_id: uuid.UUID | None = Query(default=None), deal_id: uuid.UUID | None = Query(default=None),
    status: str | None = Query(default=None),
    limit: int = Query(default=100, ge=1, le=200), offset: int = Query(default=0, ge=0),
    session: AsyncSession = Depends(get_db), tenant: TenantContext = Depends(_VIEW),
) -> EmailList:
    rows, total = await svc.list_emails(session, tenant=tenant, contact_id=contact_id, deal_id=deal_id,
                                        email_status=status, limit=limit, offset=offset)
    return EmailList(items=[EmailResponse.model_validate(r) for r in rows], total=total)


@router.get("/stats", response_model=EmailStats)
async def email_stats(session: AsyncSession = Depends(get_db), tenant: TenantContext = Depends(_VIEW)) -> EmailStats:
    return EmailStats(**await svc.email_stats(session, tenant=tenant))
