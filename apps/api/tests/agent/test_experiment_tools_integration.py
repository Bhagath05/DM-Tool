"""Phase 7.4 — real-Postgres tests for the BRO experiment READ tools.

Exercises the two new tools THROUGH the registry (so authorization, tenant-scope,
and schema validation all run), proving:

  * get_experiment_results returns an experiment's measured snapshots, and is
    honest (found=False) for an id that is not this brand's (isolation);
  * evaluate_experiment_evidence returns SUPPORTED for a clean, comparable,
    adequately-powered win, and INSUFFICIENT_EVIDENCE when volume is too low —
    never a fabricated significance;
  * both tools fail closed without the required RBAC permission;
  * the consequential boundary is intact — the conversational registry exposes
    no CONSEQUENTIAL tool, and publishing remains CONSEQUENTIAL + approval-gated.

Skips cleanly when no project Postgres is reachable (tests/_dbtest).
"""

from __future__ import annotations

import uuid

import pytest


def _ctx(*, org, brand, user, perms):
    from aicmo.tenancy.context import TenantContext

    return TenantContext(
        user_id=str(user), user_uuid=user, organization_id=org, brand_id=brand,
        member_id=uuid.uuid4(), role_slugs=frozenset({"owner"}), permissions=frozenset(perms),
    )


async def _seed_experiment(s, *, org, brand, user, goal, asset_type, platform, choices):
    from aicmo.modules.learning.models import CampaignExperiment

    exp = CampaignExperiment(
        id=uuid.uuid4(), organization_id=org, brand_id=brand, user_id=str(user),
        source_asset_type=asset_type, source_asset_id=uuid.uuid4(), platform=platform,
        goal=goal, hypothesis="h", status="pending", variable_choices=choices,
    )
    s.add(exp)
    await s.flush()
    return exp.id


