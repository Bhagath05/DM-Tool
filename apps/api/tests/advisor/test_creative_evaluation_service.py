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


# ---------------- pure: evidence-source labelling (Phase 13) ----------------
def test_evidence_source_labelling():
    from aicmo.modules.advisor.creative_evaluation_service import _evidence_source
    from aicmo.modules.marketing_analytics.creative_evaluation import CreativeSample

    def _cs(prov: Provenance, source: str) -> CreativeSample:
        return CreativeSample(
            provenance=prov, metrics={"views": 1.0}, platform="youtube", fmt="video", source=source
        )

    # any comparable (AI/human) sample from a connected account => provider_verified
    assert (
        _evidence_source([_cs(Provenance.AI, "provider"), _cs(Provenance.HUMAN, "local")])
        == "provider_verified"
    )
    # only fixture/local comparable samples => local_only
    assert (
        _evidence_source([_cs(Provenance.AI, "local"), _cs(Provenance.HUMAN, "local")])
        == "local_only"
    )
    # no comparable (only unknown) samples => none, even if provider-collected
    assert _evidence_source([_cs(Provenance.UNKNOWN, "provider")]) == "none"
    assert _evidence_source([]) == "none"


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


def test_no_significant_difference_recommends_a_controlled_test():
    resp = shape_response(_eval(Verdict.NO_SIGNIFICANT_DIFFERENCE))
    assert resp.verdict == "NO_SIGNIFICANT_DIFFERENCE"
    action = (resp.recommended_action + " ".join(resp.alternatives)).lower()
    assert "test" in action or "control" in action  # controlled testing, not a claimed winner
    assert "generate more ai" not in action
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


@pytest.mark.asyncio
async def test_record_creative_recommendation_uses_dedicated_write_session():
    """Hermetic H1 pin: request session is never committed; write session is."""
    from contextlib import asynccontextmanager
    from unittest.mock import AsyncMock, MagicMock, patch

    request_session = AsyncMock()
    request_session.commit = AsyncMock()
    attached = MagicMock()
    attached.id = uuid.uuid4()
    attached.status = "not_started"
    request_session.get = AsyncMock(return_value=attached)

    write_session = AsyncMock()
    write_session.commit = AsyncMock()

    @asynccontextmanager
    async def _fake_session_local():
        yield write_session

    tenant = SimpleNamespace(
        organization_id=uuid.uuid4(),
        brand_id=uuid.uuid4(),
        user_id=str(uuid.uuid4()),
    )
    response = shape_response(_eval(Verdict.AI_UNDERPERFORMING, confidence=80))
    fake_row = MagicMock()
    fake_row.id = attached.id
    fake_row.status = "not_started"

    with (
        patch(
            "aicmo.db.session.SessionLocal",
            _fake_session_local,
        ),
        patch(
            "aicmo.modules.advisor.creative_evaluation_service._upsert_recommendation",
            new=AsyncMock(return_value=fake_row),
        ) as upsert,
    ):
        out = await record_creative_recommendation(
            request_session, tenant=tenant, response=response
        )

    assert out is attached
    upsert.assert_awaited_once()
    assert upsert.await_args.args[0] is write_session
    write_session.commit.assert_awaited_once()
    request_session.commit.assert_not_awaited()
    from aicmo.modules.advisor.models import AdvisorRecommendation

    expected_rec_id = uuid.uuid5(
        uuid.NAMESPACE_URL, f"creative_eval:{tenant.brand_id}:{response.verdict}"
    )
    request_session.get.assert_awaited_once_with(AdvisorRecommendation, expected_rec_id)


