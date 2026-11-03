"""HTTP surface for the canonical Business DNA read model (Phase 7.20 Stage 1).

One read-only endpoint. Permission floor is ``analytics.view`` — the same
read permission the advisor/analytics intelligence surfaces already use (no new
RBAC catalog entry is introduced). Brand scope is authorization-derived from the
resolved tenant; the service re-scopes every underlying read by it.
"""

from __future__ import annotations

from fastapi import APIRouter, Depends
from sqlalchemy.ext.asyncio import AsyncSession

from aicmo.db.session import get_db
from aicmo.modules.business_dna import service
from aicmo.modules.business_dna.schemas import BusinessDna
from aicmo.tenancy.context import TenantContext
from aicmo.tenancy.dependencies import require_permission

router = APIRouter(prefix="/business-dna", tags=["business-dna"])

_RequireRead = require_permission("analytics.view")


@router.get("", response_model=BusinessDna)
async def get_business_dna(
    tenant: TenantContext = Depends(_RequireRead),
    session: AsyncSession = Depends(get_db),
) -> BusinessDna:
    """Return the unified, provenance-aware Business DNA for the active brand."""
    return await service.get_business_dna(session, tenant=tenant)
