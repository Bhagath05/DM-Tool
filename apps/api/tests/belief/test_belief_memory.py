"""Phase 3A — belief memory integration (Postgres-gated).

Covers create/validation/evidence-refs/confidence/scope, tenant isolation +
RLS-compatible scoping, cross-tenant evidence rejection, contradiction ("we were
wrong"), supersession + history, active resolution, insufficient evidence,
deterministic ordering, and the outcome-update ownership guard.
"""

from __future__ import annotations

import uuid

import pytest

from aicmo.modules.belief import resolver, service
from aicmo.modules.belief.enums import BeliefCategory, EvidenceRefKind, EvidenceRelation
from aicmo.modules.belief.schemas import BeliefCreate, EvidenceRefInput


class _T:
    def __init__(self, *, org, brand, user):
        self.organization_id = org
        self.brand_id = brand
        self.user_uuid = user
        self.user_id = str(user)
        self.role_slugs = frozenset()
        self.permissions = frozenset()

    def has_permission(self, slug):
        return False


def _engine():
    from sqlalchemy.ext.asyncio import create_async_engine

    from tests._dbtest import async_dsn

    return create_async_engine(async_dsn())


async def _seed_tenant(session, *, org, brand, user, tag):
    from sqlalchemy import text

    await session.execute(
        text("INSERT INTO users (id, clerk_user_id, email) VALUES (:i,:c,:e)"),
        {"i": user, "c": f"clerk_{tag}", "e": f"{tag}@t.local"},
    )
    await session.execute(
        text("INSERT INTO organizations (id, slug, name, owner_user_id) VALUES (:i,:s,:n,:o)"),
        {"i": org, "s": f"org-{tag}", "n": "Belief Org", "o": user},
    )
    await session.execute(
        text(
            "INSERT INTO brands (id, organization_id, slug, name, created_by_user_id) "
            "VALUES (:i,:o,:s,:n,:u)"
        ),
        {"i": brand, "o": org, "s": f"brand-{tag}", "n": "Belief Brand", "u": user},
    )


async def _seed_evidence(session, *, org, brand, claim) -> uuid.UUID:
    from sqlalchemy import text

    eid = uuid.uuid4()
    await session.execute(
        text(
            "INSERT INTO brain_evidence (id, organization_id, brand_id, kind, category, claim) "
            "VALUES (:i,:o,:b,'observation','marketing',:c)"
        ),
        {"i": eid, "o": org, "b": brand, "c": claim},
    )
    return eid


