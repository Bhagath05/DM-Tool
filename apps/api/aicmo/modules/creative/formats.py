"""creative_format catalog reader — DB is the source of truth (tunable
without deploy, like the plan catalog)."""

from __future__ import annotations

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from aicmo.modules.creative.models import CreativeFormat


async def list_formats(session: AsyncSession, *, media_type: str | None = None) -> list[CreativeFormat]:
    stmt = select(CreativeFormat).where(CreativeFormat.is_active.is_(True))
    if media_type:
        stmt = stmt.where(CreativeFormat.media_type == media_type)
    stmt = stmt.order_by(CreativeFormat.sort_order)
    return list((await session.execute(stmt)).scalars().all())


async def get_format(session: AsyncSession, slug: str) -> CreativeFormat | None:
    return (
        await session.execute(select(CreativeFormat).where(CreativeFormat.slug == slug))
    ).scalar_one_or_none()
