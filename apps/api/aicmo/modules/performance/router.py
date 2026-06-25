"""Performance API surface — Phase 9.1.

CSV-only ingest plus read endpoints. No platform mutations, no
autonomous spend changes, no Meta/Google connectors. Permission
gate: same `analytics.view` we already use for coach/analytics.
"""

from __future__ import annotations

import uuid

from fastapi import APIRouter, Depends, File, HTTPException, UploadFile, status
from sqlalchemy.ext.asyncio import AsyncSession

from aicmo.db.session import get_db
from aicmo.modules.performance import service
from aicmo.modules.performance.schemas import (
    CsvIngestSummary,
    PerformanceOverview,
)
from aicmo.tenancy.context import TenantContext
from aicmo.tenancy.dependencies import require_permission

router = APIRouter(prefix="/performance", tags=["performance"])

# Hard cap on upload size — 2 MiB. A month of Meta CSV is well
# under this; bigger files are almost always misuse.
_MAX_BYTES = 2 * 1024 * 1024


@router.post(
    "/upload-csv",
    response_model=CsvIngestSummary,
    status_code=status.HTTP_201_CREATED,
)
async def upload_csv(
    file: UploadFile = File(...),
    session: AsyncSession = Depends(get_db),
    tenant: TenantContext = Depends(require_permission("analytics.view")),
) -> CsvIngestSummary:
    """Accept a CSV export and ingest its rows.

    Returns a per-upload summary the dashboard renders inline. Errors
    inside individual rows are SURFACED (in the summary), not raised —
    a 30-row file with 2 bad rows still imports the other 28.
    """
    blob = await file.read()
    if not blob:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Uploaded file is empty.",
        )
    if len(blob) > _MAX_BYTES:
        raise HTTPException(
            status_code=status.HTTP_413_REQUEST_ENTITY_TOO_LARGE,
            detail=(
                f"File is too large ({len(blob):,} bytes). "
                f"Max {_MAX_BYTES:,}. Trim to the last 30 days."
            ),
        )
    try:
        text = blob.decode("utf-8-sig")  # handles Excel BOMs
    except UnicodeDecodeError:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="File must be UTF-8 encoded CSV.",
        )
    try:
        return await service.ingest_csv(
            session,
            tenant=tenant,
            payload=text,
            filename=file.filename,
        )
    except ValueError as exc:
        # Structural problem — header missing, file empty, etc.
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST, detail=str(exc)
        )


@router.get("/overview", response_model=PerformanceOverview)
async def get_overview(
    session: AsyncSession = Depends(get_db),
    tenant: TenantContext = Depends(require_permission("analytics.view")),
) -> PerformanceOverview:
    """Founder-facing payload. Returns has_data=False when nothing
    has been ingested yet — the dashboard renders the upload CTA in
    that slot."""
    return await service.overview(session, tenant=tenant)


@router.post(
    "/diagnostics/{diagnostic_id}/dismiss",
    status_code=status.HTTP_204_NO_CONTENT,
)
async def dismiss(
    diagnostic_id: uuid.UUID,
    session: AsyncSession = Depends(get_db),
    tenant: TenantContext = Depends(require_permission("analytics.view")),
) -> None:
    """Founder clicked 'not useful'. Hide, don't delete (audit trail)."""
    ok = await service.dismiss_diagnostic(
        session, tenant=tenant, diagnostic_id=diagnostic_id
    )
    if not ok:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Diagnostic not found or already resolved.",
        )


@router.delete(
    "/data",
    status_code=status.HTTP_204_NO_CONTENT,
)
async def reset_performance_data(
    session: AsyncSession = Depends(get_db),
    tenant: TenantContext = Depends(require_permission("analytics.view")),
) -> None:
    """Wipe ALL ingested performance data for this brand.

    Drops every row from `performance_events`, `creative_results`, and
    `performance_diagnostics` scoped to the active brand. The brand's
    creative tags on `generated_*` tables are untouched — only the
    uploaded-CSV-derived data is removed.

    Use cases:
      - Stale test data needs clearing.
      - Founder uploaded the wrong file and wants to start over.
      - Brand changes attribution model and wants a clean slate.

    Returns 204 on success regardless of how many rows were deleted —
    "no data to clear" is a valid success state.
    """
    await service.reset_brand_data(session, tenant=tenant)
