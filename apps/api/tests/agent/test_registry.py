"""Phase 1 — Tool Registry regression + security tests.

Covers registration/discovery/validation, fail-closed authorization, tenant
isolation (no model-controlled tenant), the consequential-execution boundary,
metadata safety, and provenance. Underlying services are mocked — the registry
is the unit under test.
"""

from __future__ import annotations

import uuid
from unittest.mock import AsyncMock, patch

import pytest
from pydantic import BaseModel

from aicmo.agent.registry import ToolRegistry
from aicmo.agent.tools import get_default_registry
from aicmo.agent.types import (
    ConsequentialExecutionError,
    DuplicateToolError,
    ExecutionContext,
    Idempotency,
    OperationClass,
    TenantScope,
    ToolDefinition,
    ToolInput,
    ToolInputError,
    ToolNotFoundError,
    ToolOutputError,
    ToolPermissionError,
    ToolResult,
    ToolTenantError,
)


class _FakeTenant:
    """Duck-typed TenantContext: the registry only uses brand_id,
    organization_id, and has_permission."""

    def __init__(self, *, brand_id, org_id=None, permissions=()):
        self.organization_id = org_id or uuid.uuid4()
        self.brand_id = brand_id
        self.user_uuid = uuid.uuid4()
        self.user_id = str(self.user_uuid)
        self.role_slugs = frozenset()
        self.permissions = frozenset(permissions)

    def has_permission(self, slug: str) -> bool:
        return slug in self.permissions


def _ctx(*, brand_id=None, permissions=()):
    if brand_id is None:
        brand_id = uuid.uuid4()
    return ExecutionContext(session=AsyncMock(), tenant=_FakeTenant(brand_id=brand_id, permissions=permissions))


# --- synthetic tools for contract-level tests -------------------------------
class _Out(BaseModel):
    ok: bool = True


class _EchoIn(ToolInput):
    n: int = 1


async def _read_handler(ctx, inp):
    return _Out(ok=True)


async def _write_handler(ctx, inp):
    return _Out(ok=True)


async def _consequential_handler(ctx, inp):  # must never be called
    raise AssertionError("consequential handler must not execute")


async def _bad_output_handler(ctx, inp):
    return "not a model at all"  # wrong type → output validation must fail


def _def(name, cls, handler, *, permission=None, scope=TenantScope.BRAND, approval=False):
    return ToolDefinition(
        name=name,
        description=f"{name} tool",
        category="test",
        operation_class=cls,
        input_schema=_EchoIn,
        output_schema=_Out,
        handler=handler,
        permission=permission,
        tenant_scope=scope,
        approval_required=approval,
        idempotency=Idempotency.REQUIRED if cls != OperationClass.READ else Idempotency.NOT_REQUIRED,
    )


# --- registration + discovery ----------------------------------------------
def test_register_and_get_tool():
    reg = ToolRegistry()
    reg.register_tool(_def("t_read", OperationClass.READ, _read_handler))
    assert reg.get_tool("t_read") is not None
    assert reg.resolve_tool("t_read").name == "t_read"


def test_duplicate_registration_rejected():
    reg = ToolRegistry()
    reg.register_tool(_def("dup", OperationClass.READ, _read_handler))
    with pytest.raises(DuplicateToolError):
        reg.register_tool(_def("dup", OperationClass.READ, _read_handler))


def test_unknown_tool_rejected():
    reg = ToolRegistry()
    with pytest.raises(ToolNotFoundError):
        reg.resolve_tool("does_not_exist")
    # A python builtin name must NOT resolve — allowlist only.
    with pytest.raises(ToolNotFoundError):
        reg.resolve_tool("eval")


def test_list_tools_metadata_is_safe():
    reg = get_default_registry()
    tools = reg.list_tools()
    assert len(tools) == 12
    keys = set(tools[0])
    assert "handler" not in keys and "output_schema" in keys and "input_schema" in keys
    import json

    blob = json.dumps(tools)
    for leak in ("aicmo.", "_get_", "handler", "object at 0x"):
        assert leak not in blob
    # discovery can filter by class
    assert reg.list_tools(operation_class=OperationClass.CONSEQUENTIAL) == []


# --- input / output validation ---------------------------------------------
@pytest.mark.asyncio
async def test_input_rejects_smuggled_fields():
    reg = ToolRegistry()
    reg.register_tool(_def("t", OperationClass.READ, _read_handler))
    # A model trying to smuggle a tenant id → rejected (extra="forbid").
    with pytest.raises(ToolInputError):
        await reg.execute_tool("t", {"n": 1, "brand_id": str(uuid.uuid4())}, _ctx())


