"""Phase 7.4 — real-Postgres tests for the experiment-draft service.

Proves the persistence + security guarantees a fake session cannot:

  * a valid proposal creates ONE reversible draft (an AdvisorRecommendation with
    record_type="experiment"), validated, tenant-scoped, audited;
  * re-running with the same proposal is idempotent (same id, created=False, no
    duplicate row) — safe under retries;
  * by default (autonomy master switch OFF) acting on the draft requires approval
    — creation never auto-grants a consequential action;
  * an invalid proposal is rejected before anything is written;
  * two brands proposing the "same" experiment get distinct, isolated drafts.

Skips cleanly when no project Postgres is reachable (tests/_dbtest).
"""

from __future__ import annotations

import uuid

import pytest


def _tenant_ctx(*, org, brand, user):
    from aicmo.tenancy.context import TenantContext

    return TenantContext(
        user_id=str(user), user_uuid=user, organization_id=org, brand_id=brand,
        member_id=uuid.uuid4(), role_slugs=frozenset({"owner"}), permissions=frozenset(),
    )


def _proposal() -> dict:
    return {
        "business_objective": "Get more qualified leads from Instagram",
        "hypothesis": "Founder-led reels beat product carousels for lead intent",
        "primary_metric": "leads",
        "comparison": "Founder reel vs product carousel, same offer",
        "variants": [
            {"label": "Reel", "variable_choices": {"format": "reel"}},
            {"label": "Carousel", "variable_choices": {"format": "carousel"}},
        ],
        "channel": "instagram",
        "measurement_window_days": 14,
        "success_condition": "Reel yields >=20% more leads at >=100 impressions per arm",
        "inconclusive_condition": "Difference within the 10% noise band or under 100 impressions",
    }


async def _seed_brand(conn, *, org, brand, user, tag):
    from sqlalchemy import text

    await conn.execute(text("INSERT INTO users (id, clerk_user_id, email) VALUES (:i,:c,:e)"),
                       {"i": user, "c": f"c{tag}", "e": f"{tag}@t.local"})
    await conn.execute(text("INSERT INTO organizations (id, slug, name, owner_user_id) VALUES (:i,:s,:n,:o)"),
                       {"i": org, "s": f"o{tag}", "n": "O", "o": user})
    await conn.execute(
        text("INSERT INTO brands (id, organization_id, slug, name, created_by_user_id) VALUES (:i,:o,:s,:n,:u)"),
        {"i": brand, "o": org, "s": f"b{tag}", "n": "B", "u": user},
    )


@pytest.mark.asyncio
async def test_draft_created_once_idempotent_and_approval_gated():
    from tests._dbtest import pg_reachable

    if not pg_reachable():
        pytest.skip("Postgres not reachable")

    from sqlalchemy import func, select, text
    from sqlalchemy.ext.asyncio import AsyncSession, create_async_engine

    import aicmo.main  # noqa: F401 — registers the full ORM graph
    from aicmo.modules.advisor.models import AdvisorRecommendation
    from aicmo.modules.audit.models import AuditEvent
    from aicmo.modules.learning.experiment_contract import ExperimentContractError
    from aicmo.modules.learning.experiment_drafts import create_experiment_draft
    from tests._dbtest import async_dsn

    eng = create_async_engine(async_dsn())
    tag = uuid.uuid4().hex[:8]
    org, brand, user = uuid.uuid4(), uuid.uuid4(), uuid.uuid4()
    try:
        async with eng.begin() as conn:
            await _seed_brand(conn, org=org, brand=brand, user=user, tag=tag)

        ctx = _tenant_ctx(org=org, brand=brand, user=user)

        async with AsyncSession(eng, expire_on_commit=False) as s:
            res = await create_experiment_draft(s, tenant=ctx, proposal=_proposal())
            await s.commit()
        assert res.created is True
        # Default autonomy (manual level + master switch OFF) → acting on the
        # draft requires human approval; creation never auto-grants it.
        assert res.requires_approval is True
        assert res.autonomy_mode == "always_approve"

        async with AsyncSession(eng, expire_on_commit=False) as s:
            rows = (await s.execute(
                select(AdvisorRecommendation).where(AdvisorRecommendation.brand_id == brand)
            )).scalars().all()
            assert len(rows) == 1
            row = rows[0]
            assert row.record_type == "experiment"
            assert row.status == "not_started"
            assert row.confidence == 0  # a draft asserts no confidence
            assert row.generator_hint["kind"] == "experiment_proposal"
            assert row.generator_hint["proposal"]["primary_metric"] == "leads"
            assert row.generator_hint["autonomy"]["requires_approval"] is True
            # Audited.
            audits = (await s.execute(
                select(AuditEvent).where(
                    AuditEvent.target_id == row.id,
                    AuditEvent.action == "experiment.draft_created",
                )
            )).scalars().all()
            assert len(audits) == 1

        # Idempotent: re-propose the SAME experiment → same row, no duplicate.
        async with AsyncSession(eng, expire_on_commit=False) as s:
            res2 = await create_experiment_draft(s, tenant=ctx, proposal=_proposal())
            await s.commit()
        assert res2.created is False
        assert res2.recommendation_id == res.recommendation_id

        async with AsyncSession(eng, expire_on_commit=False) as s:
            count = (await s.execute(
                select(func.count()).select_from(AdvisorRecommendation).where(
                    AdvisorRecommendation.brand_id == brand
                )
            )).scalar_one()
            assert count == 1

        # Invalid proposal → rejected, nothing written.
        async with AsyncSession(eng, expire_on_commit=False) as s:
            bad = _proposal()
            bad["variants"] = [bad["variants"][0]]  # only one arm
            with pytest.raises(ExperimentContractError):
                await create_experiment_draft(s, tenant=ctx, proposal=bad)
            await s.rollback()
    finally:
        async with eng.begin() as conn:
            await conn.execute(text("DELETE FROM audit_events WHERE brand_id=:b"), {"b": brand})
            await conn.execute(text("DELETE FROM advisor_recommendations WHERE brand_id=:b"), {"b": brand})
            await conn.execute(text("DELETE FROM brands WHERE organization_id=:o"), {"o": org})
            await conn.execute(text("DELETE FROM organizations WHERE id=:o"), {"o": org})
            await conn.execute(text("DELETE FROM users WHERE id=:u"), {"u": user})
        await eng.dispose()


