"""DB-backed plan + quota resolution — Phase 1.

The system of record for plans + limits is PostgreSQL (`plan` /
`plan_quota`), so pricing/quotas are tunable without a deploy. This
service is the read path. A short in-process TTL cache keeps the hot
quota lookup cheap without making limit-tuning wait for a restart
(default 60s — a changed limit takes effect within a minute).

Quota semantics:
  - a `plan_quota` row with `monthly_limit = N`  → limit N
  - a `plan_quota` row with `monthly_limit = NULL` → explicit unlimited
  - NO `plan_quota` row for (plan, kind)         → unlimited (default)

So Early Access and Scale (no quota rows) are unlimited, by construction.
"""

from __future__ import annotations

import time

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from aicmo.modules.billing.plan_models import Plan, PlanQuota

# (plan_slug, usage_kind) -> limit (None = unlimited). Cached with a TTL.
_QUOTA_CACHE: dict[tuple[str, str], int | None] = {}
_QUOTA_CACHE_AT: float = 0.0
_CACHE_TTL_SECONDS = 60.0


async def _load_quota_cache(session: AsyncSession) -> None:
    global _QUOTA_CACHE, _QUOTA_CACHE_AT
    rows = (
        await session.execute(
            select(PlanQuota.plan_slug, PlanQuota.usage_kind, PlanQuota.monthly_limit)
        )
    ).all()
    _QUOTA_CACHE = {(ps, k): lim for ps, k, lim in rows}
    _QUOTA_CACHE_AT = time.monotonic()


def clear_cache() -> None:
    """Force the next quota lookup to re-read the DB (tests / after a
    limit change you want reflected immediately)."""
    global _QUOTA_CACHE_AT
    _QUOTA_CACHE_AT = 0.0


async def quota_for(
    session: AsyncSession, plan_slug: str, usage_kind: str
) -> int | None:
    """Return the monthly limit for (plan, kind). None = unlimited.

    Absence of a row means unlimited — so any kind without an explicit
    quota (and any plan like early_access/scale) is unbounded.
    """
    now = time.monotonic()
    if (now - _QUOTA_CACHE_AT) >= _CACHE_TTL_SECONDS:
        await _load_quota_cache(session)
    if (plan_slug, usage_kind) not in _QUOTA_CACHE:
        # Distinguish "explicit unlimited row" from "no row": both → None.
        return None
    return _QUOTA_CACHE[(plan_slug, usage_kind)]


async def get_active_plans(session: AsyncSession) -> list[Plan]:
    rows = (
        await session.execute(
            select(Plan).where(Plan.is_active.is_(True)).order_by(Plan.sort_order)
        )
    ).scalars().all()
    return list(rows)


async def get_plan(session: AsyncSession, slug: str) -> Plan | None:
    return (
        await session.execute(select(Plan).where(Plan.slug == slug))
    ).scalar_one_or_none()


async def default_plan_slug(session: AsyncSession) -> str:
    row = (
        await session.execute(select(Plan.slug).where(Plan.is_default.is_(True)))
    ).scalar_one_or_none()
    return row or "early_access"
