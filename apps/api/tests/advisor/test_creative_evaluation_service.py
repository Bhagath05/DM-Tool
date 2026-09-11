"""Service + governance tests for the AI-vs-human creative evaluator.

Covers the integration half of the required matrix: provenance resolution, the
"recommend humans, never just more AI" shaping, confidence-cannot-bypass-
approval, human rejection remaining authoritative, tenant isolation, and the
recommendation audit trail. Pure/hermetic checks always run; DB-backed checks
run against a real local Postgres and skip cleanly when one isn't reachable.
"""

from __future__ import annotations

import uuid
from datetime import UTC, datetime
from types import SimpleNamespace

import pytest

# Register FK-target models so SocialAsset's mapper configures under ORM use
# (SocialAsset -> integration_connection / social_connections). Referenced in
# _REGISTER below so they read as used.
import aicmo.modules.integrations.models as _integrations_models
import aicmo.modules.social.models as _social_models
from aicmo.modules.advisor.creative_evaluation_service import (
    record_creative_recommendation,
    resolve_provenance,
    shape_response,
)
from aicmo.modules.marketing_analytics.creative_evaluation import (
    CreativeEvaluation,
    MetricDelta,
    Provenance,
    Verdict,
)

# Force SocialAsset's FK-target models to register before any ORM use.
_REGISTER = (_integrations_models, _social_models)


# ---------------- pure: provenance resolution ----------------
def test_resolve_provenance_explicit_label_wins():
    assert resolve_provenance(explicit="ai", source_table=None) is Provenance.AI
    assert (
        resolve_provenance(explicit="human", source_table="generated_content") is Provenance.HUMAN
    )
    assert resolve_provenance(explicit="AI", source_table=None) is Provenance.AI  # case-insensitive


def test_resolve_provenance_derives_ai_from_generated_source():
    assert resolve_provenance(explicit=None, source_table="generated_content") is Provenance.AI
    assert resolve_provenance(explicit=None, source_table="generated_ads") is Provenance.AI
    assert resolve_provenance(explicit=None, source_table="generated_visuals") is Provenance.AI


def test_resolve_provenance_unknown_is_never_guessed_human():
    # An unrecognised source is UNKNOWN, never silently "human".
    assert resolve_provenance(explicit=None, source_table="some_upload") is Provenance.UNKNOWN
    assert resolve_provenance(explicit=None, source_table=None) is Provenance.UNKNOWN
    assert resolve_provenance(explicit="", source_table=None) is Provenance.UNKNOWN


# ---------------- pure: recommendation shaping ----------------
def _eval(verdict: Verdict, confidence: int = 80) -> CreativeEvaluation:
    deltas = [
        MetricDelta("views", "views", 800, 1200, -0.33, ai_better=False, significant=True),
        MetricDelta(
            "engagement_rate", "engagement", 0.02, 0.03, -0.33, ai_better=False, significant=True
        ),
    ]
    return CreativeEvaluation(
        verdict=verdict,
        confidence=confidence,
        ai_sample_size=4,
        human_sample_size=4,
        unknown_sample_size=0,
        metric_deltas=deltas,
        evidence=["4 AI vs 4 human samples."],
        limitations=["No per-creative attributed revenue data available."],
    )


def test_underperforming_recommends_humans_not_more_ai():
    resp = shape_response(_eval(Verdict.AI_UNDERPERFORMING))
    assert resp.verdict == "AI_UNDERPERFORMING"
    assert "human" in resp.recommended_action.lower()
    assert "do not scale ai" in resp.recommended_action.lower()
    # must offer real human alternatives, never "generate more AI"
    joined = " ".join(resp.alternatives).lower()
    assert any(k in joined for k in ("creator", "photographer", "videographer", "ugc", "model"))
    assert "generate more ai" not in joined
    # full contract present
    assert resp.diagnosis and resp.expected_impact and resp.assumptions and resp.risks
    assert resp.evidence_limitations  # limitations surfaced, not hidden


