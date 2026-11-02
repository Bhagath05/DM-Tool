"""Phase 7.17 — the AI Coach grounded in the brand's evidence-graded beliefs.

Proves the Coach became an evidence-grounded intelligence layer WITHOUT a new
memory system: it reads the shared belief-grounding foundation and injects it
into every recommendation surface (reality check, weekly plan, analytics
summary), stays honest when there is no evidence (INSUFFICIENT_EVIDENCE rather
than invented outcomes), degrades gracefully when grounding fails, and never
leaks another brand's beliefs.

Two layers:
  * Prompt/plumbing unit tests — no DB. The three system prompts carry the
    LEARNED-BELIEFS discipline; the three user-prompt builders inject the belief
    block and fall back to INSUFFICIENT_EVIDENCE framing when it is empty.
  * Real-Postgres tests — ``coach_belief_block`` grounds in ACTIVE beliefs,
    surfaces CONTRADICTED ones, is INSUFFICIENT_EVIDENCE for an empty brand, and
    is brand-isolated. Skips cleanly when no project Postgres is reachable.

Confidence/status come from the belief memory; this phase never asserts them.
"""

from __future__ import annotations

import uuid
from datetime import UTC, datetime
from types import SimpleNamespace

import pytest

from aicmo.modules.coach.prompts import (
    ANALYTICS_SUMMARY_SYSTEM_PROMPT,
    SYSTEM_PROMPT,
    WEEKLY_SYSTEM_PROMPT,
    _belief_section,
    build_analytics_summary_user_prompt,
    build_user_prompt,
    build_weekly_user_prompt,
)

# A sentinel the real belief resolver would never emit, so finding it in a
# rendered prompt proves the Coach injected the grounding block we handed it.
_SENTINEL = "SENTINEL-BELIEF::reels-beat-static-for-leads"


def _fake_profile() -> SimpleNamespace:
    """Minimal stand-in for BusinessProfileResponse — only the attributes the
    prompt builders read. Builders format attributes into an f-string; they never
    validate the type, so a namespace keeps these unit tests DB-free."""
    return SimpleNamespace(
        business_name="Acme Coffee",
        industry="specialty coffee",
        business_location="Austin, TX",
        current_monthly_leads_band="0-10",
        monthly_budget_band="$0-100",
        preferred_platforms=["instagram"],
        target_audience="local coffee lovers",
        primary_goal_text="get my first 20 leads",
    )


# ---------------------------------------------------------------------
#  System prompts carry the LEARNED-BELIEFS discipline (all 3 surfaces)
# ---------------------------------------------------------------------


@pytest.mark.parametrize(
    "system_prompt",
    [SYSTEM_PROMPT, WEEKLY_SYSTEM_PROMPT, ANALYTICS_SUMMARY_SYSTEM_PROMPT],
)
def test_system_prompts_carry_learned_belief_discipline(system_prompt: str):
    # The discipline that makes the Coach prefer validated beliefs over guesses
    # and stay honest under insufficient evidence must be present on every surface.
    assert "LEARNED BELIEFS" in system_prompt
    assert "high-confidence ACTIVE belief" in system_prompt
    assert "INSUFFICIENT_EVIDENCE" in system_prompt
    assert "never claim a learned result you do not have" in system_prompt


# ---------------------------------------------------------------------
#  _belief_section — the single injection point all 3 builders share
# ---------------------------------------------------------------------


def test_belief_section_renders_the_block_verbatim():
    out = _belief_section(_SENTINEL)
    assert _SENTINEL in out
    assert "LEARNED" in out
    # A real block must NOT be reframed as "no beliefs".
    assert "no validated beliefs yet" not in out


def test_belief_section_insufficient_evidence_fallback_when_empty():
    out = _belief_section("")
    assert "INSUFFICIENT_EVIDENCE" in out
    assert "hypothesis" in out.lower()
    # Honest, not fabricated: nothing but the fallback note.
    assert _SENTINEL not in out


# ---------------------------------------------------------------------
#  Each user-prompt builder injects the belief block (evidence injection)
#  and degrades to INSUFFICIENT_EVIDENCE framing when there is none.
# ---------------------------------------------------------------------


def test_reality_prompt_injects_belief_block():
    prompt = build_user_prompt(
        profile=_fake_profile(),
        goal_text="get my first 20 leads",
        timeline_hint="3 months",
        feasibility_score=55,
        feasibility_label="Aggressive but possible",
        signals=["zero captured leads so far"],
        belief_block=_SENTINEL,
    )
    assert _SENTINEL in prompt
    assert "LEARNED" in prompt


