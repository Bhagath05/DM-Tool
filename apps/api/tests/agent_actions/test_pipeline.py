"""Phase 4A — approval-gated consequential execution (pure + wiring).

These run WITHOUT Postgres: exact-action fingerprinting, the approval state
machine, the consequential-execution boundary, schema authority limits,
prompt-injection-as-data, result validation, registry isolation, and the
unchanged read-only agent behavior. The full DB lifecycle lives in
test_pipeline_integration.py (PG-gated).
"""

from __future__ import annotations

import uuid

import httpx
import pytest
from pydantic import BaseModel, ValidationError

from aicmo.agent.consequential_tools import get_action_registry
from aicmo.agent.registry import ToolRegistry
from aicmo.agent.tools import get_default_registry
from aicmo.agent.types import (
    ConsequentialExecutionError,
    ExecutionContext,
    Idempotency,
    OperationClass,
    TenantScope,
    ToolDefinition,
    ToolError,
    ToolInput,
)
from aicmo.modules.agent_actions import fingerprint as fp
from aicmo.modules.agent_actions.enums import ALLOWED_TRANSITIONS, ApprovalStatus, can_transition
from aicmo.modules.agent_actions.schemas import ApprovalView, ProposeActionRequest
from aicmo.tenancy.context import TenantContext

_ORIGIN = "https://dm-tool-web.vercel.app"
_ORG = uuid.uuid4()
_BRAND = uuid.uuid4()


def _tenant(*, perms=("content.create",), brand=_BRAND, org=_ORG) -> TenantContext:
    return TenantContext(
        user_id=str(uuid.uuid4()),
        user_uuid=uuid.uuid4(),
        organization_id=org,
        brand_id=brand,
        member_id=uuid.uuid4(),
        role_slugs=frozenset(),
        permissions=frozenset(perms),
    )


class _StubInput(ToolInput):
    target_id: uuid.UUID


class _StubResult(BaseModel):
    id: uuid.UUID
    publish_status: str
    platform_post_id: str | None = None


# --- exact-action fingerprint ----------------------------------------------
def _fp(tool="t", org=_ORG, brand=_BRAND, action_input=None):
    return fp.fingerprint_action(
        organization_id=org, brand_id=brand, tool_name=tool,
        operation_class="consequential", action_input=action_input or {"scheduled_post_id": "abc"},
    )


def test_fingerprint_is_deterministic():
    assert _fp() == _fp()


def test_fingerprint_changes_when_input_changes():
    a = _fp(action_input={"scheduled_post_id": "1"})
    b = _fp(action_input={"scheduled_post_id": "2"})
    assert a != b


def test_fingerprint_changes_when_tenant_or_tool_changes():
    base_input = {"scheduled_post_id": "1"}
    a = _fp(action_input=base_input)
    b = _fp(org=uuid.uuid4(), action_input=base_input)
    c = _fp(tool="other", action_input=base_input)
    assert a != b and a != c


def test_fingerprint_order_independent():
    a = _fp(action_input={"x": 1, "y": 2})
    b = _fp(action_input={"y": 2, "x": 1})
    assert a == b


def test_idempotency_key_derived_from_fingerprint():
    f = "deadbeef" * 8
    assert fp.idempotency_key(f) == fp.idempotency_key(f)
    assert fp.idempotency_key(f) != f  # distinct from the fingerprint itself


# --- state machine ----------------------------------------------------------
def test_state_machine_allows_only_defined_transitions():
    assert can_transition(ApprovalStatus.PENDING, ApprovalStatus.APPROVED)
    assert can_transition(ApprovalStatus.PENDING, ApprovalStatus.REJECTED)
    assert can_transition(ApprovalStatus.PENDING, ApprovalStatus.EXPIRED)
    assert can_transition(ApprovalStatus.APPROVED, ApprovalStatus.EXECUTED)
    assert can_transition(ApprovalStatus.APPROVED, ApprovalStatus.FAILED)


def test_state_machine_forbids_illegal_transitions():
    assert not can_transition(ApprovalStatus.REJECTED, ApprovalStatus.EXECUTED)
    assert not can_transition(ApprovalStatus.EXPIRED, ApprovalStatus.EXECUTED)
    assert not can_transition(ApprovalStatus.EXECUTED, ApprovalStatus.EXECUTED)
    assert not can_transition(ApprovalStatus.FAILED, ApprovalStatus.EXECUTED)
    assert not can_transition(ApprovalStatus.PENDING, ApprovalStatus.EXECUTED)  # must be approved first


