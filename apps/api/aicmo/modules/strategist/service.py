"""Marketing-strategist service.

`generate_strategy` is the pure, testable core (profile → LLM → strategy).
`run_strategy` is the background task that persists the result. Reads are
brand-scoped (tenant isolation) and ordered newest-first.
"""

from __future__ import annotations

import uuid

import structlog
from sqlalchemy import desc, select
from sqlalchemy.ext.asyncio import AsyncSession

from aicmo.db.session import SessionLocal
from aicmo.llm import get_llm_router
from aicmo.llm.providers.base import LLMMessage
from aicmo.modules.onboarding.schemas import BusinessProfileResponse
from aicmo.modules.strategist import prompts
from aicmo.modules.strategist.models import MarketingStrategyRecord
from aicmo.modules.strategist.schemas import (
    MarketingStrategy,
    MarketingStrategyList,
    MarketingStrategyResponse,
)
from aicmo.tenancy.context import TenantContext

log = structlog.get_logger()


async def generate_strategy(
    profile: BusinessProfileResponse,
    learning_block: str = "",
    goals_block: str = "",
) -> MarketingStrategy:
    """Pure of the DB so it can be unit-tested with a mocked LLM router.

    `learning_block` (Module 6) injects learned lessons; `goals_block` (4.3)
    injects the brand's active goals so the strategy serves them."""
    router = get_llm_router()
    result = await router.generate(
        response_schema=MarketingStrategy,
        system=prompts.SYSTEM_PROMPT,
        messages=[
            LLMMessage(
                role="user",
                content=prompts.build_strategy_prompt(
                    profile, learning_block, goals_block
                ),
            ),
        ],
        max_tokens=4096,
    )
    return result.data


async def create_pending(
    session: AsyncSession, *, tenant: TenantContext
) -> MarketingStrategyRecord:
    row = MarketingStrategyRecord(
        id=uuid.uuid4(),
        user_id=tenant.user_id,
        organization_id=tenant.organization_id,
        brand_id=tenant.brand_id,
        status="pending",
    )
    session.add(row)
    await session.commit()
    await session.refresh(row)
    return row


async def latest(
    session: AsyncSession, *, brand_id: uuid.UUID
) -> MarketingStrategyRecord | None:
    stmt = (
        select(MarketingStrategyRecord)
        .where(MarketingStrategyRecord.brand_id == brand_id)
        .order_by(desc(MarketingStrategyRecord.created_at))
        .limit(1)
    )
    return (await session.execute(stmt)).scalar_one_or_none()


async def list_strategies(
    session: AsyncSession, *, brand_id: uuid.UUID, limit: int = 20
) -> MarketingStrategyList:
    stmt = (
        select(MarketingStrategyRecord)
        .where(MarketingStrategyRecord.brand_id == brand_id)
        .order_by(desc(MarketingStrategyRecord.created_at))
        .limit(min(max(limit, 1), 50))
    )
    rows = (await session.execute(stmt)).scalars().all()
    return MarketingStrategyList(
        items=[MarketingStrategyResponse.model_validate(r) for r in rows]
    )


async def run_strategy(
    record_id: str,
    snapshot: BusinessProfileResponse,
    learning_block: str = "",
    goals_block: str = "",
) -> None:
    """Background task — generate then persist. Never raises (worker safety);
    a failure is recorded on the row so the UI can surface + retry."""
    try:
        strategy = await generate_strategy(snapshot, learning_block, goals_block)
    except Exception as e:
        log.warning("strategist.generate.failed", error=str(e)[:200])
        async with SessionLocal() as session:
            await _finish(session, record_id, status="failed", payload=None, error=str(e)[:1000])
        return
    async with SessionLocal() as session:
        await _finish(
            session, record_id, status="completed", payload=strategy.model_dump(), error=None
        )


async def _finish(
    session: AsyncSession,
    record_id: str,
    *,
    status: str,
    payload: dict | None,
    error: str | None,
) -> None:
    row = await session.get(MarketingStrategyRecord, uuid.UUID(str(record_id)))
    if row is None:
        return
    row.status = status
    row.strategy = payload
    row.error = error
    await session.commit()