def test_human_approval_always_required_regardless_of_confidence():
    for verdict in Verdict:
        for conf in (10, 55, 90):
            resp = shape_response(_eval(verdict, confidence=conf))
            assert resp.human_approval_required is True  # confidence never unlocks execution


def test_outperforming_still_keeps_a_human_control():
    resp = shape_response(_eval(Verdict.AI_OUTPERFORMING))
    assert resp.verdict == "AI_OUTPERFORMING"
    assert "control" in (resp.recommended_action + " ".join(resp.alternatives)).lower()
    assert resp.human_approval_required is True


def test_insufficient_evidence_does_not_push_ai_generation():
    resp = shape_response(
        CreativeEvaluation(
            verdict=Verdict.INSUFFICIENT_EVIDENCE,
            confidence=0,
            ai_sample_size=1,
            human_sample_size=0,
            unknown_sample_size=2,
            evidence=[],
            limitations=["thin"],
        )
    )
    assert resp.verdict == "INSUFFICIENT_EVIDENCE"
    assert "generate more ai" not in (resp.recommended_action + " ".join(resp.alternatives)).lower()


# ---------------- real-Postgres integration ----------------
def _pg():
    from tests._dbtest import pg_reachable

    if not pg_reachable():
        pytest.skip("Postgres not reachable")


def _engine():
    from sqlalchemy.ext.asyncio import create_async_engine

    from tests._dbtest import async_dsn

    return create_async_engine(async_dsn())


async def _seed_tenant(session, *, org, brands, user, tag):
    """Insert the org/brand/user graph the SocialAsset FKs require."""
    from sqlalchemy import text

    await session.execute(
        text("INSERT INTO users (id, clerk_user_id, email) VALUES (:i,:c,:e)"),
        {"i": user, "c": f"clerk_{tag}", "e": f"{tag}@t.local"},
    )
    await session.execute(
        text("INSERT INTO organizations (id, slug, name, owner_user_id) VALUES (:i,:s,:n,:o)"),
        {"i": org, "s": f"org-{tag}", "n": "Eval Org", "o": user},
    )
    for idx, b in enumerate(brands):
        await session.execute(
            text(
                "INSERT INTO brands (id, organization_id, slug, name, created_by_user_id) "
                "VALUES (:i,:o,:s,:n,:u)"
            ),
            {"i": b, "o": org, "s": f"brand-{tag}-{idx}", "n": f"Brand {idx}", "u": user},
        )
    await session.flush()


async def _seed_brand(session, *, org, brand, user, ai_views, human_views, ai_eng, human_eng, tag):
    from aicmo.modules.social.models import PerformanceSignal, SocialAsset

    async def _asset(prov: str, views: float, eng: float, i: int):
        a = SocialAsset(
            id=uuid.uuid4(),
            user_id=str(user),
            organization_id=org,
            brand_id=brand,
            platform="instagram",
            platform_post_id=f"{tag}-{prov}-{i}",
            asset_type="reel",
            posted_at=datetime.now(UTC),
            creative_provenance=prov,
        )
        session.add(a)
        await session.flush()
        session.add(
            PerformanceSignal(
                id=uuid.uuid4(),
                asset_id=a.id,
                views=int(views),
                engagement_rate=eng,
                captured_at=datetime.now(UTC),
            )
        )

    for i in range(3):
        await _asset("ai", ai_views, ai_eng, i)
        await _asset("human", human_views, human_eng, i)


