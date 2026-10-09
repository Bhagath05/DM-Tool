"""Phase 7.3 — the proactive belief-contradiction signal (real Postgres).

The operations loop already detected deterministic metric-delta events. This
phase adds ONE more deterministic signal reusing the SAME DetectedEvent +
notifier machinery: a belief this brand had VALIDATED is now CONTRADICTED by
newer measured outcomes (set by the reconciliation engine, never the LLM).

These tests prove the real persistence + security guarantees that a unit test
with a fake session cannot:

  * a validated-then-contradicted belief produces exactly one event, and the
    notifier raises a notification whose wording records a correlation and does
    NOT imply an action was executed;
  * re-running the detector is idempotent (one active event per belief);
  * a never-validated contradicted belief, and an active belief, produce none
    (no false alarms, honest about weak/absent support);
  * brand/tenant isolation — another brand's contradicted belief never leaks.

Confidence/status are read from the belief row; this phase derives nothing.
Skips cleanly when no project Postgres is reachable (tests/_dbtest).
"""

from __future__ import annotations

import uuid
from datetime import UTC, datetime, timedelta

import pytest


async def _seed_brand(conn, *, org, brand, user, tag):
    from sqlalchemy import text

    await conn.execute(
        text("INSERT INTO users (id, clerk_user_id, email) VALUES (:i,:c,:e)"),
        {"i": user, "c": f"c{tag}", "e": f"{tag}@t.local"},
    )
    await conn.execute(
        text("INSERT INTO organizations (id, slug, name, owner_user_id) VALUES (:i,:s,:n,:o)"),
        {"i": org, "s": f"o{tag}", "n": "O", "o": user},
    )
    await conn.execute(
        text(
            "INSERT INTO brands (id, organization_id, slug, name, created_by_user_id)"
            " VALUES (:i,:o,:s,:n,:u)"
        ),
        {"i": brand, "o": org, "s": f"b{tag}", "n": "B", "u": user},
    )


async def _seed_belief(
    session, *, org, brand, status, validated_at, statement="Reels beat static for leads.",
):
    from aicmo.modules.belief.models import Belief

    belief = Belief(
        id=uuid.uuid4(),
        organization_id=org,
        brand_id=brand,
        category="channel",
        subject_key=f"channel:{uuid.uuid4().hex[:8]}",
        statement=statement,
        scope={},
        status=status,
        confidence=20 if status == "contradicted" else 70,
        confidence_reason="2 supporting, 3 contradicting measured outcomes",
        evidence_count=5,
        validated_at=validated_at,
        updated_at=datetime.now(UTC),
    )
    session.add(belief)
    await session.flush()
    return belief.id


@pytest.mark.asyncio
async def test_validated_then_contradicted_belief_notifies_without_implying_execution():
    from tests._dbtest import pg_reachable

    if not pg_reachable():
        pytest.skip("Postgres not reachable")

    from sqlalchemy import func, select, text
    from sqlalchemy.ext.asyncio import AsyncSession, create_async_engine

    import aicmo.main  # noqa: F401 — registers the full ORM graph
    from aicmo.modules.operations import events, notifier
    from aicmo.modules.operations.models import DetectedEvent, OperationsNotification
    from tests._dbtest import async_dsn

    eng = create_async_engine(async_dsn())
    tag = uuid.uuid4().hex[:8]
    org, brand, user = uuid.uuid4(), uuid.uuid4(), uuid.uuid4()
    now = datetime.now(UTC)
    try:
        async with eng.begin() as conn:
            await _seed_brand(conn, org=org, brand=brand, user=user, tag=tag)

        async with AsyncSession(eng, expire_on_commit=False) as s:
            # The real signal: previously effective (validated_at set), now contradicted.
            target = await _seed_belief(
                s, org=org, brand=brand, status="contradicted", validated_at=now - timedelta(days=5)
            )
            # Controls that must NOT fire:
            await _seed_belief(  # contradicted but never validated → not "previously effective"
                s, org=org, brand=brand, status="contradicted", validated_at=None
            )
            await _seed_belief(  # still active → no contradiction
                s, org=org, brand=brand, status="active", validated_at=now - timedelta(days=5)
            )
            await s.commit()

        # Detect, then notify from the detected events — the real driver path.
        async with AsyncSession(eng, expire_on_commit=False) as s:
            created = await events.detect_belief_contradictions(
                s, organization_id=org, brand_id=brand, now=now
            )
            assert len(created) == 1
            ev = created[0]
            assert ev.event_type == "belief_contradicted"
            assert ev.severity == "high"
            # Grounded in the belief's own statement + "correlation, not cause".
            assert "correlation" in ev.summary.lower()
            assert "not a proven cause" in ev.summary.lower()

            staged = await notifier.emit_for_cycle(
                s, organization_id=org, brand_id=brand, new_events=created, work_created=0, now=now
            )
            assert staged == 1
            await s.commit()

        async with AsyncSession(eng, expire_on_commit=False) as s:
            # Exactly one event row, for the validated-then-contradicted belief only.
            rows = (
                await s.execute(
                    select(DetectedEvent).where(
                        DetectedEvent.brand_id == brand,
                        DetectedEvent.event_type == "belief_contradicted",
                    )
                )
            ).scalars().all()
            assert len(rows) == 1
            assert rows[0].dedupe_key == f"{brand}:belief_contradicted:{target}"

            # The notification records a correlation and never implies BRO acted.
            notes = (
                await s.execute(
                    select(OperationsNotification).where(OperationsNotification.brand_id == brand)
                )
            ).scalars().all()
            assert len(notes) == 1
            body = notes[0].body.lower()
            assert "correlation" in body
            for forbidden in ("we changed", "we have changed", "we applied", "we switched",
                              "we paused", "we updated your", "has been applied", "was applied",
                              "we've adjusted", "automatically changed"):
                assert forbidden not in body

        # Idempotent: re-running while the event is still open creates nothing new.
        async with AsyncSession(eng, expire_on_commit=False) as s:
            again = await events.detect_belief_contradictions(
                s, organization_id=org, brand_id=brand, now=now + timedelta(hours=1)
            )
            await s.commit()
            assert again == []

        async with AsyncSession(eng, expire_on_commit=False) as s:
            count = (
                await s.execute(
                    select(func.count())
                    .select_from(DetectedEvent)
                    .where(
                        DetectedEvent.brand_id == brand,
                        DetectedEvent.event_type == "belief_contradicted",
                    )
                )
            ).scalar_one()
            assert count == 1
    finally:
        async with eng.begin() as conn:
            await conn.execute(text("DELETE FROM operations_notifications WHERE brand_id=:b"), {"b": brand})
            await conn.execute(text("DELETE FROM detected_events WHERE brand_id=:b"), {"b": brand})
            await conn.execute(text("DELETE FROM beliefs WHERE brand_id=:b"), {"b": brand})
            await conn.execute(text("DELETE FROM brands WHERE organization_id=:o"), {"o": org})
            await conn.execute(text("DELETE FROM organizations WHERE id=:o"), {"o": org})
            await conn.execute(text("DELETE FROM users WHERE id=:u"), {"u": user})
        await eng.dispose()