@pytest.mark.asyncio
async def test_record_insufficient_evidence_does_not_commit():
    from unittest.mock import AsyncMock, patch

    session = AsyncMock()
    session.commit = AsyncMock()
    tenant = SimpleNamespace(
        organization_id=uuid.uuid4(),
        brand_id=uuid.uuid4(),
        user_id=str(uuid.uuid4()),
    )
    response = shape_response(
        CreativeEvaluation(
            verdict=Verdict.INSUFFICIENT_EVIDENCE,
            confidence=0,
            ai_sample_size=0,
            human_sample_size=0,
            unknown_sample_size=0,
            evidence=[],
            limitations=["thin"],
        )
    )
    with patch("aicmo.db.session.SessionLocal") as session_local:
        out = await record_creative_recommendation(session, tenant=tenant, response=response)
    assert out is None
    session.commit.assert_not_awaited()
    session_local.assert_not_called()


# ---------------- real-Postgres integration ----------------
def _pg():
    from tests._dbtest import pg_reachable

    if not pg_reachable():
        pytest.skip("Postgres not reachable")


def _engine():
    from sqlalchemy.ext.asyncio import create_async_engine

    from tests._dbtest import async_dsn

    return create_async_engine(async_dsn())


def _patch_session_local(monkeypatch, eng):
    """Point the app's SessionLocal at the test engine so dedicated write
    sessions in record_creative_recommendation hit the same DB as the test."""
    from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

    factory = async_sessionmaker(bind=eng, expire_on_commit=False, class_=AsyncSession)
    monkeypatch.setattr("aicmo.db.session.SessionLocal", factory)


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


async def _seed_brand(
    session,
    *,
    org,
    brand,
    user,
    ai_views,
    human_views,
    ai_eng,
    human_eng,
    tag,
    integration_connection_id=None,
):
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
            integration_connection_id=integration_connection_id,
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
        # Seeded fixtures have no integration connection → labelled local, never
        # dressed up as live provider data.
        assert resp.evidence_source == "local_only"
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
async def test_recommendation_persists_advisory_and_is_audited(monkeypatch):
    _pg()
    from sqlalchemy import text
    from sqlalchemy.ext.asyncio import AsyncSession

    from aicmo.modules.advisor.creative_evaluation_service import evaluate_creative

    org, brand, user = uuid.uuid4(), uuid.uuid4(), uuid.uuid4()
    tag = uuid.uuid4().hex[:8]
    eng = _engine()
    _patch_session_local(monkeypatch, eng)
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
            assert resp.human_approval_required is True
            rec = await record_creative_recommendation(s, tenant=tenant, response=resp)
            # Dedicated write session already committed; request session need not.
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
async def test_human_rejection_is_authoritative_across_reevaluation(monkeypatch):
    _pg()
    from sqlalchemy import text
    from sqlalchemy.ext.asyncio import AsyncSession

    from aicmo.modules.advisor.creative_evaluation_service import evaluate_creative

    org, brand, user = uuid.uuid4(), uuid.uuid4(), uuid.uuid4()
    tag = uuid.uuid4().hex[:8]
    eng = _engine()
    _patch_session_local(monkeypatch, eng)
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
            assert rec is not None
            rec_id = rec.id
            # Human rejects on the request session — object must still be attached.
            rec.status = "skipped"
            await s.commit()
        # Re-evaluation (same fingerprint) must NOT resurrect a rejected rec.
        async with AsyncSession(eng, expire_on_commit=False) as s:
            resp2 = await evaluate_creative(s, tenant=tenant)
            await record_creative_recommendation(s, tenant=tenant, response=resp2)
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


