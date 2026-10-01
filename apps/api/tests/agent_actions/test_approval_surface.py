"""Phase 4C — the human approval surface (API additions).

Covers what 4C adds on top of the 4A pipeline: the detail view exposes the
validated ``arguments`` (and nothing secret), decision requests cannot carry
approval authority, approve re-validates the exact-action binding (tool +
fingerprint) before transitioning, and the reject endpoint requires auth.

The broad lifecycle / tenant-isolation / idempotency / injection / audit
guarantees are proven by test_pipeline.py and test_pipeline_integration.py (real
Postgres) — not duplicated here.
"""

from __future__ import annotations

import uuid
from types import SimpleNamespace

import httpx
import pytest
from pydantic import BaseModel, ValidationError

from aicmo.agent.registry import ToolRegistry
from aicmo.agent.types import (
    Idempotency,
    OperationClass,
    TenantScope,
    ToolDefinition,
    ToolInput,
)
from aicmo.modules.agent_actions import fingerprint as fp
from aicmo.modules.agent_actions import service
from aicmo.modules.agent_actions.schemas import ApprovalView, DecisionRequest
from aicmo.tenancy.context import TenantContext

_ORIGIN = "https://dm-tool-web.vercel.app"


def _tenant(*, org=None, brand=None, user=None, perms=("content.create", "settings.manage")):
    # user must be a REAL seeded user for DB tests (audit actor FK); defaults to a
    # random uuid for pure/non-DB tests.
    org = org or uuid.uuid4()
    brand = brand or uuid.uuid4()
    user = user or uuid.uuid4()
    return TenantContext(
        user_id=str(user), user_uuid=user, organization_id=org, brand_id=brand,
        member_id=uuid.uuid4(), role_slugs=frozenset(), permissions=frozenset(perms),
    )


class _StubIn(ToolInput):
    scheduled_post_id: uuid.UUID


class _StubOut(BaseModel):
    id: uuid.UUID
    publish_status: str = "published"
    platform_post_id: str | None = "X"


def _stub_registry() -> ToolRegistry:
    async def _h(ctx, inp):
        return _StubOut(id=inp.scheduled_post_id)

    r = ToolRegistry()
    r.register_tool(
        ToolDefinition(
            name="stub_publish", description="d", category="c",
            operation_class=OperationClass.CONSEQUENTIAL, input_schema=_StubIn, output_schema=_StubOut,
            handler=_h, permission="content.create", tenant_scope=TenantScope.BRAND,
            approval_required=True, idempotency=Idempotency.REQUIRED,
            autonomy_action_type="social_publishing",
        )
    )
    return r


# --- decision request cannot carry authority -------------------------------
def test_decision_request_forbids_extra_authority_fields():
    for smuggled in (
        {"approved": True},
        {"status": "approved"},
        {"tenant_id": str(uuid.uuid4())},
        {"decided_by_user_id": str(uuid.uuid4())},
    ):
        with pytest.raises(ValidationError):
            DecisionRequest.model_validate(smuggled)
    # a bounded reason is the ONLY thing a human may attach.
    assert DecisionRequest.model_validate({"reason": "looks good"}).reason == "looks good"


# --- detail view exposes validated arguments, nothing secret ---------------
def test_approval_view_exposes_arguments_and_no_secrets():
    fields = set(ApprovalView.model_fields.keys())
    assert "arguments" in fields
    for forbidden in ("session", "handler", "callable", "db", "engine", "connection", "credentials", "password"):
        assert forbidden not in fields


# --- approve re-validates the exact-action binding (pure) ------------------
def _row(tenant, *, tool="stub_publish", action_input=None, fingerprint=None):
    action_input = action_input if action_input is not None else {"scheduled_post_id": str(uuid.uuid4())}
    good_fp = fp.fingerprint_action(
        organization_id=tenant.organization_id, brand_id=tenant.brand_id,
        tool_name=tool, operation_class="consequential", action_input=action_input,
    )
    return SimpleNamespace(
        tool_name=tool, action_input=action_input, brand_id=tenant.brand_id,
        action_fingerprint=fingerprint or good_fp,
    )


def test_binding_check_passes_for_unchanged_action():
    t = _tenant()
    service._assert_binding_current(t, _row(t), _stub_registry())  # type: ignore[arg-type]


def test_binding_check_fails_when_tool_removed():
    t = _tenant()
    empty = ToolRegistry()
    with pytest.raises(service.ApprovalStateError):
        service._assert_binding_current(t, _row(t), empty)  # type: ignore[arg-type]


