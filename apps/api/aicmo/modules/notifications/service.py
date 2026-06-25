"""Phase 10.2b — Notification preferences service layer.

Three operations:

  1. get_catalog()             — static descriptor, no I/O
  2. get_matrix(user, org)     — materialised 18-cell matrix
  3. upsert_preferences(...)   — bulk update with lock enforcement

Locked-cell policy: a PUT that attempts to disable a locked cell is
SILENTLY COERCED to enabled=True. We don't 4xx for it because:

  - The frontend gets the lock status from /catalog and disables the
    toggle, so a well-behaved client can never send a disable.
  - A buggy or replayed request shouldn't break the user's settings
    page. Coerce, persist the safe value, return the materialised
    matrix so the caller sees what landed.

Tested in tests/notifications/test_service.py.
"""

from __future__ import annotations

import uuid
from dataclasses import dataclass

from sqlalchemy import select
from sqlalchemy.dialects.postgresql import insert as pg_insert
from sqlalchemy.ext.asyncio import AsyncSession

from aicmo.modules.notifications import catalog
from aicmo.modules.notifications.models import NotificationPreference
from aicmo.modules.notifications.schemas import (
    NotificationCatalog,
    PreferenceCell,
    PreferenceMatrix,
    PreferenceUpdate,
)


# ---------------------------------------------------------------------
#  Public surface
# ---------------------------------------------------------------------


def get_catalog() -> NotificationCatalog:
    """Pure pass-through — the catalog is static. Wrapped in a service
    function so the router never reaches into `catalog` directly and
    future changes (e.g. per-tenant overrides) are localised here."""
    return catalog.get_catalog()


async def get_matrix(
    session: AsyncSession,
    *,
    user_id: uuid.UUID,
    organization_id: uuid.UUID,
) -> PreferenceMatrix:
    """Return the full (category × channel) matrix for one user-org pair.

    Cells with no stored row fall back to the code-defined default.
    """
    stored = await _load_stored(
        session,
        user_id=user_id,
        organization_id=organization_id,
    )
    return PreferenceMatrix(cells=list(_materialise(stored)))


async def upsert_preferences(
    session: AsyncSession,
    *,
    user_id: uuid.UUID,
    organization_id: uuid.UUID,
    updates: list[PreferenceUpdate],
) -> PreferenceMatrix:
    """Bulk-upsert preference cells; return the resulting matrix.

    - Unknown category/channel values are rejected at the Pydantic
      Literal layer before reaching here.
    - Locked cells are silently coerced to enabled=True (see module
      docstring).
    - De-dupe by (category, channel) — last update wins. We don't
      raise on duplicates because the frontend's React-state flush
      can plausibly send the same cell twice in one PUT.
    """
    if not updates:
        # Pydantic min_length=1 already rejects this; defensive guard
        # for callers reaching the service directly.
        return await get_matrix(
            session,
            user_id=user_id,
            organization_id=organization_id,
        )

    # De-dupe (last write wins) + apply lock policy.
    coerced = coerce_updates_with_locks(updates)

    # Bulk upsert — Postgres ON CONFLICT DO UPDATE on the composite PK.
    rows = [
        {
            "user_id": user_id,
            "organization_id": organization_id,
            "category": cat,
            "channel": ch,
            "enabled": enabled,
            "source": "user",
        }
        for (cat, ch), enabled in coerced.items()
    ]
    stmt = pg_insert(NotificationPreference).values(rows)
    stmt = stmt.on_conflict_do_update(
        constraint="pk_notification_preference",
        set_={
            "enabled": stmt.excluded.enabled,
            "source": stmt.excluded.source,
            "updated_at": _now_sql(),
        },
    )
    await session.execute(stmt)
    await session.flush()

    return await get_matrix(
        session,
        user_id=user_id,
        organization_id=organization_id,
    )


# ---------------------------------------------------------------------
#  Pure helpers (unit-testable without a session)
# ---------------------------------------------------------------------


def coerce_updates_with_locks(
    updates: list[PreferenceUpdate],
) -> dict[tuple[str, str], bool]:
    """De-dupe by (category, channel) (last write wins) and force
    locked cells to enabled=True. Pure function — tested directly.
    """
    coerced: dict[tuple[str, str], bool] = {}
    for u in updates:
        key = (u.category, u.channel)
        coerced[key] = True if catalog.is_locked(*key) else u.enabled
    return coerced


def materialise_matrix(
    stored: dict[tuple[str, str], "_StoredRow"],
) -> list[PreferenceCell]:
    """Public alias for `_materialise` — exported so tests can build a
    synthetic stored map without a session. The service uses the same
    function internally."""
    return _materialise(stored)


# ---------------------------------------------------------------------
#  Internals
# ---------------------------------------------------------------------


@dataclass(frozen=True)
class _StoredRow:
    enabled: bool
    source: str
    updated_at: object  # datetime; left untyped to avoid datetime import noise


async def _load_stored(
    session: AsyncSession,
    *,
    user_id: uuid.UUID,
    organization_id: uuid.UUID,
) -> dict[tuple[str, str], _StoredRow]:
    """Read all stored rows for (user, org) into a {(cat,ch): row} map."""
    stmt = select(NotificationPreference).where(
        NotificationPreference.user_id == user_id,
        NotificationPreference.organization_id == organization_id,
    )
    rows = (await session.execute(stmt)).scalars().all()
    return {
        (r.category, r.channel): _StoredRow(
            enabled=r.enabled,
            source=r.source,
            updated_at=r.updated_at,
        )
        for r in rows
    }


def _materialise(
    stored: dict[tuple[str, str], _StoredRow],
) -> list[PreferenceCell]:
    """Overlay stored rows on code-defined defaults — produces every
    (category × channel) cell in canonical order."""
    out: list[PreferenceCell] = []
    for cat, ch in catalog.all_cells():
        spec = catalog.cell_spec(cat, ch)
        row = stored.get((cat, ch))
        if row is None:
            out.append(
                PreferenceCell(
                    category=cat,
                    channel=ch,
                    enabled=spec.default_enabled,
                    source="system",
                    locked=spec.locked,
                    updated_at=None,
                )
            )
        else:
            # Lock invariant: even if a stale row somehow has
            # enabled=False on a locked cell, surface it as True. The
            # next upsert will rewrite it.
            effective = True if spec.locked else row.enabled
            out.append(
                PreferenceCell(
                    category=cat,
                    channel=ch,
                    enabled=effective,
                    source=row.source,  # type: ignore[arg-type]
                    locked=spec.locked,
                    updated_at=row.updated_at,  # type: ignore[arg-type]
                )
            )
    return out


def _now_sql():
    """func.now() lazily — keeps the import close to use."""
    from sqlalchemy import func

    return func.now()