@pytest.mark.asyncio
async def test_generate_persists_recommendation_that_feeds_outcome_loop(monkeypatch):
    """The Advisor-workflow entry point persists an actionable verdict as a
    normal AdvisorRecommendation (source_surface=creative_evaluation) with an
    expected_result — i.e. it enters the SAME recommendation table the existing
    outcome/effectiveness loop evaluates, as advisory (status not_started)."""
    _pg()
    from sqlalchemy import text
    from sqlalchemy.ext.asyncio import AsyncSession

    from aicmo.modules.advisor.creative_evaluation_service import (
        generate_creative_recommendation,
    )

    org, brand, user = uuid.uuid4(), uuid.uuid4(), uuid.uuid4()
    tag = uuid.uuid4().hex[:8]
    eng = _engine()
    _patch_session_local(monkeypatch, eng)
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
            resp = await generate_creative_recommendation(s, tenant=tenant)
            # Dedicated write session already committed; no request-session commit.
            assert resp.verdict in ("AI_UNDERPERFORMING", "HUMAN_OUTPERFORMING")
            assert resp.human_approval_required is True
        async with AsyncSession(eng, expire_on_commit=False) as s:
            row = (
                await s.execute(
                    text(
                        "SELECT id, status, record_type, expected_result, source_surface "
                        "FROM advisor_recommendations WHERE brand_id=:b AND source_surface='creative_evaluation'"
                    ),
                    {"b": brand},
                )
            ).one()
            rec_id = row[0]
            assert row[1] == "not_started"  # advisory — never auto-executed
            assert row[2] == "recommendation_created"  # normal rec the loop tracks
            assert row[3] and row[3].strip()  # expected_result set → outcome loop can compare
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
async def test_evidence_source_provider_verified_when_from_connected_account():
    """Cohort assembled from provider-collected SocialAssets (an integration
    connection is present) is labelled provider_verified — the honest 'this is
    live provider data' signal for the UI/advisor."""
    _pg()
    from sqlalchemy import text
    from sqlalchemy.ext.asyncio import AsyncSession

    from aicmo.modules.advisor.creative_evaluation_service import evaluate_creative

    org, brand, user = uuid.uuid4(), uuid.uuid4(), uuid.uuid4()
    conn_id = uuid.uuid4()
    tag = uuid.uuid4().hex[:8]
    eng = _engine()
    try:
        async with AsyncSession(eng, expire_on_commit=False) as s:
            await _seed_tenant(s, org=org, brands=[brand], user=user, tag=tag)
            await s.execute(
                text(
                    "INSERT INTO integration_connection "
                    "(id, organization_id, brand_id, provider_slug, state, scopes_granted) "
                    "VALUES (:i,:o,:b,'youtube','ACTIVE','[]'::jsonb)"
                ),
                {"i": conn_id, "o": org, "b": brand},
            )
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
                integration_connection_id=conn_id,
            )
            await s.commit()
        tenant = SimpleNamespace(organization_id=org, brand_id=brand, user_id=str(user))
        async with AsyncSession(eng, expire_on_commit=False) as s:
            resp = await evaluate_creative(s, tenant=tenant)
        assert resp.evidence_source == "provider_verified"
        assert resp.verdict in ("AI_UNDERPERFORMING", "HUMAN_OUTPERFORMING")
    finally:
        async with eng.begin() as conn:
            await conn.execute(
                text(
                    "DELETE FROM performance_signals WHERE asset_id IN "
                    "(SELECT id FROM social_assets WHERE brand_id=:b)"
                ),
                {"b": brand},
            )
            await conn.execute(text("DELETE FROM social_assets WHERE brand_id=:b"), {"b": brand})
            await conn.execute(
                text("DELETE FROM integration_connection WHERE id=:i"), {"i": conn_id}
            )
            await conn.execute(text("DELETE FROM brands WHERE organization_id=:o"), {"o": org})
            await conn.execute(text("DELETE FROM organizations WHERE id=:o"), {"o": org})
            await conn.execute(text("DELETE FROM users WHERE id=:u"), {"u": user})
        await eng.dispose()


