"""Growth service — outcome objective CRUD (the Law 1 primary object).

Brand-scoped (filters by brand_id). No industry logic anywhere — the
objective is an outcome + a free-text statement that flows into prompts.
"""

from __future__ import annotations

import uuid

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from aicmo.modules.growth.models import GrowthObjective, ObjectiveKind
from aicmo.modules.growth.schemas import CreateObjectiveRequest
from aicmo.tenancy.context import TenantContext


class UnknownObjectiveKind(ValueError):
    """The requested objective_kind slug is not in the catalog."""


class MissingBrand(ValueError):
    """A brand-scoped objective was requested without a resolved brand."""


def _brand_id(tenant: TenantContext) -> uuid.UUID:
    if tenant.brand_id is None:
        raise MissingBrand("a brand is required to create or read objectives")
    return tenant.brand_id


async def list_objective_kinds(session: AsyncSession) -> list[ObjectiveKind]:
    rows = await session.execute(
        select(ObjectiveKind).where(ObjectiveKind.is_active.is_(True)).order_by(ObjectiveKind.sort_order)
    )
    return list(rows.scalars().all())


async def create_objective(
    session: AsyncSession, *, tenant: TenantContext, payload: CreateObjectiveRequest
) -> GrowthObjective:
    brand_id = _brand_id(tenant)
    kind = await session.get(ObjectiveKind, payload.objective_kind)
    if kind is None or not kind.is_active:
        raise UnknownObjectiveKind(payload.objective_kind)
    obj = GrowthObjective(
        id=uuid.uuid4(),
        organization_id=tenant.organization_id,
        brand_id=brand_id,
        user_id=tenant.user_id,
        objective_kind=payload.objective_kind,
        statement=payload.statement,
        audience_hypothesis=payload.audience_hypothesis,
        budget_cents=payload.budget_cents,
        status="active",
    )
    session.add(obj)
    return obj


async def list_objectives(
    session: AsyncSession, *, tenant: TenantContext
) -> list[GrowthObjective]:
    brand_id = _brand_id(tenant)
    rows = await session.execute(
        select(GrowthObjective)
        .where(GrowthObjective.brand_id == brand_id)
        .order_by(GrowthObjective.created_at.desc())
    )
    return list(rows.scalars().all())


async def get_objective(
    session: AsyncSession, *, tenant: TenantContext, objective_id: uuid.UUID
) -> GrowthObjective | None:
    brand_id = _brand_id(tenant)
    return await session.scalar(
        select(GrowthObjective).where(
            GrowthObjective.id == objective_id,
            GrowthObjective.brand_id == brand_id,
        )
    )