@pytest.mark.asyncio
async def test_belief_memory_end_to_end():
    from tests._dbtest import pg_reachable

    if not pg_reachable():
        pytest.skip("Postgres not reachable")

    from sqlalchemy import text
    from sqlalchemy.ext.asyncio import AsyncSession

    eng = _engine()
    tag = uuid.uuid4().hex[:8]
    org_a, brand_a, user_a = uuid.uuid4(), uuid.uuid4(), uuid.uuid4()
    org_b, brand_b, user_b = uuid.uuid4(), uuid.uuid4(), uuid.uuid4()
    t_a = _T(org=org_a, brand=brand_a, user=user_a)
    t_b = _T(org=org_b, brand=brand_b, user=user_b)
    try:
        async with AsyncSession(eng, expire_on_commit=False) as s:
            await _seed_tenant(s, org=org_a, brand=brand_a, user=user_a, tag=f"a{tag}")
            await _seed_tenant(s, org=org_b, brand=brand_b, user=user_b, tag=f"b{tag}")
            ev_support = await _seed_evidence(s, org=org_a, brand=brand_a, claim="Reels engaged more")
            ev_contra = await _seed_evidence(s, org=org_a, brand=brand_a, claim="Static engaged more")
            ev_brand_b = await _seed_evidence(s, org=org_b, brand=brand_b, claim="B-only evidence")
            await s.commit()

        # 1. supported belief → ACTIVE with derived confidence
        async with AsyncSession(eng, expire_on_commit=False) as s:
            b_active = await service.create_belief(
                s, tenant=t_a,
                data=BeliefCreate(
                    category=BeliefCategory.CHANNEL,
                    subject_key="reels_vs_static",
                    statement="Reels outperform static for this audience.",
                    scope={"audience": "in_b2c_fitness_18_30", "channel": "instagram"},
                    evidence=[EvidenceRefInput(ref_kind=EvidenceRefKind.BRAIN_EVIDENCE, ref_id=ev_support)],
                ),
            )
            assert b_active.status == "active" and b_active.confidence > 0 and b_active.evidence_count == 1
            # 2. no-evidence belief → UNVALIDATED, confidence 0 (insufficient evidence)
            b_unval = await service.create_belief(
                s, tenant=t_a,
                data=BeliefCreate(category=BeliefCategory.MARKET, subject_key="tam", statement="Market is large."),
            )
            assert b_unval.status == "unvalidated" and b_unval.confidence == 0
            await s.commit()
            active_id = b_active.id

        # 3. cross-tenant evidence reference is rejected
        async with AsyncSession(eng, expire_on_commit=False) as s:
            with pytest.raises(service.BeliefValidationError):
                await service.create_belief(
                    s, tenant=t_a,
                    data=BeliefCreate(
                        category=BeliefCategory.CHANNEL, subject_key="x", statement="uses B evidence",
                        evidence=[EvidenceRefInput(ref_kind=EvidenceRefKind.BRAIN_EVIDENCE, ref_id=ev_brand_b)],
                    ),
                )
            await s.rollback()

        # 4. contradiction → confidence drops, status flips to CONTRADICTED
        async with AsyncSession(eng, expire_on_commit=False) as s:
            before = (await service.get_belief(s, tenant=t_a, belief_id=active_id)).confidence
            b = await service.add_evidence(
                s, tenant=t_a, belief_id=active_id,
                ref=EvidenceRefInput(
                    ref_kind=EvidenceRefKind.BRAIN_EVIDENCE, ref_id=ev_contra,
                    relation=EvidenceRelation.CONTRADICTS,
                ),
            )
            assert b.status == "contradicted" and b.confidence < before
            await s.commit()

        # 5. supersession: new belief replaces an active one; history retained
        async with AsyncSession(eng, expire_on_commit=False) as s:
            older = await service.create_belief(
                s, tenant=t_a,
                data=BeliefCreate(
                    category=BeliefCategory.CREATIVE, subject_key="format", statement="Short-form is best.",
                    evidence=[EvidenceRefInput(ref_kind=EvidenceRefKind.BRAIN_EVIDENCE, ref_id=ev_support)],
                ),
            )
            newer = await service.create_belief(
                s, tenant=t_a,
                data=BeliefCreate(
                    category=BeliefCategory.CREATIVE, subject_key="format", statement="Static converts better here.",
                    evidence=[EvidenceRefInput(ref_kind=EvidenceRefKind.BRAIN_EVIDENCE, ref_id=ev_support)],
                ),
            )
            await service.supersede_belief(s, tenant=t_a, old_belief_id=older.id, new_belief_id=newer.id)
            await s.commit()
            older_id, newer_id = older.id, newer.id

        async with AsyncSession(eng, expire_on_commit=False) as s:
            old_row = await service.get_belief(s, tenant=t_a, belief_id=older_id)
            new_row = await service.get_belief(s, tenant=t_a, belief_id=newer_id)
            assert old_row.status == "superseded" and old_row.superseded_by_id == newer_id
            assert new_row.parent_belief_id == older_id
            res = await resolver.resolve_beliefs(s, tenant=t_a, category="creative", include_history=True)
            assert [b.id for b in res.active] == [newer_id]  # only the current belief is active
            assert older_id in [b.id for b in res.superseded]  # history retained + retrievable

        # 6. tenant isolation: B sees none of A's beliefs; cross-tenant get fails closed
        async with AsyncSession(eng, expire_on_commit=False) as s:
            res_b = await resolver.resolve_beliefs(s, tenant=t_b)
            assert res_b.active == []
            with pytest.raises(service.BeliefNotFoundError):
                await service.get_belief(s, tenant=t_b, belief_id=active_id)

        # 7. supersession cannot cross tenants
        async with AsyncSession(eng, expire_on_commit=False) as s:
            b_of_b = await service.create_belief(
                s, tenant=t_b,
                data=BeliefCreate(category=BeliefCategory.BUSINESS, subject_key="k", statement="B belief."),
            )
            await s.commit()
            with pytest.raises(service.BeliefNotFoundError):
                # old belongs to B, new belongs to A → resolving A's belief under B fails
                await service.supersede_belief(s, tenant=t_b, old_belief_id=b_of_b.id, new_belief_id=newer_id)

        # 8. outcome-update ownership guard: a foreign/nonexistent outcome is rejected
        async with AsyncSession(eng, expire_on_commit=False) as s:
            with pytest.raises(service.BeliefValidationError):
                await service.update_from_outcome(
                    s, tenant=t_a, belief_id=newer_id, outcome_id=uuid.uuid4(),
                    relation=EvidenceRelation.CONTRADICTS,
                )
            await s.rollback()

        # 9. deterministic ordering + insufficient-evidence context
        async with AsyncSession(eng, expire_on_commit=False) as s:
            res = await resolver.resolve_beliefs(s, tenant=t_a)
            keys = [(b.category, b.subject_key) for b in res.active]
            assert keys == sorted(keys)  # deterministic (category, subject_key, …)
            empty = await resolver.resolve_beliefs(s, tenant=t_b)
            block = resolver.to_context_block(empty)
            assert "INSUFFICIENT_EVIDENCE" in block
    finally:
        async with eng.begin() as conn:
            for org in (org_a, org_b):
                await conn.execute(text("DELETE FROM belief_evidence WHERE organization_id=:o"), {"o": org})
                await conn.execute(text("DELETE FROM beliefs WHERE organization_id=:o"), {"o": org})
                await conn.execute(text("DELETE FROM brain_evidence WHERE organization_id=:o"), {"o": org})
                await conn.execute(text("DELETE FROM brands WHERE organization_id=:o"), {"o": org})
                await conn.execute(text("DELETE FROM organizations WHERE id=:o"), {"o": org})
            await conn.execute(text("DELETE FROM users WHERE id IN (:a,:b)"), {"a": user_a, "b": user_b})
        await eng.dispose()
