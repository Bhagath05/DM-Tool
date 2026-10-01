"""Read-only belief memory API (Phase 3D).

Exposes "What DM Tool believes" for the authenticated tenant. Strictly:

* **Read-only** — GET only; there is no HTTP write path to belief memory (beliefs
  are formed server-side from evidence, never by a client or the LLM).
* **Authenticated + tenant-derived** — ``require_tenant`` resolves org/brand
  server-side; the client cannot ask for another tenant's beliefs.
* **Current by default** — active, in-window beliefs only; history (superseded /
  contradicted / expired) is returned only with ``include_history=true``.
* **Fail closed** — any resolution error yields an empty, well-typed response
  rather than leaking an internal error or partial data.
"""

from __future__ import annotations

from datetime import UTC, datetime

from fastapi import APIRouter, Depends, Query
from sqlalchemy.ext.asyncio import AsyncSession

from aicmo.db.session import get_db
from aicmo.modules.belief import read, resolver
from aicmo.modules.belief.enums import BeliefCategory
from aicmo.modules.belief.schemas import BeliefReadResponse
from aicmo.tenancy.context import TenantContext
from aicmo.tenancy.dependencies import require_tenant

router = APIRouter(prefix="/api/v1/beliefs", tags=["beliefs"])

_MAX_LIMIT = 100


@router.get("", response_model=BeliefReadResponse)
async def list_beliefs(
    include_history: bool = Query(default=False),
    category: BeliefCategory | None = Query(default=None),
    limit: int = Query(default=25, ge=1, le=_MAX_LIMIT),
    session: AsyncSession = Depends(get_db),
    tenant: TenantContext = Depends(require_tenant()),
) -> BeliefReadResponse:
    now = datetime.now(UTC)
    try:
        resolution = await resolver.resolve_beliefs(
            session,
            tenant=tenant,
            category=category.value if category is not None else None,
            include_history=include_history,
            limit=limit,
        )
    except Exception:
        # Fail closed — never surface an internal error or another tenant's data.
        from aicmo.modules.belief.schemas import BeliefReadResponse as _Empty

        return _Empty(as_of=now, includes_history=include_history)
    return read.to_read_response(resolution, now=now, includes_history=include_history)