@pytest.mark.asyncio
async def test_output_validation_rejects_wrong_type():
    reg = ToolRegistry()
    reg.register_tool(_def("t", OperationClass.READ, _bad_output_handler))
    with pytest.raises(ToolOutputError):
        await reg.execute_tool("t", {}, _ctx())


# --- authorization: fail closed --------------------------------------------
@pytest.mark.asyncio
async def test_permission_enforced_fail_closed():
    reg = ToolRegistry()
    reg.register_tool(_def("t", OperationClass.READ, _read_handler, permission="analytics.view"))
    # missing permission → blocked
    with pytest.raises(ToolPermissionError):
        await reg.execute_tool("t", {}, _ctx(permissions=()))
    # with permission → runs
    res = await reg.execute_tool("t", {}, _ctx(permissions=("analytics.view",)))
    assert isinstance(res, ToolResult) and res.data.ok is True


@pytest.mark.asyncio
async def test_tenant_scope_requires_brand():
    reg = ToolRegistry()
    reg.register_tool(_def("t", OperationClass.READ, _read_handler))
    with pytest.raises(ToolTenantError):
        await reg.execute_tool("t", {}, _ctx(brand_id=None) if False else ExecutionContext(
            session=AsyncMock(), tenant=_FakeTenant(brand_id=None)
        ))


# --- consequential boundary: never auto-executes ---------------------------
@pytest.mark.asyncio
async def test_consequential_tool_is_blocked_not_executed():
    reg = ToolRegistry()
    reg.register_tool(_def("danger", OperationClass.CONSEQUENTIAL, _consequential_handler, approval=True))
    with pytest.raises(ConsequentialExecutionError):
        await reg.execute_tool("danger", {}, _ctx(permissions=("analytics.view",)))
    # metadata still discoverable + correctly classed
    meta = reg.get_tool("danger").metadata()
    assert meta["operation_class"] == "consequential"
    assert meta["approval_required"] is True
    assert meta["idempotency"] == "required"


@pytest.mark.asyncio
async def test_write_tool_executes_with_metadata():
    reg = ToolRegistry()
    reg.register_tool(_def("make_draft", OperationClass.WRITE, _write_handler))
    res = await reg.execute_tool("make_draft", {}, _ctx())
    assert res.operation_class == OperationClass.WRITE and res.data.ok is True
    assert reg.get_tool("make_draft").metadata()["operation_class"] == "write"


# --- built-in READ execution + tenant derivation ----------------------------
@pytest.mark.asyncio
async def test_builtin_read_execution_uses_context_tenant():
    reg = get_default_registry()
    ctx = _ctx(permissions=("analytics.view",))
    # get_business_profile → onboarding.get_profile_or_none (patched to None).
    with patch(
        "aicmo.modules.onboarding.service.get_profile_or_none", new=AsyncMock(return_value=None)
    ) as p:
        res = await reg.execute_tool("get_business_profile", {}, ctx)
    assert res.tool == "get_business_profile"
    assert res.data.present is False  # safe typed snapshot, no ORM object
    # The service was called with the CONTEXT brand — never a model-supplied one.
    _, kwargs = p.call_args
    called_brand = p.call_args.args[1] if len(p.call_args.args) > 1 else kwargs.get("brand_id")
    assert called_brand == ctx.tenant.brand_id


@pytest.mark.asyncio
async def test_builtin_recommendations_derives_brand_from_context_not_input():
    reg = get_default_registry()
    ctx = _ctx(permissions=("analytics.view",))
    with patch("aicmo.agent.tools.load_brand_memory", new=AsyncMock(return_value=[])) as p:
        # Attempt to smuggle a foreign brand_id → rejected by input schema.
        with pytest.raises(ToolInputError):
            await reg.execute_tool("get_recommendations", {"days": 30, "brand_id": str(uuid.uuid4())}, ctx)
        # Valid input → brand comes from the context.
        res = await reg.execute_tool("get_recommendations", {"days": 30}, ctx)
    assert res.data.items == []
    assert p.call_args.kwargs["brand_id"] == ctx.tenant.brand_id
    assert p.call_args.kwargs["days"] == 30


# --- provenance mirrors the declaration (never fabricated) ------------------
@pytest.mark.asyncio
async def test_provenance_flag_reflects_definition():
    reg = get_default_registry()
    ctx = _ctx(permissions=("analytics.view",))
    with patch(
        "aicmo.modules.onboarding.service.get_profile_or_none", new=AsyncMock(return_value=None)
    ):
        res = await reg.execute_tool("get_business_profile", {}, ctx)
    # Owner-declared profile → provenance False (honest; not evidence-sourced).
    assert res.provenance is False
    # An evidence tool declares provenance True in its metadata.
    assert reg.get_tool("get_icp_evidence").metadata()["provenance"] is True