@pytest.mark.asyncio
async def test_drafts_are_brand_isolated():
    from tests._dbtest import pg_reachable

    if not pg_reachable():
        pytest.skip("Postgres not reachable")

    from sqlalchemy import select, text
    from sqlalchemy.ext.asyncio import AsyncSession, create_async_engine

    import aicmo.main  # noqa: F401
    from aicmo.modules.advisor.models import AdvisorRecommendation
    from aicmo.modules.learning.experiment_drafts import create_experiment_draft
    from tests._dbtest import async_dsn

    eng = create_async_engine(async_dsn())
    tag_a, tag_b = uuid.uuid4().hex[:8], uuid.uuid4().hex[:8]
    org_a, brand_a, user_a = uuid.uuid4(), uuid.uuid4(), uuid.uuid4()
    org_b, brand_b, user_b = uuid.uuid4(), uuid.uuid4(), uuid.uuid4()
    try:
        async with eng.begin() as conn:
            await _seed_brand(conn, org=org_a, brand=brand_a, user=user_a, tag=tag_a)
            await _seed_brand(conn, org=org_b, brand=brand_b, user=user_b, tag=tag_b)

        # Both brands propose the SAME experiment text.
        async with AsyncSession(eng, expire_on_commit=False) as s:
            ra = await create_experiment_draft(s, tenant=_tenant_ctx(org=org_a, brand=brand_a, user=user_a), proposal=_proposal())
            rb = await create_experiment_draft(s, tenant=_tenant_ctx(org=org_b, brand=brand_b, user=user_b), proposal=_proposal())
            await s.commit()

        # Distinct drafts (id is brand-scoped), each owned by its own brand.
        assert ra.recommendation_id != rb.recommendation_id
        assert ra.fingerprint == rb.fingerprint  # same proposal text → same fingerprint

        async with AsyncSession(eng, expire_on_commit=False) as s:
            a_rows = (await s.execute(
                select(AdvisorRecommendation).where(AdvisorRecommendation.brand_id == brand_a)
            )).scalars().all()
            assert len(a_rows) == 1 and a_rows[0].id == ra.recommendation_id
            assert a_rows[0].organization_id == org_a
    finally:
        async with eng.begin() as conn:
            for b, o, u in ((brand_a, org_a, user_a), (brand_b, org_b, user_b)):
                await conn.execute(text("DELETE FROM audit_events WHERE brand_id=:b"), {"b": b})
                await conn.execute(text("DELETE FROM advisor_recommendations WHERE brand_id=:b"), {"b": b})
                await conn.execute(text("DELETE FROM brands WHERE organization_id=:o"), {"o": o})
                await conn.execute(text("DELETE FROM organizations WHERE id=:o"), {"o": o})
                await conn.execute(text("DELETE FROM users WHERE id=:u"), {"u": u})
        await eng.dispose()
