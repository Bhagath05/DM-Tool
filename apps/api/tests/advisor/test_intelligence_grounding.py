"""Phase 7.16 — the Advisor intelligence engine is grounded in belief memory.

Unit: signals_to_prompt_block renders the learned-beliefs section (and the honest
INSUFFICIENT_EVIDENCE framing when empty).
Real-PG: gather_intelligence_signals resolves the brand's beliefs, sets the block
+ provenance, and surfaces them as data-source refs (brand-isolated).
"""

from __future__ import annotations

import uuid
from datetime import UTC, datetime

import pytest

from aicmo.modules.advisor.brain import BusinessBrain
from aicmo.modules.advisor.signals import IntelligenceSignals, signals_to_prompt_block


def _signals(belief_block=""):
    return IntelligenceSignals(
        brain=BusinessBrain(industry="Cafe", business_type="Coffee shop",
                            target_audience="Urban professionals who want specialty coffee"),
        brain_complete=True, setup_steps=[], outcome_context={}, connector_context={},
        content_intelligence={}, lead_context={}, analytics_signals=[],
        belief_block=belief_block,
    )


def test_prompt_renders_learned_beliefs_section():
    out = signals_to_prompt_block(_signals("- [channel] Reels beat static (confidence 82%)"), confidence_cap=55)
    assert "LEARNED BELIEFS" in out
    assert "Reels beat static" in out


def test_prompt_states_insufficient_evidence_when_no_beliefs():
    out = signals_to_prompt_block(_signals(""), confidence_cap=55)
    assert "INSUFFICIENT_EVIDENCE" in out


async def _seed_brand(conn, *, org, brand, user, tag):
    from sqlalchemy import text

    await conn.execute(text("INSERT INTO users (id, clerk_user_id, email) VALUES (:i,:c,:e)"),
                       {"i": user, "c": f"c{tag}", "e": f"{tag}@t.local"})
    await conn.execute(text("INSERT INTO organizations (id, slug, name, owner_user_id) VALUES (:i,:s,:n,:o)"),
                       {"i": org, "s": f"o{tag}", "n": "O", "o": user})
    await conn.execute(
        text("INSERT INTO brands (id, organization_id, slug, name, created_by_user_id) VALUES (:i,:o,:s,:n,:u)"),
        {"i": brand, "o": org, "s": f"b{tag}", "n": "B", "u": user})


@pytest.mark.asyncio
async def test_gather_signals_wires_belief_grounding_and_data_sources():
    from tests._dbtest import pg_reachable

    if not pg_reachable():
        pytest.skip("Postgres not reachable")

    from sqlalchemy import text
    from sqlalchemy.ext.asyncio import AsyncSession, create_async_engine

    import aicmo.main  # noqa: F401
    from aicmo.modules.advisor.signals import gather_intelligence_signals
    from aicmo.modules.belief.models import Belief
    from aicmo.modules.onboarding.schemas import BusinessProfileResponse
    from aicmo.tenancy.context import TenantContext
    from tests._dbtest import async_dsn

    eng = create_async_engine(async_dsn())
    tag = uuid.uuid4().hex[:8]
    org, brand, user = uuid.uuid4(), uuid.uuid4(), uuid.uuid4()
    now = datetime.now(UTC)
    tenant = TenantContext(user_id=str(user), user_uuid=user, organization_id=org, brand_id=brand,
                           member_id=uuid.uuid4(), role_slugs=frozenset({"owner"}), permissions=frozenset())
    profile = BusinessProfileResponse.model_validate({
        "id": uuid.uuid4(), "user_id": str(user), "organization_id": org, "brand_id": brand,
        "business_name": "Brew & Bloom", "industry": "Cafe",
        "target_audience": "Remote workers who want specialty coffee",
        "brand_tone": "warm", "goals": ["more leads"], "preferred_platforms": ["instagram"],
        "analysis_status": "pending", "analysis": None, "analysis_error": None,
        "created_at": now, "updated_at": now,
    })
    try:
        async with eng.begin() as conn:
            await _seed_brand(conn, org=org, brand=brand, user=user, tag=tag)
        async with AsyncSession(eng, expire_on_commit=False) as s:
            s.add(Belief(id=uuid.uuid4(), organization_id=org, brand_id=brand, category="channel",
                         subject_key="channel:reels", statement="Reels beat static for leads", scope={},
                         status="active", confidence=82, confidence_reason="r", evidence_count=2,
                         validated_at=now))
            await s.commit()

        async with AsyncSession(eng, expire_on_commit=False) as s:
            ctx = await gather_intelligence_signals(s, profile=profile, tenant=tenant)

        assert ctx.belief_grounding is not None
        assert ctx.belief_grounding.status == "grounded"
        assert "Reels beat static for leads" in ctx.belief_block
        assert any(ds.key.startswith("belief:") for ds in ctx.data_sources)
    finally:
        async with eng.begin() as conn:
            await conn.execute(text("DELETE FROM beliefs WHERE brand_id=:b"), {"b": brand})
            await conn.execute(text("DELETE FROM brands WHERE organization_id=:o"), {"o": org})
            await conn.execute(text("DELETE FROM organizations WHERE id=:o"), {"o": org})
            await conn.execute(text("DELETE FROM users WHERE id=:u"), {"u": user})
        await eng.dispose()