@pytest.mark.asyncio
async def test_experiment_tools_end_to_end():
    from tests._dbtest import pg_reachable

    if not pg_reachable():
        pytest.skip("Postgres not reachable")

    from sqlalchemy import text
    from sqlalchemy.ext.asyncio import AsyncSession, create_async_engine

    import aicmo.main  # noqa: F401
    from aicmo.agent.consequential_tools import get_action_registry
    from aicmo.agent.tools import get_default_registry
    from aicmo.agent.types import (
        ExecutionContext,
        OperationClass,
        ToolPermissionError,
    )
    from aicmo.modules.learning import service as learning_service
    from aicmo.modules.learning.experiment_contract import EvidenceVerdict
    from aicmo.modules.learning.schemas import RecordResultInput
    from tests._dbtest import async_dsn

    eng = create_async_engine(async_dsn())
    tag = uuid.uuid4().hex[:8]
    org, brand, user = uuid.uuid4(), uuid.uuid4(), uuid.uuid4()
    registry = get_default_registry()
    full = _ctx(org=org, brand=brand, user=user, perms={"analytics.view", "library.view"})
    try:
        async with eng.begin() as conn:
            await conn.execute(text("INSERT INTO users (id, clerk_user_id, email) VALUES (:i,:c,:e)"),
                               {"i": user, "c": f"c{tag}", "e": f"{tag}@t.local"})
            await conn.execute(text("INSERT INTO organizations (id, slug, name, owner_user_id) VALUES (:i,:s,:n,:o)"),
                               {"i": org, "s": f"o{tag}", "n": "O", "o": user})
            await conn.execute(
                text("INSERT INTO brands (id, organization_id, slug, name, created_by_user_id) VALUES (:i,:o,:s,:n,:u)"),
                {"i": brand, "o": org, "s": f"b{tag}", "n": "B", "u": user},
            )

        # Two comparable arms, adequate volume, a clear leads win for A.
        async with AsyncSession(eng, expire_on_commit=False) as s:
            exp_a = await _seed_experiment(s, org=org, brand=brand, user=user, goal="leads",
                                           asset_type="content", platform="instagram", choices={"format": "reel"})
            exp_b = await _seed_experiment(s, org=org, brand=brand, user=user, goal="leads",
                                           asset_type="content", platform="instagram", choices={"format": "carousel"})
            await learning_service.record_result(s, payload=RecordResultInput(experiment_id=exp_a, impressions=600, leads=30))
            await learning_service.record_result(s, payload=RecordResultInput(experiment_id=exp_b, impressions=600, leads=20))
            # A low-volume experiment for the insufficient path.
            exp_low = await _seed_experiment(s, org=org, brand=brand, user=user, goal="leads",
                                             asset_type="content", platform="instagram", choices={"format": "story"})
            await learning_service.record_result(s, payload=RecordResultInput(experiment_id=exp_low, impressions=10, leads=1))
            await s.commit()

        async with AsyncSession(eng, expire_on_commit=False) as s:
            ctx_exec = ExecutionContext(session=s, tenant=full)

            # 1. get_experiment_results — found + has a measured snapshot.
            r = await registry.execute_tool("get_experiment_results", {"experiment_id": str(exp_a)}, ctx_exec)
            assert r.data.found is True
            assert len(r.data.results) == 1
            assert r.data.results[0].leads == 30

            # 2. brand isolation — a random id is "not found", never leaked.
            r = await registry.execute_tool("get_experiment_results", {"experiment_id": str(uuid.uuid4())}, ctx_exec)
            assert r.data.found is False and r.data.experiment is None

            # 3. evidence — clean comparable win → SUPPORTED, no fabricated %.
            r = await registry.execute_tool(
                "evaluate_experiment_evidence",
                {"experiment_id": str(exp_a), "baseline_experiment_id": str(exp_b), "primary_metric": "leads"},
                ctx_exec,
            )
            assert r.data.verdict == EvidenceVerdict.SUPPORTED
            assert r.data.effect is not None and r.data.effect > 0
            assert 0.0 <= r.data.data_strength <= 0.85

            # 4. evidence — low volume → INSUFFICIENT_EVIDENCE.
            r = await registry.execute_tool(
                "evaluate_experiment_evidence",
                {"experiment_id": str(exp_low), "primary_metric": "leads"},
                ctx_exec,
            )
            assert r.data.verdict == EvidenceVerdict.INSUFFICIENT_EVIDENCE

        # 5. permission failure — no analytics.view/library.view → fail closed.
        async with AsyncSession(eng, expire_on_commit=False) as s:
            weak = ExecutionContext(session=s, tenant=_ctx(org=org, brand=brand, user=user, perms=set()))
            with pytest.raises(ToolPermissionError):
                await registry.execute_tool("get_experiment_results", {"experiment_id": str(exp_a)}, weak)
            with pytest.raises(ToolPermissionError):
                await registry.execute_tool("evaluate_experiment_evidence", {"experiment_id": str(exp_a)}, weak)

        # 6. consequential boundary intact (unchanged by this phase).
        assert registry.list_tools(operation_class=OperationClass.CONSEQUENTIAL) == []
        publish = get_action_registry().get_tool("publish_scheduled_post")
        assert publish is not None
        assert publish.operation_class == OperationClass.CONSEQUENTIAL
        assert publish.approval_required is True
        assert registry.get_tool("publish_scheduled_post") is None  # never on the conversational surface
    finally:
        async with eng.begin() as conn:
            await conn.execute(text("DELETE FROM experiment_results WHERE experiment_id IN "
                                    "(SELECT id FROM campaign_experiments WHERE brand_id=:b)"), {"b": brand})
            await conn.execute(text("DELETE FROM campaign_experiments WHERE brand_id=:b"), {"b": brand})
            await conn.execute(text("DELETE FROM brands WHERE organization_id=:o"), {"o": org})
            await conn.execute(text("DELETE FROM organizations WHERE id=:o"), {"o": org})
            await conn.execute(text("DELETE FROM users WHERE id=:u"), {"u": user})
        await eng.dispose()
