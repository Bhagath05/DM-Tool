"""Creative Model Gateway HTTP API. Credentials never leave the server."""

from __future__ import annotations

import uuid
from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.ext.asyncio import AsyncSession

from aicmo.config import get_settings
from aicmo.db.session import get_db
from aicmo.modules.creative.gateway import service
from aicmo.modules.creative.gateway.registry import catalog
from aicmo.modules.creative.gateway.schemas import (
    GenerateRequest,
    JobResponse,
    ModelResult,
    ModelView,
)
from aicmo.modules.creative.gateway.selection import SelectionError
from aicmo.tenancy.context import TenantContext
from aicmo.tenancy.dependencies import require_permission

router = APIRouter(prefix="/creative/gateway", tags=["creative-gateway"])

_RequireRead = require_permission("content.read")
_RequireCreate = require_permission("content.create")


def _require_studio() -> None:
    if not get_settings().studio_enabled:
        raise HTTPException(
            status.HTTP_409_CONFLICT,
            detail="The Creative Studio isn't enabled yet.",
        )


def _job_out(job) -> JobResponse:
    return JobResponse(
        id=job.id,
        mode=job.mode,
        task=job.task,
        status=job.status,
        explanation=job.explanation,
        results=[ModelResult.model_validate(row) for row in (job.results or [])],
        error_message=job.error_message,
    )


@router.get("/models", response_model=list[ModelView])
async def list_models(
    _tenant: Annotated[TenantContext, Depends(_RequireRead)],
) -> list[ModelView]:
    _require_studio()
    return [
        ModelView(
            model_id=model.model_id,
            provider=model.provider,
            task=model.task,
            display_name=model.display_name,
            output_kind=model.output_kind,
            available=model.available(),
            verified=model.verified and model.configured(),
            aspect_ratios=list(model.aspect_ratios),
            resolutions=list(model.resolutions),
            cost_cents=model.cost_cents if model.available() else None,
            cost_unit=model.cost_unit if model.available() else None,
            unavailable_reason=None if model.available() else model.unavailable_reason,
        )
        for model in catalog()
    ]


@router.post("/generations", response_model=JobResponse, status_code=status.HTTP_201_CREATED)
async def create_generation(
    payload: GenerateRequest,
    tenant: Annotated[TenantContext, Depends(_RequireCreate)],
    session: Annotated[AsyncSession, Depends(get_db)],
) -> JobResponse:
    _require_studio()
    try:
        job = await service.run_generation(
            session,
            tenant=tenant,
            mode=payload.mode,
            task=payload.task,
            prompt=payload.prompt,
            model_ids=payload.model_ids,
            aspect_ratio=payload.aspect_ratio,
            resolution=payload.resolution,
        )
    except SelectionError as exc:
        raise HTTPException(status.HTTP_409_CONFLICT, detail=str(exc)) from exc
    return _job_out(job)


@router.get("/generations/{job_id}", response_model=JobResponse)
async def read_generation(
    job_id: uuid.UUID,
    tenant: Annotated[TenantContext, Depends(_RequireRead)],
    session: Annotated[AsyncSession, Depends(get_db)],
) -> JobResponse:
    _require_studio()
    job = await service.get_job(session, tenant=tenant, job_id=job_id)
    if job is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, detail="Generation job not found.")
    return _job_out(job)
