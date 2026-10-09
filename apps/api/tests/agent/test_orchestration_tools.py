"""Phase 7.1 — orchestration READ tools (get_marketing_strategy, get_experiments).

Unit-level: dispatch, typed-argument validation, fail-closed permission, honest
missing-data, and safe field mapping (verbose internal snapshots are NOT fed to
the model). Database-backed brand isolation is pinned separately in
test_orchestration_tools_integration.py.
"""

from __future__ import annotations

import uuid
from datetime import UTC, datetime
from types import SimpleNamespace
from unittest.mock import AsyncMock, patch

import pytest

from aicmo.agent.tools import get_default_registry
from aicmo.agent.types import (
    ExecutionContext,
    ToolInputError,
    ToolPermissionError,
)
from aicmo.modules.agent.schemas import AgentPlan, ProposedToolCall


# --- plan robustness: malformed tool-call arguments (non-strict LLM output) --
def test_plan_coerces_non_dict_arguments_so_one_bad_call_cannot_fail_the_turn():
    # The model sometimes emits arguments as a list for a parameterized tool.
    plan = AgentPlan.model_validate(
        {
            "intent": "x",
            "answer_strategy": "y",
            "tool_calls": [
                {"tool_name": "get_experiments", "arguments": ["limit"], "purpose": "p"}
            ],
            "confidence": 80,
            "needs_more_evidence": False,
        }
    )
    assert plan.tool_calls[0].arguments == {}  # coerced; tool will use its defaults


def test_plan_preserves_valid_and_extra_key_dict_arguments():
    # A valid dict is untouched; a dict with an extra key is PRESERVED so the
    # tool's own input schema (extra="forbid") still rejects it downstream.
    assert ProposedToolCall.model_validate(
        {"tool_name": "t", "arguments": {"limit": 5}}
    ).arguments == {"limit": 5}
    assert ProposedToolCall.model_validate(
        {"tool_name": "t", "arguments": {"brand_id": "x"}}
    ).arguments == {"brand_id": "x"}


class _FakeTenant:
    def __init__(self, *, brand_id, permissions=()):
        self.organization_id = uuid.uuid4()
        self.brand_id = brand_id
        self.user_uuid = uuid.uuid4()
        self.user_id = str(self.user_uuid)
        self.role_slugs = frozenset()
        self.permissions = frozenset(permissions)

    def has_permission(self, slug: str) -> bool:
        return slug in self.permissions


def _ctx(*, permissions=()):
    return ExecutionContext(
        session=AsyncMock(),
        tenant=_FakeTenant(brand_id=uuid.uuid4(), permissions=permissions),
    )


# --- fail-closed permission -------------------------------------------------
@pytest.mark.asyncio
async def test_strategy_tool_requires_analytics_view_fail_closed():
    reg = get_default_registry()
    with pytest.raises(ToolPermissionError):
        await reg.execute_tool("get_marketing_strategy", {}, _ctx(permissions=()))


@pytest.mark.asyncio
async def test_experiments_tool_requires_library_view_fail_closed():
    reg = get_default_registry()
    with pytest.raises(ToolPermissionError):
        await reg.execute_tool("get_experiments", {}, _ctx(permissions=()))


# --- typed argument validation (no model-controlled tenant, bounded args) ---
@pytest.mark.asyncio
async def test_experiments_rejects_smuggled_tenant_arg():
    reg = get_default_registry()
    with pytest.raises(ToolInputError):
        await reg.execute_tool(
            "get_experiments",
            {"limit": 5, "brand_id": str(uuid.uuid4())},  # extra="forbid"
            _ctx(permissions=("library.view",)),
        )


@pytest.mark.asyncio
async def test_experiments_rejects_out_of_range_limit():
    reg = get_default_registry()
    with pytest.raises(ToolInputError):
        await reg.execute_tool(
            "get_experiments", {"limit": 999}, _ctx(permissions=("library.view",))
        )


# --- honest missing-data ----------------------------------------------------
@pytest.mark.asyncio
async def test_strategy_tool_missing_is_present_false_not_fabricated():
    reg = get_default_registry()
    with patch("aicmo.modules.strategist.service.latest", new=AsyncMock(return_value=None)):
        res = await reg.execute_tool(
            "get_marketing_strategy", {}, _ctx(permissions=("analytics.view",))
        )
    assert res.data.present is False
    assert res.data.positioning is None


# --- dispatch + safe field mapping ------------------------------------------
@pytest.mark.asyncio
async def test_strategy_tool_maps_fields_from_record():
    rec = SimpleNamespace(
        status="completed",
        created_at=datetime.now(UTC),
        strategy={
            "positioning": "Small-batch bakery",
            "target_summary": "nearby locals",
            "recommendation": "Publish a lead page",
            "reason": "no page exists",
            "expected_result": "1-3 leads",
            "campaign_roadmap": ["launch page", "promote it", "email follow-up"],
        },
    )
    reg = get_default_registry()
    with patch("aicmo.modules.strategist.service.latest", new=AsyncMock(return_value=rec)):
        res = await reg.execute_tool(
            "get_marketing_strategy", {}, _ctx(permissions=("analytics.view",))
        )
    out = res.data
    assert out.present is True and out.positioning == "Small-batch bakery"
    assert out.recommendation == "Publish a lead page"
    assert out.campaign_roadmap[:1] == ["launch page"]


@pytest.mark.asyncio
async def test_experiments_tool_excludes_verbose_internal_snapshots():
    row = SimpleNamespace(
        id=uuid.uuid4(),
        hypothesis="Reels beat static",
        goal="leads",
        platform="instagram",
        status="running",
        sample_size=120,
        confidence_score=0.62,
        created_at=datetime.now(UTC),
        # Verbose internal fields that must NOT reach the model:
        context_snapshot={"secret": "internal"},
        variable_choices={"x": 1},
    )
    reg = get_default_registry()
    with patch(
        "aicmo.modules.learning.service.list_experiments",
        new=AsyncMock(return_value=[row]),
    ):
        res = await reg.execute_tool(
            "get_experiments", {"limit": 5}, _ctx(permissions=("library.view",))
        )
    assert len(res.data.items) == 1
    item = res.data.items[0]
    assert item.hypothesis == "Reels beat static" and item.sample_size == 120
    # The agent view has no field for the internal snapshots.
    assert not hasattr(item, "context_snapshot")
    assert "secret" not in res.data.model_dump_json()
