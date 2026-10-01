"""Phase 3D — cross-belief contradiction / supersession.

Pure tests pin the safety-critical comparability + stance rules (different
scopes must never contradict). PG-gated tests exercise the full reconcile pass
and the resolver's validity-window handling.
"""

from __future__ import annotations

import uuid

import pytest

from aicmo.modules.belief import reconcile
from aicmo.modules.belief.enums import BeliefStatus


# --- comparability (pure) ---------------------------------------------------
def test_same_channel_is_comparable():
    assert reconcile.scopes_comparable({"channel": "instagram"}, {"channel": "Instagram"}) is True


def test_different_channel_is_not_comparable():
    assert reconcile.scopes_comparable({"channel": "instagram"}, {"channel": "email"}) is False


def test_no_shared_distinguishing_key_is_not_comparable():
    # One is about a channel, the other about an audience — cannot be shown to be
    # the same slice, so they can never contradict.
    assert reconcile.scopes_comparable({"channel": "instagram"}, {"audience": "b2c"}) is False


def test_agree_on_shared_disagree_on_other_is_not_comparable():
    a = {"channel": "instagram", "audience": "b2c"}
    b = {"channel": "instagram", "audience": "b2b"}
    assert reconcile.scopes_comparable(a, b) is False


def test_agree_on_all_shared_is_comparable():
    a = {"channel": "instagram", "audience": "b2c", "metric": "lead_volume"}
    b = {"channel": "instagram", "audience": "b2c"}
    assert reconcile.scopes_comparable(a, b) is True


def test_non_dict_scope_is_not_comparable():
    assert reconcile.scopes_comparable(None, {"channel": "x"}) is False  # type: ignore[arg-type]


# --- stance (pure) ----------------------------------------------------------
def test_active_default_stance_points_up():
    s = reconcile.derive_stance(scope={"metric": "lead_volume"}, status="active", category="channel")
    assert s is not None and s.direction == "up" and s.metric == "lead_volume"


def test_effect_decrease_points_down():
    s = reconcile.derive_stance(
        scope={"metric": "lead_volume", "effect": "decrease"}, status="active", category="channel"
    )
    assert s is not None and s.direction == "down"


def test_metric_defaults_by_category():
    s = reconcile.derive_stance(scope={}, status="active", category="performance")
    assert s is not None and s.metric == "lead_volume"


def test_non_active_belief_has_no_stance():
    for status in (
        BeliefStatus.UNVALIDATED.value,
        BeliefStatus.CONTRADICTED.value,
        BeliefStatus.SUPERSEDED.value,
        BeliefStatus.RETIRED.value,
    ):
        assert reconcile.derive_stance(scope={}, status=status, category="channel") is None