@pytest.mark.asyncio
async def test_account_level_revenue_is_not_treated_as_per_creative():
    """YouTube-style organic cohorts carry views/engagement only — revenue must
    NOT appear as a per-creative metric and MUST be surfaced as a limitation,
    even if account-level revenue exists elsewhere (ConnectorMetric)."""
    _pg()
    from sqlalchemy import text
    from sqlalchemy.ext.asyncio import AsyncSession

    from aicmo.modules.advisor.creative_evaluation_service import evaluate_creative

    org, brand, user = uuid.uuid4(), uuid.uuid4(), uuid.uuid4()
    tag = uuid.uuid4().hex[:8]
    eng = _engine()
    try:
        async with AsyncSession(eng, expire_on_commit=False) as s:
            await _seed_tenant(s, org=org, brands=[brand], user=user, tag=tag)
            # Account-level revenue exists as a ConnectorMetric — must NOT leak
            # into the per-creative comparison.
            await s.execute(
                text(
                    "INSERT INTO connector_metrics "
                    "(id, brand_id, provider_slug, metric_key, metric_value, synced_at) "
                    "VALUES (:i,:b,'youtube','revenue',9999,now())"
                ),
                {"i": uuid.uuid4(), "b": brand},
            )
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
        assert not any(d.metric == "revenue" for d in resp.metric_deltas)
        assert any("revenue" in lim.lower() for lim in resp.evidence_limitations)
    finally:
        async with eng.begin() as conn:
            await conn.execute(
                text("DELETE FROM connector_metrics WHERE brand_id=:b"), {"b": brand}
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
async def test_compose_intelligence_fallback_persists_creative_recommendation(monkeypatch):
    """H1 regression: compose_intelligence() → creative rec → LLM failure →
    deterministic_report must still leave the recommendation durable after the
    dedicated write session closes — WITHOUT committing the request session.
    """
    _pg()
    from unittest.mock import AsyncMock

    from sqlalchemy import text
    from sqlalchemy.ext.asyncio import AsyncSession

    from aicmo.modules.advisor import intelligence
    from aicmo.modules.advisor.brain import BusinessBrain
    from aicmo.modules.advisor.schemas import DataSourceRef
    from aicmo.modules.advisor.signals import IntelligenceSignals
    from aicmo.modules.analytics.schemas import OverviewKpis

    org, brand, user = uuid.uuid4(), uuid.uuid4(), uuid.uuid4()
    tag = uuid.uuid4().hex[:8]
    eng = _engine()
    _patch_session_local(monkeypatch, eng)
    rec_id = None
    enqueue_calls: list = []
    request_commits: list = []

    brain = BusinessBrain(
        industry="Cafe",
        business_type="Coffee shop",
        target_audience="Urban professionals who want specialty coffee",
    )
    ctx = IntelligenceSignals(
        brain=brain,
        brain_complete=True,
        setup_steps=[],
        outcome_context={},
        connector_context={"metrics": [], "has_data": True},
        content_intelligence={},
        lead_context={},
        analytics_signals=["Total leads: 3"],
        data_sources=[DataSourceRef(key="leads_7d", label="Leads (7 days)", value="3")],
        has_outcomes=False,
        has_connectors=True,
        has_content_intel=False,
        has_lead_intel=False,
        activity_signals=1,
        analytics_signal=None,
    )

    class _FailingRouter:
        async def generate(self, **_kw):
            raise RuntimeError("llm unavailable — force deterministic fallback")

    overview = OverviewKpis(
        total_leads=3,
        leads_7d=1,
        leads_30d=3,
        hot_leads=1,
        landing_pages_published=1,
        total_views=10,
        total_submissions=2,
        conversion_rate=0.2,
        top_landing_page_title=None,
        top_landing_page_slug=None,
        top_landing_page_submissions=0,
    )

    monkeypatch.setattr(intelligence, "gather_intelligence_signals", AsyncMock(return_value=ctx))
    monkeypatch.setattr(intelligence, "get_llm_router", lambda: _FailingRouter())
    monkeypatch.setattr(
        intelligence.analytics_service, "overview", AsyncMock(return_value=overview)
    )
    monkeypatch.setattr(
        intelligence,
        "get_settings",
        lambda: SimpleNamespace(
            advisor_intelligence_enabled=True,
            advisor_engine_enabled=True,
        ),
    )
    # generate_creative_recommendation imports get_settings from aicmo.config
    # inside the function body — patch the module it resolves.
    monkeypatch.setattr(
        "aicmo.config.get_settings",
        lambda: SimpleNamespace(
            advisor_intelligence_enabled=True,
            advisor_engine_enabled=True,
        ),
    )
    # Guard: creative path must not enqueue publish/spend work.
    monkeypatch.setattr(
        "aicmo.queue.enqueue.enqueue_tenant_job",
        AsyncMock(side_effect=lambda *a, **k: enqueue_calls.append((a, k)) or None),
    )

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
        # One request-scoped session — close WITHOUT an outer commit, like get_db().
        async with AsyncSession(eng, expire_on_commit=False) as s:
            original_commit = s.commit

            async def _tracked_commit(*a, **k):
                request_commits.append(True)
                return await original_commit(*a, **k)

            s.commit = _tracked_commit  # type: ignore[method-assign]
            report = await intelligence.compose_intelligence(
                s, profile=SimpleNamespace(), tenant=tenant
            )
            assert report.ready is True  # deterministic fallback path
            # Deliberately no s.commit() here — and the persist path must not
            # have committed this request session either.
            assert request_commits == []

        # Fresh session after dedicated write-session lifecycle — durable.
        async with AsyncSession(eng, expire_on_commit=False) as s:
            row = (
                await s.execute(
                    text(
                        "SELECT id, brand_id, organization_id, status, record_type, "
                        "source_surface, expected_result, description "
                        "FROM advisor_recommendations "
                        "WHERE brand_id=:b AND source_surface='creative_evaluation'"
                    ),
                    {"b": brand},
                )
            ).one()
            rec_id = row[0]
            assert row[1] == brand
            assert row[2] == org
            assert row[3] == "not_started"
            assert row[4] == "recommendation_created"
            assert row[5] == "creative_evaluation"
            assert row[6] and str(row[6]).strip()  # expected_result present → actionable
            assert row[7] and str(row[7]).strip()  # recommended action persisted

        # Human approval still required: advisory status + no enqueue/publish/spend.
        assert enqueue_calls == []
    finally:
        async with eng.begin() as conn:
            if rec_id:
                await conn.execute(
                    text("DELETE FROM advisor_memory_events WHERE recommendation_id=:r"),
                    {"r": rec_id},
                )
                await conn.execute(
                    text("DELETE FROM advisor_recommendations WHERE id=:r"),
                    {"r": rec_id},
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
async def test_compose_intelligence_success_persists_creative_recommendation(monkeypatch):
    """H1 regression (LLM-success path): compose_intelligence() → creative rec →
    the main intelligence LLM SUCCEEDS → the creative recommendation must STILL
    be durable after the dedicated write session closes, WITHOUT committing the
    request session. Complements the LLM-fallback regression above so both
    branches of the integration seam are pinned.
    """
    _pg()
    from unittest.mock import AsyncMock

    from sqlalchemy import text
    from sqlalchemy.ext.asyncio import AsyncSession

    from aicmo.modules.advisor import intelligence
    from aicmo.modules.advisor.brain import BusinessBrain
    from aicmo.modules.advisor.intelligence import _IntelligenceNarrative, _NarrativeRec
    from aicmo.modules.advisor.schemas import DataSourceRef
    from aicmo.modules.advisor.signals import IntelligenceSignals

    org, brand, user = uuid.uuid4(), uuid.uuid4(), uuid.uuid4()
    tag = uuid.uuid4().hex[:8]
    eng = _engine()
    _patch_session_local(monkeypatch, eng)
    rec_id = None
    enqueue_calls: list = []
    request_commits: list = []
    generate_calls: list = []

    brain = BusinessBrain(
        industry="Cafe",
        business_type="Coffee shop",
        target_audience="Urban professionals who want specialty coffee",
    )
    ctx = IntelligenceSignals(
        brain=brain,
        brain_complete=True,
        setup_steps=[],
        outcome_context={},
        connector_context={"metrics": [], "has_data": True},
        content_intelligence={},
        lead_context={},
        analytics_signals=["Total leads: 3"],
        data_sources=[DataSourceRef(key="leads_7d", label="Leads (7 days)", value="3")],
        has_outcomes=False,
        has_connectors=True,
        has_content_intel=False,
        has_lead_intel=False,
        activity_signals=1,
        analytics_signal=None,
    )

    narrative = _IntelligenceNarrative(
        daily_brief_what_happened="Leads grew modestly versus the prior week.",
        daily_brief_why="More consistent posting lifted profile visits and saves.",
        daily_brief_confidence=55,
        hero=_NarrativeRec(
            observation="Short-form reels reach more new accounts than static posts.",
            root_cause="The platform distributes short video to non-followers more widely.",
            recommended_action="Publish two more reels this week using your top format.",
            expected_impact="Likely 5-10 more profile visits and 1-2 leads.",
            confidence=55,
            data_sources_used=[DataSourceRef(key="leads_7d", label="Leads (7 days)", value="3")],
        ),
    )

    class _SuccessRouter:
        async def generate(self, **_kw):
            generate_calls.append(True)
            return SimpleNamespace(data=narrative)

    monkeypatch.setattr(intelligence, "gather_intelligence_signals", AsyncMock(return_value=ctx))
    monkeypatch.setattr(intelligence, "get_llm_router", lambda: _SuccessRouter())
    # In the compose path, advisor_engine_enabled=False skips the separate hero/
    # opportunity persistence so this test isolates the creative-rec durability;
    # generate_creative_recommendation reads aicmo.config settings (engine on).
    monkeypatch.setattr(
        intelligence,
        "get_settings",
        lambda: SimpleNamespace(
            advisor_intelligence_enabled=True,
            advisor_engine_enabled=False,
        ),
    )
    monkeypatch.setattr(
        "aicmo.config.get_settings",
        lambda: SimpleNamespace(
            advisor_intelligence_enabled=True,
            advisor_engine_enabled=True,
        ),
    )
    # Guard: creative path must not enqueue publish/spend work.
    monkeypatch.setattr(
        "aicmo.queue.enqueue.enqueue_tenant_job",
        AsyncMock(side_effect=lambda *a, **k: enqueue_calls.append((a, k)) or None),
    )

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
            original_commit = s.commit

            async def _tracked_commit(*a, **k):
                request_commits.append(True)
                return await original_commit(*a, **k)

            s.commit = _tracked_commit  # type: ignore[method-assign]
            report = await intelligence.compose_intelligence(
                s, profile=SimpleNamespace(), tenant=tenant
            )
            # LLM-success branch: the router was invoked and did NOT raise, so
            # compose took the narrative path (not the deterministic fallback).
            assert generate_calls == [True]
            assert report.ready is True
            # Creative rec used its own write session — request session untouched.
            assert request_commits == []

        # Fresh session after the dedicated write-session lifecycle — durable.
        async with AsyncSession(eng, expire_on_commit=False) as s:
            row = (
                await s.execute(
                    text(
                        "SELECT id, brand_id, organization_id, status, record_type, "
                        "source_surface, expected_result, description "
                        "FROM advisor_recommendations "
                        "WHERE brand_id=:b AND source_surface='creative_evaluation'"
                    ),
                    {"b": brand},
                )
            ).one()
            rec_id = row[0]
            assert row[1] == brand
            assert row[2] == org
            assert row[3] == "not_started"  # advisory — never auto-approved/executed
            assert row[4] == "recommendation_created"
            assert row[5] == "creative_evaluation"
            assert row[6] and str(row[6]).strip()  # expected_result present → actionable
            assert row[7] and str(row[7]).strip()  # recommended action persisted

        # Human approval still required: advisory status + no enqueue/publish/spend.
        assert enqueue_calls == []
    finally:
        async with eng.begin() as conn:
            if rec_id:
                await conn.execute(
                    text("DELETE FROM advisor_memory_events WHERE recommendation_id=:r"),
                    {"r": rec_id},
                )
                await conn.execute(
                    text("DELETE FROM advisor_recommendations WHERE id=:r"),
                    {"r": rec_id},
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
async def test_record_creative_recommendation_does_not_commit_request_session_dirtiness(
    monkeypatch,
):
    """Transaction-isolation regression: unrelated pending work on the request
    session must NOT be committed when the dedicated recommendation write
    session commits. Proves durability + isolation against real Postgres.
    """
    _pg()
    from sqlalchemy import text
    from sqlalchemy.ext.asyncio import AsyncSession

    from aicmo.modules.orgs.models import OrganizationMember

    org = uuid.uuid4()
    brand_a = uuid.uuid4()
    brand_b = uuid.uuid4()
    user = uuid.uuid4()
    member_id = uuid.uuid4()
    tag = uuid.uuid4().hex[:8]
    eng = _engine()
    _patch_session_local(monkeypatch, eng)
    rec_id = None

    try:
        async with AsyncSession(eng, expire_on_commit=False) as s:
            await _seed_tenant(s, org=org, brands=[brand_a, brand_b], user=user, tag=tag)
            await s.execute(
                text(
                    "INSERT INTO organization_members "
                    "(id, organization_id, user_id, last_active_brand_id, status) "
                    "VALUES (:i,:o,:u,:b,'active')"
                ),
                {"i": member_id, "o": org, "u": user, "b": brand_a},
            )
            await _seed_brand(
                s,
                org=org,
                brand=brand_a,
                user=user,
                ai_views=700,
                human_views=1300,
                ai_eng=0.018,
                human_eng=0.034,
                tag=f"{tag}a",
            )
            await s.commit()

        tenant = SimpleNamespace(organization_id=org, brand_id=brand_a, user_id=str(user))
        response = shape_response(_eval(Verdict.AI_UNDERPERFORMING, confidence=80))

        # Request session carries unrelated tenancy dirtiness — never committed.
        async with AsyncSession(eng, expire_on_commit=False) as request_session:
            member = await request_session.get(OrganizationMember, member_id)
            assert member is not None
            assert member.last_active_brand_id == brand_a
            member.last_active_brand_id = brand_b  # dirty, uncommitted
            await request_session.flush()  # visible in this txn only

            rec = await record_creative_recommendation(
                request_session, tenant=tenant, response=response
            )
            assert rec is not None
            rec_id = rec.id
            # Deliberately roll back / close without committing request dirtiness.
            await request_session.rollback()

        # Fresh session: recommendation durable; tenancy preference NOT updated.
        async with AsyncSession(eng, expire_on_commit=False) as s:
            status = (
                await s.execute(
                    text(
                        "SELECT status, brand_id, organization_id FROM advisor_recommendations "
                        "WHERE id=:r"
                    ),
                    {"r": rec_id},
                )
            ).one()
            assert status[0] == "not_started"
            assert status[1] == brand_a
            assert status[2] == org

            sticky = (
                await s.execute(
                    text("SELECT last_active_brand_id FROM organization_members WHERE id=:m"),
                    {"m": member_id},
                )
            ).scalar_one()
            assert sticky == brand_a  # unrelated mutation must NOT have persisted
    finally:
        async with eng.begin() as conn:
            if rec_id:
                await conn.execute(
                    text("DELETE FROM advisor_memory_events WHERE recommendation_id=:r"),
                    {"r": rec_id},
                )
                await conn.execute(
                    text("DELETE FROM advisor_recommendations WHERE id=:r"),
                    {"r": rec_id},
                )
            await conn.execute(
                text("DELETE FROM organization_members WHERE id=:m"), {"m": member_id}
            )
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
