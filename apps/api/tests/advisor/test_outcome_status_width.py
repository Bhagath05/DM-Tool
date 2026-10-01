"""Regression (Postgres-gated): advisor_outcomes.evaluation_status must hold the
longest status the evaluator writes.

Before the 0079 migration the column was varchar(16) while the evaluator writes
"insufficient_data" (17 chars), which truncation-errored on insert. This pins
that every real status value round-trips.
"""

from __future__ import annotations

import uuid

import pytest


@pytest.mark.asyncio
async def test_insufficient_data_status_persists():
    from tests._dbtest import pg_reachable

    if not pg_reachable():
        pytest.skip("Postgres not reachable")

    from sqlalchemy import select, text
    from sqlalchemy.ext.asyncio import AsyncSession, create_async_engine

    import aicmo.main  # noqa: F401 — registers the full ORM graph (orgs/brands FKs)
    from aicmo.modules.advisor.models import AdvisorOutcome, AdvisorRecommendation
    from tests._dbtest import async_dsn

    eng = create_async_engine(async_dsn())
    tag = uuid.uuid4().hex[:8]
    org, brand, user = uuid.uuid4(), uuid.uuid4(), uuid.uuid4()
    try:
        async with AsyncSession(eng, expire_on_commit=False) as s:
            await s.execute(text("INSERT INTO users (id, clerk_user_id, email) VALUES (:i,:c,:e)"),
                            {"i": user, "c": f"c{tag}", "e": f"{tag}@t.local"})
            await s.execute(text("INSERT INTO organizations (id, slug, name, owner_user_id) VALUES (:i,:s,:n,:o)"),
                            {"i": org, "s": f"o{tag}", "n": "O", "o": user})
            await s.execute(
                text("INSERT INTO brands (id, organization_id, slug, name, created_by_user_id) VALUES (:i,:o,:s,:n,:u)"),
                {"i": brand, "o": org, "s": f"b{tag}", "n": "B", "u": user},
            )
            # Every real evaluation_status value must insert without truncation.
            # One recommendation per outcome (recommendation_id is unique).
            from datetime import UTC, datetime

            for status in ("pending", "evaluated", "insufficient_data"):
                rec = AdvisorRecommendation(
                    id=uuid.uuid4(), organization_id=org, brand_id=brand, user_id=str(user),
                    record_type="opportunity", title="t", source_surface="coach",
                    source_fingerprint=uuid.uuid4().hex,
                )
                s.add(rec)
                await s.flush()
                s.add(AdvisorOutcome(
                    id=uuid.uuid4(), brand_id=brand, recommendation_id=rec.id,
                    evaluation_status=status, evaluate_after=datetime.now(UTC),
                ))
            await s.commit()

        async with AsyncSession(eng, expire_on_commit=False) as s:
            rows = (
                await s.execute(select(AdvisorOutcome.evaluation_status).where(AdvisorOutcome.brand_id == brand))
            ).scalars().all()
            assert set(rows) == {"pending", "evaluated", "insufficient_data"}
    finally:
        async with eng.begin() as conn:
            await conn.execute(text("DELETE FROM advisor_outcomes WHERE brand_id=:b"), {"b": brand})
            await conn.execute(text("DELETE FROM advisor_recommendations WHERE organization_id=:o"), {"o": org})
            await conn.execute(text("DELETE FROM brands WHERE organization_id=:o"), {"o": org})
            await conn.execute(text("DELETE FROM organizations WHERE id=:o"), {"o": org})
            await conn.execute(text("DELETE FROM users WHERE id=:u"), {"u": user})
        await eng.dispose()