@pytest.mark.asyncio
async def test_tenant_isolation_evaluation_only_sees_its_own_brand():
    _pg()
    from sqlalchemy import text
    from sqlalchemy.ext.asyncio import AsyncSession

    from aicmo.modules.advisor.creative_evaluation_service import evaluate_creative

    org, brand_a, brand_b, user = uuid.uuid4(), uuid.uuid4(), uuid.uuid4(), uuid.uuid4()
    tag = uuid.uuid4().hex[:8]
    eng = _engine()
    try:
        async with AsyncSession(eng, expire_on_commit=False) as s:
            await _seed_tenant(s, org=org, brands=[brand_a, brand_b], user=user, tag=tag)
            # Brand A: AI clearly worse. Brand B: AI clearly better (opposite).
            await _seed_brand(
                s,
                org=org,
                brand=brand_a,
                user=user,
                ai_views=800,
                human_views=1200,
                ai_eng=0.02,
                human_eng=0.03,
                tag=f"{tag}a",
            )
            await _seed_brand(
                s,
                org=org,
                brand=brand_b,
                user=user,
                ai_views=1400,
                human_views=1000,
                ai_eng=0.045,
                human_eng=0.03,
                tag=f"{tag}b",
            )
            await s.commit()

        tenant_a = SimpleNamespace(organization_id=org, brand_id=brand_a, user_id=str(user))
        async with AsyncSession(eng, expire_on_commit=False) as s:
            resp = await evaluate_creative(s, tenant=tenant_a)
        # Only brand A's 3+3 — brand B's opposite data must not leak in.
        assert resp.ai_sample_size == 3 and resp.human_sample_size == 3
        assert resp.verdict in ("AI_UNDERPERFORMING", "HUMAN_OUTPERFORMING")
    finally:
        async with eng.begin() as conn:
            await conn.execute(
                text(
                    "DELETE FROM performance_signals WHERE asset_id IN "
                    "(SELECT id FROM social_assets WHERE brand_id IN (:a,:b))"
                ),
                {"a": brand_a, "b": brand_b},
            )
            await conn.execute(
                text("DELETE FROM social_assets WHERE brand_id IN (:a,:b)"),
                {"a": brand_a, "b": brand_b},
            )
            await conn.execute(text("DELETE FROM brands WHERE organization_id=:o"), {"o": org})
            await conn.execute(text("DELETE FROM organizations WHERE id=:o"), {"o": org})
            await conn.execute(text("DELETE FROM users WHERE id=:u"), {"u": user})
        await eng.dispose()


@pytest.mark.asyncio
async def test_recommendation_persists_advisory_and_is_audited():
    _pg()
    from sqlalchemy import text
    from sqlalchemy.ext.asyncio import AsyncSession

    from aicmo.modules.advisor.creative_evaluation_service import evaluate_creative

    org, brand, user = uuid.uuid4(), uuid.uuid4(), uuid.uuid4()
    tag = uuid.uuid4().hex[:8]
    eng = _engine()
    rec_id = None
    try:
        async with AsyncSession(eng, expire_on_commit=False) as s:
            await _seed_tenant(s, org=org, brands=[brand], user=user, tag=tag)
            await _seed_brand(
                s,
                org=org,
                brand=brand,
                user=user,
                ai_views=700,
                human_views=1300,
                ai_eng=0.018,
                human_eng=0.034,
                tag=tag,
            )
            await s.commit()

        tenant = SimpleNamespace(organization_id=org, brand_id=brand, user_id=str(user))
        async with AsyncSession(eng, expire_on_commit=False) as s:
            resp = await evaluate_creative(s, tenant=tenant)
            assert resp.ai_is_underperforming if hasattr(resp, "ai_is_underperforming") else True
            assert resp.verdict in ("AI_UNDERPERFORMING", "HUMAN_OUTPERFORMING")
            rec = await record_creative_recommendation(s, tenant=tenant, response=resp)
            await s.commit()
            assert rec is not None
            rec_id = rec.id
            # persisted as ADVISORY — status not_started, never auto-approved/executed,
            # regardless of confidence (confidence cannot bypass approval).
            assert rec.status == "not_started"
            assert rec.brand_id == brand
            assert rec.confidence == resp.confidence

        # audit trail row exists for the recommendation.
        async with AsyncSession(eng, expire_on_commit=False) as s:
            n = (
                await s.execute(
                    text("SELECT count(*) FROM advisor_memory_events WHERE recommendation_id=:r"),
                    {"r": rec_id},
                )
            ).scalar_one()
            assert n >= 1
    finally:
        async with eng.begin() as conn:
            if rec_id:
                await conn.execute(
                    text("DELETE FROM advisor_memory_events WHERE recommendation_id=:r"),
                    {"r": rec_id},
                )
                await conn.execute(
                    text("DELETE FROM advisor_recommendations WHERE id=:r"), {"r": rec_id}
                )
            await conn.execute(
                text(
                    "DELETE FROM performance_signals WHERE asset_id IN "
                    "(SELECT id FROM social_assets WHERE brand_id=:b)"
                ),
                {"b": brand},
            )
            await conn.execute(text("DELETE FROM social_assets WHERE brand_id=:b"), {"b": brand})
            await conn.execute(text("DELETE FROM brands WHERE organization_id=:o"), {"o": org})
            await conn.execute(text("DELETE FROM organizations WHERE id=:o"), {"o": org})
            await conn.execute(text("DELETE FROM users WHERE id=:u"), {"u": user})
        await eng.dispose()


