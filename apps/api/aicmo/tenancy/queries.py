"""Tenant-scoped query helpers.

`apply_brand_filter(stmt, brand_id)` adds `WHERE brand_id = :bid` to any
SELECT/UPDATE/DELETE statement. Used by service-layer rewrites to scope
every existing query without restructuring it.

`load_in_brand(session, model, *, id, brand_id)` is the uniform single-row
lookup. Returns None when the row doesn't exist OR belongs to a different
brand — both cases collapse to 404 at the router. This is what closes the
'IDOR via id-guessing' attack vector.
"""

from __future__ import annotations

import uuid
from typing import Any, TypeVar

from sqlalchemy import Select
from sqlalchemy.ext.asyncio import AsyncSession

T = TypeVar("T")


def apply_brand_filter(stmt: Select, brand_id: uuid.UUID, model: Any) -> Select:
    """Add `WHERE model.brand_id = :bid` to a SELECT statement."""
    return stmt.where(model.brand_id == brand_id)


async def load_in_brand(
    session: AsyncSession,
    model: type[T],
    *,
    id: uuid.UUID,
    brand_id: uuid.UUID,
) -> T | None:
    """Single-row lookup with brand isolation. Returns None when not
    found OR when found-but-belongs-to-another-brand (caller collapses
    both to 404 at the router edge)."""
    row = await session.get(model, id)
    if row is None:
        return None
    # The mixin guarantees brand_id exists on every business model.
    if getattr(row, "brand_id", None) != brand_id:
        return None
    return row