def test_binding_check_fails_on_fingerprint_mismatch():
    t = _tenant()
    tampered = _row(t, fingerprint="deadbeef" * 8)  # stored fp doesn't match recompute
    with pytest.raises(service.ApprovalStateError):
        service._assert_binding_current(t, tampered, _stub_registry())  # type: ignore[arg-type]


def test_binding_check_fails_when_input_no_longer_validates():
    t = _tenant()
    bad = _row(t, action_input={"scheduled_post_id": "not-a-uuid"})
    with pytest.raises(service.ApprovalStateError):
        service._assert_binding_current(t, bad, _stub_registry())  # type: ignore[arg-type]


# --- reject requires auth (HTTP, PG-gated) ---------------------------------
@pytest.mark.asyncio
async def test_reject_endpoint_requires_auth():
    from tests._dbtest import pg_reachable

    if not pg_reachable():
        pytest.skip("Postgres not reachable")

    from aicmo.main import app

    async with httpx.AsyncClient(
        transport=httpx.ASGITransport(app=app), base_url="https://testserver",
        headers={"origin": _ORIGIN},
    ) as c:
        aid = "00000000-0000-0000-0000-000000000000"
        r = await c.post(f"/api/v1/agent/actions/{aid}/reject", json={})
        assert r.status_code == 401


# --- approve re-validation end-to-end (PG-gated) ---------------------------
@pytest.mark.asyncio
async def test_approve_rejects_tampered_action_and_shows_arguments():
    from tests._dbtest import pg_reachable

    if not pg_reachable():
        pytest.skip("Postgres not reachable")

    from sqlalchemy import text
    from sqlalchemy.ext.asyncio import AsyncSession, create_async_engine

    from aicmo.modules.agent_actions.enums import ApprovalStatus
    from aicmo.modules.agent_actions.schemas import ProposeActionRequest
    from tests._dbtest import async_dsn

    eng = create_async_engine(async_dsn())
    tag = uuid.uuid4().hex[:8]
    org, brand, user = uuid.uuid4(), uuid.uuid4(), uuid.uuid4()
    t = _tenant(org=org, brand=brand, user=user)
    reg = _stub_registry()
    post_id = uuid.uuid4()
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
            await s.commit()

        async with AsyncSession(eng, expire_on_commit=False) as s:
            row = await service.propose_action(
                s, tenant=t,
                request=ProposeActionRequest(tool_name="stub_publish", arguments={"scheduled_post_id": str(post_id)}),
                registry=reg,
            )
            await s.commit()
            aid = row.id

        # detail view exposes the validated arguments.
        async with AsyncSession(eng, expire_on_commit=False) as s:
            got = await service.get_approval(s, tenant=t, approval_id=aid)
            assert service._view(got).arguments == {"scheduled_post_id": str(post_id)}

        # tamper the stored input, then approve → fails closed, stays PENDING.
        async with AsyncSession(eng, expire_on_commit=False) as s:
            victim = await service.get_approval(s, tenant=t, approval_id=aid)
            victim.action_input = {"scheduled_post_id": str(uuid.uuid4())}
            await s.flush()
            with pytest.raises(service.ApprovalStateError):
                await service.approve(s, tenant=t, approval_id=aid, registry=reg)
            await s.rollback()

        async with AsyncSession(eng, expire_on_commit=False) as s:
            still = await service.get_approval(s, tenant=t, approval_id=aid)
            assert still.status == ApprovalStatus.PENDING.value  # never approved

        # a clean approve (untampered) succeeds.
        async with AsyncSession(eng, expire_on_commit=False) as s:
            ok = await service.approve(s, tenant=t, approval_id=aid, registry=reg)
            await s.commit()
            assert ok.status == ApprovalStatus.APPROVED.value
            assert ok.decided_by_user_id == user
    finally:
        async with eng.begin() as conn:
            await conn.execute(text("DELETE FROM agent_action_approvals WHERE organization_id=:o"), {"o": org})
            await conn.execute(text("DELETE FROM audit_events WHERE organization_id=:o"), {"o": org})
            await conn.execute(text("DELETE FROM brands WHERE organization_id=:o"), {"o": org})
            await conn.execute(text("DELETE FROM organizations WHERE id=:o"), {"o": org})
            await conn.execute(text("DELETE FROM users WHERE id=:u"), {"u": user})
        await eng.dispose()