@pytest.mark.asyncio
async def test_human_rejection_is_authoritative_across_reevaluation():
    _pg()
    from sqlalchemy import text
    from sqlalchemy.ext.asyncio import AsyncSession

    from aicmo.modules.advisor.creative_evaluation_service import evaluate_creative

    org, brand, user = uuid.uuid4(), uuid.uuid4(), uuid.uuid4()
    tag = uuid.uuid4().hex[:8]
    eng = _engine()
    rec_id = None
    try:
        async with AsyncSession(eng, expire_on_commit=False) as s:
            await _seed_tenant(s, org=org, brands=[brand], user=user, tag=tag)
            await _seed_brand(
                s,
                org=org,
                brand=brand,
                user=user,
                ai_views=700,
                human_views=1300,
                ai_eng=0.018,
                human_eng=0.034,
                tag=tag,
            )
            await s.commit()
        tenant = SimpleNamespace(organization_id=org, brand_id=brand, user_id=str(user))
        async with AsyncSession(eng, expire_on_commit=False) as s:
            resp = await evaluate_creative(s, tenant=tenant)
            rec = await record_creative_recommendation(s, tenant=tenant, response=resp)
            await s.commit()
            rec_id = rec.id
            # Human rejects the recommendation.
            rec.status = "skipped"
            await s.commit()
        # Re-evaluation (same fingerprint) must NOT resurrect a rejected rec.
        async with AsyncSession(eng, expire_on_commit=False) as s:
            resp2 = await evaluate_creative(s, tenant=tenant)
            await record_creative_recommendation(s, tenant=tenant, response=resp2)
            await s.commit()
        async with AsyncSession(eng, expire_on_commit=False) as s:
            status = (
                await s.execute(
                    text("SELECT status FROM advisor_recommendations WHERE id=:r"), {"r": rec_id}
                )
            ).scalar_one()
            assert status == "skipped"  # human rejection remains authoritative
    finally:
        async with eng.begin() as conn:
            if rec_id:
                await conn.execute(
                    text("DELETE FROM advisor_memory_events WHERE recommendation_id=:r"),
                    {"r": rec_id},
                )
                await conn.execute(
                    text("DELETE FROM advisor_recommendations WHERE id=:r"), {"r": rec_id}
                )
            await conn.execute(
                text(
                    "DELETE FROM performance_signals WHERE asset_id IN "
                    "(SELECT id FROM social_assets WHERE brand_id=:b)"
                ),
                {"b": brand},
            )
            await conn.execute(text("DELETE FROM social_assets WHERE brand_id=:b"), {"b": brand})
            await conn.execute(text("DELETE FROM brands WHERE organization_id=:o"), {"o": org})
            await conn.execute(text("DELETE FROM organizations WHERE id=:o"), {"o": org})
            await conn.execute(text("DELETE FROM users WHERE id=:u"), {"u": user})
        await eng.dispose()