@pytest.mark.asyncio
async def test_belief_signal_is_brand_isolated():
    from tests._dbtest import pg_reachable

    if not pg_reachable():
        pytest.skip("Postgres not reachable")

    from sqlalchemy import select, text
    from sqlalchemy.ext.asyncio import AsyncSession, create_async_engine

    import aicmo.main  # noqa: F401
    from aicmo.modules.operations import events
    from aicmo.modules.operations.models import DetectedEvent
    from tests._dbtest import async_dsn

    eng = create_async_engine(async_dsn())
    tag_a, tag_b = uuid.uuid4().hex[:8], uuid.uuid4().hex[:8]
    org_a, brand_a, user_a = uuid.uuid4(), uuid.uuid4(), uuid.uuid4()
    org_b, brand_b, user_b = uuid.uuid4(), uuid.uuid4(), uuid.uuid4()
    now = datetime.now(UTC)
    try:
        async with eng.begin() as conn:
            await _seed_brand(conn, org=org_a, brand=brand_a, user=user_a, tag=tag_a)
            await _seed_brand(conn, org=org_b, brand=brand_b, user=user_b, tag=tag_b)

        async with AsyncSession(eng, expire_on_commit=False) as s:
            # Brand B owns the contradicted belief.
            await _seed_belief(
                s, org=org_b, brand=brand_b, status="contradicted", validated_at=now - timedelta(days=3)
            )
            await s.commit()

        # Scanning brand A (with brand A's org) must find nothing — no leak.
        async with AsyncSession(eng, expire_on_commit=False) as s:
            a_events = await events.detect_belief_contradictions(
                s, organization_id=org_a, brand_id=brand_a, now=now
            )
            await s.commit()
            assert a_events == []

        # Scanning with brand B's id but the WRONG org must also find nothing
        # (both brand_id and organization_id are enforced).
        async with AsyncSession(eng, expire_on_commit=False) as s:
            wrong_org = await events.detect_belief_contradictions(
                s, organization_id=org_a, brand_id=brand_b, now=now
            )
            await s.commit()
            assert wrong_org == []

        # Brand B sees exactly its own one event.
        async with AsyncSession(eng, expire_on_commit=False) as s:
            b_events = await events.detect_belief_contradictions(
                s, organization_id=org_b, brand_id=brand_b, now=now
            )
            await s.commit()
            assert len(b_events) == 1

        async with AsyncSession(eng, expire_on_commit=False) as s:
            a_rows = (
                await s.execute(select(DetectedEvent).where(DetectedEvent.brand_id == brand_a))
            ).scalars().all()
            assert a_rows == []
    finally:
        async with eng.begin() as conn:
            for b, o, u in ((brand_a, org_a, user_a), (brand_b, org_b, user_b)):
                await conn.execute(text("DELETE FROM detected_events WHERE brand_id=:b"), {"b": b})
                await conn.execute(text("DELETE FROM beliefs WHERE brand_id=:b"), {"b": b})
                await conn.execute(text("DELETE FROM brands WHERE organization_id=:o"), {"o": o})
                await conn.execute(text("DELETE FROM organizations WHERE id=:o"), {"o": o})
                await conn.execute(text("DELETE FROM users WHERE id=:u"), {"u": u})
        await eng.dispose()