def test_terminal_states_have_no_outgoing_transitions():
    for terminal in (ApprovalStatus.REJECTED, ApprovalStatus.EXPIRED, ApprovalStatus.EXECUTED, ApprovalStatus.FAILED):
        assert ALLOWED_TRANSITIONS[terminal] == frozenset()


# --- consequential-execution boundary --------------------------------------
@pytest.mark.asyncio
async def test_public_execute_blocks_consequential():
    registry = get_action_registry()
    ctx = ExecutionContext(session=None, tenant=_tenant())  # type: ignore[arg-type]
    with pytest.raises(ConsequentialExecutionError):
        await registry.execute_tool("publish_scheduled_post", {"scheduled_post_id": str(uuid.uuid4())}, ctx)


@pytest.mark.asyncio
async def test_execute_consequential_rejects_non_consequential_tool():
    registry = ToolRegistry()
    registry.register_tool(
        ToolDefinition(
            name="read_thing", description="d", category="c",
            operation_class=OperationClass.READ, input_schema=_StubInput, output_schema=_StubResult,
            handler=_noop_handler, tenant_scope=TenantScope.BRAND,
        )
    )
    ctx = ExecutionContext(session=None, tenant=_tenant())  # type: ignore[arg-type]
    with pytest.raises(ToolError):
        await registry.execute_consequential("read_thing", {"target_id": str(uuid.uuid4())}, ctx)


@pytest.mark.asyncio
async def test_execute_consequential_enforces_permission():
    registry = _stub_registry()
    # tenant WITHOUT the required permission → fail closed, handler never runs.
    ctx = ExecutionContext(session=None, tenant=_tenant(perms=()))  # type: ignore[arg-type]
    with pytest.raises(ToolError):
        await registry.execute_consequential("stub_publish", {"target_id": str(uuid.uuid4())}, ctx)


@pytest.mark.asyncio
async def test_unknown_tool_cannot_execute():
    registry = get_action_registry()
    ctx = ExecutionContext(session=None, tenant=_tenant())  # type: ignore[arg-type]
    with pytest.raises(ToolError):
        await registry.execute_consequential("no_such_tool", {}, ctx)


# --- schema authority limits (model cannot smuggle authority) --------------
def test_propose_request_forbids_smuggled_authority():
    for smuggled in (
        {"tenant_id": str(uuid.uuid4())},
        {"organization_id": str(uuid.uuid4())},
        {"approved": True},
        {"status": "approved"},
        {"decided_by_user_id": str(uuid.uuid4())},
    ):
        with pytest.raises(ValidationError):
            ProposeActionRequest.model_validate(
                {"tool_name": "publish_scheduled_post", "arguments": {}, **smuggled}
            )


def test_propose_request_arguments_are_opaque_but_bounded():
    # arguments is a free dict (validated later against the TOOL schema), but the
    # top-level body cannot carry approval authority. This is valid:
    req = ProposeActionRequest.model_validate(
        {"tool_name": "t", "arguments": {"scheduled_post_id": "x", "approved": True}}
    )
    # Even an "approved": true INSIDE arguments is just data — it is not an
    # approval; it will be rejected by the tool's extra='forbid' input schema.
    assert req.arguments["approved"] is True


def test_approval_view_exposes_no_session_or_callable():
    fields = set(ApprovalView.model_fields.keys())
    for forbidden in ("session", "handler", "callable", "db", "engine", "connection"):
        assert forbidden not in fields


# --- result validation ------------------------------------------------------
def test_result_summary_requires_published_and_post_id():
    from aicmo.modules.agent_actions.service import _summarize_result

    ok, summary = _summarize_result(_StubResult(id=uuid.uuid4(), publish_status="published", platform_post_id="X"))
    assert ok is True and summary["published"] is True

    # published but NO external id → not success (never fabricate success).
    no_id, s2 = _summarize_result(_StubResult(id=uuid.uuid4(), publish_status="published", platform_post_id=None))
    assert no_id is False and s2["published"] is False

    # not published → not success.
    failed, s3 = _summarize_result(_StubResult(id=uuid.uuid4(), publish_status="failed", platform_post_id=None))
    assert failed is False and s3["published"] is False


