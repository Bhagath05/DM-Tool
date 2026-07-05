"""Shared CRM helpers (Phase 6.5 enterprise consolidation).

One audit path for every CRM slice — deals, contacts, companies, tasks, email,
insights, dashboard — instead of five byte-identical copies. Always tags
target_type="crm" and is exception-safe (audit MUST NOT break a business op).
"""

from __future__ import annotations

import contextlib
import uuid

from sqlalchemy.ext.asyncio import AsyncSession

from aicmo.modules.audit import service as audit_service
from aicmo.tenancy.context import TenantContext


async def record_crm_audit(
    session: AsyncSession, *, tenant: TenantContext, action: str,
    target_id: uuid.UUID | None = None, metadata: dict | None = None,
) -> None:
    with contextlib.suppress(Exception):
        await audit_service.record(
            session, organization_id=tenant.organization_id, actor_user_id=tenant.user_uuid,
            action=action, brand_id=tenant.brand_id, target_type="crm", target_id=target_id,
            metadata=metadata or {},
        )