def test_reality_prompt_insufficient_evidence_when_no_beliefs():
    prompt = build_user_prompt(
        profile=_fake_profile(),
        goal_text="get my first 20 leads",
        timeline_hint=None,
        feasibility_score=55,
        feasibility_label="Aggressive but possible",
        signals=[],
        belief_block="",
    )
    assert "INSUFFICIENT_EVIDENCE" in prompt


def test_weekly_prompt_injects_belief_block():
    prompt = build_weekly_user_prompt(
        profile=_fake_profile(),
        signals=["zero captured leads so far"],
        recent_activity={},
        has_published_page=False,
        top_asset_summary=None,
        trends_summary=None,
        analysis_phase_summary=None,
        analysis_channels=[],
        belief_block=_SENTINEL,
    )
    assert _SENTINEL in prompt
    assert "LEARNED" in prompt


def test_weekly_prompt_insufficient_evidence_when_no_beliefs():
    prompt = build_weekly_user_prompt(
        profile=_fake_profile(),
        signals=[],
        recent_activity={},
        has_published_page=False,
        top_asset_summary=None,
        trends_summary=None,
        analysis_phase_summary=None,
        analysis_channels=[],
        belief_block="",
    )
    assert "INSUFFICIENT_EVIDENCE" in prompt


def test_analytics_summary_prompt_injects_belief_block():
    prompt = build_analytics_summary_user_prompt(
        profile_name="Acme Coffee",
        profile_stage="0-10 band",
        overview={},
        timeline_summary="(no daily timeline available)",
        sources_summary="(no source data yet)",
        landing_pages_summary="(no published landing pages yet)",
        top_assets_summary="(no converting assets yet)",
        belief_block=_SENTINEL,
    )
    assert _SENTINEL in prompt
    assert "LEARNED" in prompt


def test_analytics_summary_prompt_insufficient_evidence_when_no_beliefs():
    prompt = build_analytics_summary_user_prompt(
        profile_name="Acme Coffee",
        profile_stage=None,
        overview={},
        timeline_summary="(no daily timeline available)",
        sources_summary="(no source data yet)",
        landing_pages_summary="(no published landing pages yet)",
        top_assets_summary="(no converting assets yet)",
        belief_block="",
    )
    assert "INSUFFICIENT_EVIDENCE" in prompt


# ---------------------------------------------------------------------
#  coach_belief_block degrades gracefully — a grounding miss must never
#  break an advisory Coach response (returns "" so the prompt renders
#  INSUFFICIENT_EVIDENCE rather than raising).
# ---------------------------------------------------------------------


@pytest.mark.asyncio
async def test_coach_belief_block_degrades_to_empty_on_grounding_failure(monkeypatch):
    from aicmo.modules.coach import grounding as coach_grounding
    from aicmo.tenancy.context import TenantContext

    async def _boom(*_a, **_k):
        raise RuntimeError("belief store unavailable")

    # Patch the binding captured in the coach grounding module.
    monkeypatch.setattr(coach_grounding, "resolve_evidence_grounding", _boom)

    tenant = TenantContext(
        user_id=str(uuid.uuid4()), user_uuid=uuid.uuid4(),
        organization_id=uuid.uuid4(), brand_id=uuid.uuid4(),
        member_id=uuid.uuid4(), role_slugs=frozenset({"owner"}), permissions=frozenset(),
    )

    # session is never touched before the (patched) resolver raises.
    block = await coach_grounding.coach_belief_block(None, tenant=tenant)
    assert block == ""


# ---------------------------------------------------------------------
#  Real-Postgres: coach_belief_block grounds, surfaces contradictions,
#  is honest on an empty brand, and is brand-isolated.
# ---------------------------------------------------------------------


def _tenant(*, org, brand, user):
    from aicmo.tenancy.context import TenantContext

    return TenantContext(
        user_id=str(user), user_uuid=user, organization_id=org, brand_id=brand,
        member_id=uuid.uuid4(), role_slugs=frozenset({"owner"}), permissions=frozenset(),
    )


async def _seed_brand(conn, *, org, brand, user, tag):
    from sqlalchemy import text

    await conn.execute(text("INSERT INTO users (id, clerk_user_id, email) VALUES (:i,:c,:e)"),
                       {"i": user, "c": f"c{tag}", "e": f"{tag}@t.local"})
    await conn.execute(text("INSERT INTO organizations (id, slug, name, owner_user_id) VALUES (:i,:s,:n,:o)"),
                       {"i": org, "s": f"o{tag}", "n": "O", "o": user})
    await conn.execute(
        text("INSERT INTO brands (id, organization_id, slug, name, created_by_user_id) VALUES (:i,:o,:s,:n,:u)"),
        {"i": brand, "o": org, "s": f"b{tag}", "n": "B", "u": user})


