"""HTTP surface for the canonical Business DNA read model (Phase 7.20).

Reads use ``analytics.view`` (the same floor the advisor/analytics intelligence
surfaces already use). The economics WRITE uses ``settings.manage`` — the
established business-config-write permission (same floor as Business Brain
research/ICP mutations); financial inputs are admin-level config. No new RBAC
catalog entry is introduced. Brand scope is authorization-derived from the
resolved tenant; the service/store re-scope every read and write by it.
"""

from __future__ import annotations

from fastapi import APIRouter, Depends
from sqlalchemy.ext.asyncio import AsyncSession

from aicmo.db.session import get_db
from aicmo.modules.business_dna import economics_store, service
from aicmo.modules.business_dna.economics_schema import BusinessEconomics
from aicmo.modules.business_dna.schemas import BusinessDna
from aicmo.tenancy.context import TenantContext
from aicmo.tenancy.dependencies import require_permission

router = APIRouter(prefix="/business-dna", tags=["business-dna"])

_RequireRead = require_permission("analytics.view")
_RequireEconomicsWrite = require_permission("settings.manage")


@router.get("", response_model=BusinessDna)
async def get_business_dna(
    tenant: TenantContext = Depends(_RequireRead),
    session: AsyncSession = Depends(get_db),
) -> BusinessDna:
    """Return the unified, provenance-aware Business DNA for the active brand."""
    return await service.get_business_dna(session, tenant=tenant)


@router.get("/economics", response_model=BusinessEconomics | None)
async def get_economics(
    tenant: TenantContext = Depends(_RequireRead),
    session: AsyncSession = Depends(get_db),
) -> BusinessEconomics | None:
    """Return the brand's stored structured economics inputs, or null."""
    return await economics_store.get_economics(session, tenant=tenant)


@router.put("/economics", response_model=BusinessEconomics)
async def put_economics(
    payload: BusinessEconomics,
    tenant: TenantContext = Depends(_RequireEconomicsWrite),
    session: AsyncSession = Depends(get_db),
) -> BusinessEconomics:
    """Validate + merge + persist the brand's economics (no-LLM-overwrite; never
    touches the AI ``analysis`` column)."""
    return await economics_store.set_economics(session, tenant=tenant, payload=payload)
