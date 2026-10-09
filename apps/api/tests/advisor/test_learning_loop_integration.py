"""Phase 7.2 — the measured-outcome -> belief learning loop is now CLOSED.

The belief-formation pipeline (belief.formation / belief.tasks.form_brand_beliefs)
already existed and was worker-registered, but nothing ever triggered it. This
phase wires it into `advisor.tasks.evaluate_advisor_outcomes`, so evaluating a
tenant's outcomes also forms evidence-backed beliefs from the eligible ones.

These real-Postgres tests prove the WIRING end-to-end (the formation pipeline's
own invariants — eligibility, contradiction, cross-tenant rejection, sanitised
statements — are covered in tests/belief/test_formation.py):

  * an evaluated outcome causes the task to form a belief, with the outcome kept
    as provenance, and that belief is then resolvable for a later agent turn;
  * re-running the task is idempotent (no duplicate belief/evidence);
  * an insufficient-data outcome produces NO belief.

Confidence/status are derived by the belief service, never set by this phase.
Skips cleanly when no project Postgres is reachable (tests/_dbtest).
"""

from __future__ import annotations

import uuid
from datetime import UTC, datetime

import pytest


def _tenant_ctx(*, org, brand, user):
    from aicmo.tenancy.context import TenantContext

    return TenantContext(
        user_id=str(user),
        user_uuid=user,
        organization_id=org,
        brand_id=brand,
        member_id=uuid.uuid4(),
        role_slugs=frozenset({"owner"}),
        permissions=frozenset(),
    )


async def _seed_evaluated_outcome(session, *, org, brand, user, status, score):
    """Seed a recommendation + an outcome already in `status` (no _evaluate_one
    run needed — that path requires real lead data and is tested elsewhere)."""
    from aicmo.modules.advisor.models import AdvisorOutcome, AdvisorRecommendation

    rec = AdvisorRecommendation(
        id=uuid.uuid4(), organization_id=org, brand_id=brand, user_id=str(user),
        record_type="opportunity", title="Publish a lead page", source_surface="coach",
        source_fingerprint=uuid.uuid4().hex,
    )
    session.add(rec)
    await session.flush()
    outcome = AdvisorOutcome(
        id=uuid.uuid4(), brand_id=brand, recommendation_id=rec.id,
        evaluation_status=status, effectiveness_score=score,
        evaluate_after=datetime.now(UTC), evaluated_at=datetime.now(UTC),
        delta_summary="Leads +3 in the window.",
        baseline_snapshot={}, outcome_snapshot={},
    )
    session.add(outcome)
    await session.flush()
    return outcome.id


@pytest.mark.asyncio
async def test_evaluate_task_forms_belief_from_outcome_and_surfaces_it():
    from tests._dbtest import pg_reachable

    if not pg_reachable():
        pytest.skip("Postgres not reachable")

    from sqlalchemy import func, select, text
    from sqlalchemy.ext.asyncio import AsyncSession, create_async_engine

    import aicmo.main  # noqa: F401 — registers the full ORM graph
    from aicmo.modules.advisor.tasks import evaluate_advisor_outcomes
    from aicmo.modules.belief.enums import EvidenceRefKind
    from aicmo.modules.belief.models import Belief, BeliefEvidence
    from aicmo.modules.belief.resolver import resolve_beliefs
    from aicmo.queue.enqueue import TenantEnvelope
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
            # One evaluated (measured, positive) outcome, and one insufficient-data outcome.
            good = await _seed_evaluated_outcome(s, org=org, brand=brand, user=user, status="evaluated", score=70)
            await _seed_evaluated_outcome(s, org=org, brand=brand, user=user, status="insufficient_data", score=None)
            await s.commit()

        envelope = TenantEnvelope.from_context(_tenant_ctx(org=org, brand=brand, user=user))

        # Run the WIRED task (undecorated via functools.wraps) with our session.
        async with AsyncSession(eng, expire_on_commit=False) as s:
            res = await evaluate_advisor_outcomes.__wrapped__({}, s, envelope)
            await s.commit()
        assert res["beliefs_formed"] == 1  # only the evaluated outcome formed a belief

        async with AsyncSession(eng, expire_on_commit=False) as s:
            # Exactly one belief, with the outcome kept as provenance.
            beliefs = (await s.execute(select(Belief).where(Belief.brand_id == brand))).scalars().all()
            assert len(beliefs) == 1
            belief = beliefs[0]
            assert belief.confidence is not None  # derived by the belief service
            ev = (await s.execute(
                select(BeliefEvidence).where(
                    BeliefEvidence.belief_id == belief.id,
                    BeliefEvidence.ref_kind == EvidenceRefKind.ADVISOR_OUTCOME.value,
                )
            )).scalars().all()
            assert [e.ref_id for e in ev] == [good]  # provenance → the measured outcome

            # Surfaced for a later agent turn via the resolver (a supporting
            # outcome yields an ACTIVE belief).
            resolution = await resolve_beliefs(s, tenant=_tenant_ctx(org=org, brand=brand, user=user))
            all_views = (
                list(resolution.active) + list(resolution.superseded) + list(resolution.contradicted)
            )
            assert any(v.id == belief.id for v in all_views)

        # Idempotent: re-running forms nothing new.
        async with AsyncSession(eng, expire_on_commit=False) as s:
            res2 = await evaluate_advisor_outcomes.__wrapped__({}, s, envelope)
            await s.commit()
        assert res2["beliefs_formed"] == 0

        async with AsyncSession(eng, expire_on_commit=False) as s:
            count = (await s.execute(select(func.count()).select_from(Belief).where(Belief.brand_id == brand))).scalar_one()
            assert count == 1  # no duplicate belief
    finally:
        async with eng.begin() as conn:
            await conn.execute(text("DELETE FROM belief_evidence WHERE brand_id=:b"), {"b": brand})
            await conn.execute(text("DELETE FROM beliefs WHERE brand_id=:b"), {"b": brand})
            await conn.execute(text("DELETE FROM advisor_outcomes WHERE brand_id=:b"), {"b": brand})
            await conn.execute(text("DELETE FROM advisor_recommendations WHERE organization_id=:o"), {"o": org})
            await conn.execute(text("DELETE FROM brands WHERE organization_id=:o"), {"o": org})
            await conn.execute(text("DELETE FROM organizations WHERE id=:o"), {"o": org})
            await conn.execute(text("DELETE FROM users WHERE id=:u"), {"u": user})
        await eng.dispose()