# --- PG-gated integration ---------------------------------------------------
class _T:
    def __init__(self, *, org, brand, user):
        self.organization_id = org
        self.brand_id = brand
        self.user_uuid = user
        self.user_id = str(user)
        self.member_id = uuid.uuid4()
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
        {"i": org, "s": f"org-{tag}", "n": "Reconcile Org", "o": user},
    )
    await session.execute(
        text(
            "INSERT INTO brands (id, organization_id, slug, name, created_by_user_id) "
            "VALUES (:i,:o,:s,:n,:u)"
        ),
        {"i": brand, "o": org, "s": f"brand-{tag}", "n": "Reconcile Brand", "u": user},
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


async def _active_belief(session, *, tenant, subject, scope, ev_id):
    from aicmo.modules.belief import service
    from aicmo.modules.belief.enums import BeliefCategory, EvidenceRefKind
    from aicmo.modules.belief.schemas import BeliefCreate, EvidenceRefInput

    return await service.create_belief(
        session,
        tenant=tenant,
        data=BeliefCreate(
            category=BeliefCategory.CHANNEL,
            subject_key=subject,
            statement="Server-templated claim for reconcile test.",
            scope=scope,
            evidence=[EvidenceRefInput(ref_kind=EvidenceRefKind.BRAIN_EVIDENCE, ref_id=ev_id)],
        ),
    )


@pytest.mark.asyncio
async def test_reconcile_and_expiry_integration():
    from tests._dbtest import pg_reachable

    if not pg_reachable():
        pytest.skip("Postgres not reachable")

    from datetime import UTC, datetime, timedelta

    from sqlalchemy import text
    from sqlalchemy.ext.asyncio import AsyncSession

    from aicmo.modules.belief import resolver, service

    eng = _engine()
    tag = uuid.uuid4().hex[:8]
    org, brand, user = uuid.uuid4(), uuid.uuid4(), uuid.uuid4()
    t = _T(org=org, brand=brand, user=user)
    try:
        async with AsyncSession(eng, expire_on_commit=False) as s:
            await _seed_tenant(s, org=org, brand=brand, user=user, tag=tag)
            ev = await _seed_evidence(s, org=org, brand=brand, claim="evidence")
            await s.commit()

        # 1. Two comparable beliefs, OPPOSITE effect → reconcile supersedes one.
        async with AsyncSession(eng, expire_on_commit=False) as s:
            up = await _active_belief(
                s, tenant=t, subject="ig_up",
                scope={"channel": "instagram", "metric": "lead_volume", "effect": "increase"}, ev_id=ev,
            )
            down = await _active_belief(
                s, tenant=t, subject="ig_down",
                scope={"channel": "instagram", "metric": "lead_volume", "effect": "decrease"}, ev_id=ev,
            )
            await s.commit()
            up_id, down_id = up.id, down.id

        async with AsyncSession(eng, expire_on_commit=False) as s:
            result = await reconcile.reconcile_belief(s, tenant=t, belief_id=up_id)
            await s.commit()
            assert result.status == "reconciled"
            assert len(result.superseded_ids) == 1

        async with AsyncSession(eng, expire_on_commit=False) as s:
            res = await resolver.resolve_beliefs(s, tenant=t, include_history=True)
            active_ids = {b.id for b in res.active}
            # exactly one of the pair survives as active; the other is history.
            assert len({up_id, down_id} & active_ids) == 1
            hist_ids = {b.id for b in res.superseded}
            loser = (result.superseded_ids or [None])[0]
            assert loser in hist_ids
            # history is preserved, not deleted: the loser still carries its scope.
            old = await service.get_belief(s, tenant=t, belief_id=loser)
            assert old.status == "superseded" and old.superseded_by_id == result.winner_id
            assert old.scope  # scope retained

        # 2. Different scope, opposite effect → NO conflict.
        async with AsyncSession(eng, expire_on_commit=False) as s:
            a = await _active_belief(
                s, tenant=t, subject="li_up",
                scope={"channel": "linkedin", "metric": "lead_volume", "effect": "increase"}, ev_id=ev,
            )
            await _active_belief(
                s, tenant=t, subject="em_down",
                scope={"channel": "email", "metric": "lead_volume", "effect": "decrease"}, ev_id=ev,
            )
            await s.commit()
            r = await reconcile.reconcile_belief(s, tenant=t, belief_id=a.id)
            assert r.status == "no_conflict"
            await s.rollback()

        # 3. Validity window: an active belief past valid_until is not "current"
        #    but is retrievable as history.
        async with AsyncSession(eng, expire_on_commit=False) as s:
            expired = await _active_belief(
                s, tenant=t, subject="expired_one",
                scope={"channel": "pinterest", "metric": "lead_volume"}, ev_id=ev,
            )
            expired.valid_until = datetime.now(UTC) - timedelta(days=1)
            await s.flush()
            await s.commit()
            expired_id = expired.id

        async with AsyncSession(eng, expire_on_commit=False) as s:
            res = await resolver.resolve_beliefs(s, tenant=t, include_history=True)
            assert expired_id not in {b.id for b in res.active}
            assert expired_id in {b.id for b in res.superseded}
    finally:
        async with eng.begin() as conn:
            await conn.execute(text("DELETE FROM belief_evidence WHERE organization_id=:o"), {"o": org})
            await conn.execute(text("DELETE FROM beliefs WHERE organization_id=:o"), {"o": org})
            await conn.execute(text("DELETE FROM brain_evidence WHERE organization_id=:o"), {"o": org})
            await conn.execute(text("DELETE FROM brands WHERE organization_id=:o"), {"o": org})
            await conn.execute(text("DELETE FROM organizations WHERE id=:o"), {"o": org})
            await conn.execute(text("DELETE FROM users WHERE id=:u"), {"u": user})
        await eng.dispose()