# --- registry isolation / read-only agent unchanged ------------------------
def test_default_agent_registry_is_read_only():
    tools = get_default_registry().list_tools()
    assert tools  # non-empty
    assert all(t["operation_class"] == "read" for t in tools)
    assert not any(t["name"] == "publish_scheduled_post" for t in tools)


def test_action_registry_holds_only_the_one_consequential_tool():
    tools = get_action_registry().list_tools()
    assert [t["name"] for t in tools] == ["publish_scheduled_post"]
    assert all(t["operation_class"] == "consequential" for t in tools)
    assert all(t["approval_required"] for t in tools)


def test_consequential_tool_declares_required_metadata():
    meta = get_action_registry().list_tools()[0]
    assert meta["operation_class"] == "consequential"
    assert meta["permission"] == "content.create"
    assert meta["tenant_scope"] == "brand"
    assert meta["approval_required"] is True
    assert meta["idempotency"] == "required"
    assert meta["autonomy_action_type"] == "social_publishing"


# --- wiring + auth boundary (PG-gated for the 401) -------------------------
def test_action_routes_registered():
    from aicmo.main import app

    paths = {getattr(r, "path", None) for r in app.routes}
    assert "/api/v1/agent/actions/propose" in paths
    assert "/api/v1/agent/actions/{approval_id}/approve" in paths
    assert "/api/v1/agent/actions/{approval_id}/execute" in paths


def _closure_strings(route) -> set[str]:
    """Collect every string captured in the closures of a route's dependency
    tree — require_permission bakes its slug in there, so this proves which
    permission gates the endpoint."""
    found: set[str] = set()

    def walk(dep):
        call = getattr(dep, "call", None)
        closure = getattr(call, "__closure__", None) or ()
        for cell in closure:
            try:
                val = cell.cell_contents
            except ValueError:
                continue
            if isinstance(val, str):
                found.add(val)
        for sub in getattr(dep, "dependencies", []) or []:
            walk(sub)

    walk(route.dependant)
    return found


def test_privileged_endpoints_require_settings_manage():
    from aicmo.main import app

    by_path_method = {}
    for r in app.routes:
        methods = getattr(r, "methods", set()) or set()
        path = getattr(r, "path", "")
        if path.startswith("/api/v1/agent/actions") and "POST" in methods:
            by_path_method[path] = r

    # approve / reject / execute require the privileged settings.manage authority.
    for path in (
        "/api/v1/agent/actions/{approval_id}/approve",
        "/api/v1/agent/actions/{approval_id}/reject",
        "/api/v1/agent/actions/{approval_id}/execute",
    ):
        assert "settings.manage" in _closure_strings(by_path_method[path]), path
    # propose requires the publishing permission the action itself needs.
    assert "content.create" in _closure_strings(by_path_method["/api/v1/agent/actions/propose"])


@pytest.mark.asyncio
async def test_action_endpoints_require_auth():
    from tests._dbtest import pg_reachable

    if not pg_reachable():
        pytest.skip("Postgres not reachable")

    async with httpx.AsyncClient(
        transport=httpx.ASGITransport(app=_app()), base_url="https://testserver",
        headers={"origin": _ORIGIN},
    ) as c:
        r = await c.post("/api/v1/agent/actions/propose", json={"tool_name": "publish_scheduled_post", "arguments": {}})
        assert r.status_code == 401
        aid = "00000000-0000-0000-0000-000000000000"
        r = await c.post(f"/api/v1/agent/actions/{aid}/approve", json={})
        assert r.status_code == 401
        r = await c.post(f"/api/v1/agent/actions/{aid}/execute", json={})
        assert r.status_code == 401


# --- helpers ----------------------------------------------------------------
async def _noop_handler(ctx, inp):
    return _StubResult(id=uuid.uuid4(), publish_status="published", platform_post_id="X")


def _stub_registry() -> ToolRegistry:
    registry = ToolRegistry()
    registry.register_tool(
        ToolDefinition(
            name="stub_publish", description="d", category="c",
            operation_class=OperationClass.CONSEQUENTIAL, input_schema=_StubInput,
            output_schema=_StubResult, handler=_noop_handler, permission="content.create",
            tenant_scope=TenantScope.BRAND, approval_required=True, idempotency=Idempotency.REQUIRED,
            autonomy_action_type="social_publishing",
        )
    )
    return registry


def _app():
    from aicmo.main import app

    return app