async def _seed_belief(session, *, org, brand, statement, status="active", confidence=80):
    from aicmo.modules.belief.models import Belief

    belief = Belief(
        id=uuid.uuid4(), organization_id=org, brand_id=brand,
        category="channel", subject_key=f"channel:{uuid.uuid4().hex[:8]}",
        statement=statement, scope={}, status=status,
        confidence=confidence, confidence_reason="measured outcomes",
        evidence_count=2, validated_at=datetime.now(UTC),
    )
    session.add(belief)
    await session.flush()


@pytest.mark.asyncio
async def test_coach_belief_block_grounded_contradicted_insufficient_and_isolation():
    from tests._dbtest import pg_reachable

    if not pg_reachable():
        pytest.skip("Postgres not reachable")

    from sqlalchemy import text
    from sqlalchemy.ext.asyncio import AsyncSession, create_async_engine

    import aicmo.main  # noqa: F401  (register ORM models)
    from aicmo.modules.coach.grounding import coach_belief_block
    from tests._dbtest import async_dsn

    eng = create_async_engine(async_dsn())
    ta, tb = uuid.uuid4().hex[:8], uuid.uuid4().hex[:8]
    org_a, brand_a, user_a = uuid.uuid4(), uuid.uuid4(), uuid.uuid4()
    org_b, brand_b, user_b = uuid.uuid4(), uuid.uuid4(), uuid.uuid4()
    empty = uuid.uuid4()
    a_stmt = "Reels beat static for leads"
    b_stmt = "BRAND-B-ONLY must not leak into brand A"
    try:
        async with eng.begin() as conn:
            await _seed_brand(conn, org=org_a, brand=brand_a, user=user_a, tag=ta)
            await _seed_brand(conn, org=org_b, brand=brand_b, user=user_b, tag=tb)
            await conn.execute(
                text("INSERT INTO brands (id, organization_id, slug, name, created_by_user_id) VALUES (:i,:o,:s,:n,:u)"),
                {"i": empty, "o": org_a, "s": f"bz{ta}", "n": "Z", "u": user_a})
        async with AsyncSession(eng, expire_on_commit=False) as s:
            await _seed_belief(s, org=org_a, brand=brand_a, statement=a_stmt, status="active", confidence=82)
            await _seed_belief(s, org=org_a, brand=brand_a, statement="Email open rates were high", status="contradicted", confidence=30)
            await _seed_belief(s, org=org_b, brand=brand_b, statement=b_stmt, status="active", confidence=90)
            await s.commit()

        # Brand A: the Coach block is grounded in A's ACTIVE belief, surfaces the
        # CONTRADICTED one as a do-not-rely warning, and never leaks brand B.
        async with AsyncSession(eng, expire_on_commit=False) as s:
            block_a = await coach_belief_block(s, tenant=_tenant(org=org_a, brand=brand_a, user=user_a))
        assert a_stmt in block_a
        assert "CONTRADICTED" in block_a and "Email open rates" in block_a
        assert b_stmt not in block_a  # cross-brand isolation

        # Empty brand (same org): honest INSUFFICIENT_EVIDENCE, no fabrication and
        # no bleed from the sibling brand's beliefs.
        async with AsyncSession(eng, expire_on_commit=False) as s:
            block_empty = await coach_belief_block(s, tenant=_tenant(org=org_a, brand=empty, user=user_a))
        assert "INSUFFICIENT_EVIDENCE" in block_empty
        assert a_stmt not in block_empty

        # Brand B sees only its own belief (isolation the other direction).
        async with AsyncSession(eng, expire_on_commit=False) as s:
            block_b = await coach_belief_block(s, tenant=_tenant(org=org_b, brand=brand_b, user=user_b))
        assert b_stmt in block_b
        assert a_stmt not in block_b
    finally:
        async with eng.begin() as conn:
            for org_id, user_id in ((org_a, user_a), (org_b, user_b)):
                await conn.execute(text("DELETE FROM beliefs WHERE organization_id=:o"), {"o": org_id})
                await conn.execute(text("DELETE FROM brands WHERE organization_id=:o"), {"o": org_id})
                await conn.execute(text("DELETE FROM organizations WHERE id=:o"), {"o": org_id})
                await conn.execute(text("DELETE FROM users WHERE id=:u"), {"u": user_id})
        await eng.dispose()
