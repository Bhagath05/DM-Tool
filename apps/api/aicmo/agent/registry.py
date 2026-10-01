"""The Tool Registry — the controlled boundary through which a future agent
discovers and invokes existing DM Tool capabilities.

The registry is an ORCHESTRATION boundary, not a business-logic layer. Every
handler calls an EXISTING domain service; the registry adds only: allowlisted
name resolution, input/output schema validation, tenant-scope + permission
enforcement (fail closed), and the consequential-execution boundary.

It NEVER: performs a dynamic import, executes an arbitrary callable chosen by a
model-controlled string, trusts tenant/authorization data from tool input, or
auto-executes a CONSEQUENTIAL tool.
"""

from __future__ import annotations

import structlog
from pydantic import BaseModel, ValidationError

from aicmo.agent.types import (
    ConsequentialExecutionError,
    DuplicateToolError,
    ExecutionContext,
    OperationClass,
    TenantScope,
    ToolDefinition,
    ToolError,
    ToolInputError,
    ToolNotFoundError,
    ToolOutputError,
    ToolPermissionError,
    ToolResult,
    ToolTenantError,
)

log = structlog.get_logger()


class ToolRegistry:
    """An in-memory, allowlisted registry of declarative tools."""

    def __init__(self) -> None:
        self._tools: dict[str, ToolDefinition] = {}

    # --- registration ------------------------------------------------------
    def register_tool(self, definition: ToolDefinition) -> None:
        if definition.name in self._tools:
            raise DuplicateToolError(f"tool already registered: {definition.name!r}")
        if not callable(definition.handler):
            raise ToolError(f"tool {definition.name!r} has no callable handler")
        if not (
            isinstance(definition.input_schema, type)
            and issubclass(definition.input_schema, BaseModel)
        ):
            raise ToolError(f"tool {definition.name!r} input_schema must be a Pydantic model")
        if not (
            isinstance(definition.output_schema, type)
            and issubclass(definition.output_schema, BaseModel)
        ):
            raise ToolError(f"tool {definition.name!r} output_schema must be a Pydantic model")
        self._tools[definition.name] = definition

    # --- discovery ---------------------------------------------------------
    def get_tool(self, name: str) -> ToolDefinition | None:
        return self._tools.get(name)

    def resolve_tool(self, name: str) -> ToolDefinition:
        """Resolve a tool by name against the allowlist ONLY. No dynamic import,
        no attribute lookup on arbitrary modules."""
        tool = self._tools.get(name)
        if tool is None:
            raise ToolNotFoundError(f"unknown tool: {name!r}")
        return tool

    def list_tools(self, *, operation_class: OperationClass | None = None) -> list[dict]:
        """Safe declarative metadata for every tool (optionally filtered by
        class). Never exposes handlers or module paths."""
        tools = sorted(self._tools.values(), key=lambda t: t.name)
        return [
            t.metadata()
            for t in tools
            if operation_class is None or t.operation_class == operation_class
        ]

    # --- validation --------------------------------------------------------
    def validate_input(self, tool: ToolDefinition, raw_input: dict | None) -> BaseModel:
        try:
            return tool.input_schema.model_validate(raw_input or {})
        except ValidationError as exc:
            raise ToolInputError(f"invalid input for {tool.name!r}: {exc.error_count()} error(s)") from exc

    def validate_output(self, tool: ToolDefinition, value: object) -> BaseModel:
        if isinstance(value, tool.output_schema):
            return value
        try:
            return tool.output_schema.model_validate(value)
        except (ValidationError, TypeError, AttributeError) as exc:
            raise ToolOutputError(f"handler for {tool.name!r} returned an invalid result") from exc

    # --- authorization (fail closed) --------------------------------------
    def _authorize_scope_and_permission(
        self, tool: ToolDefinition, ctx: ExecutionContext
    ) -> None:
        # 1. tenant scope — derived ONLY from the server-built context.
        if tool.tenant_scope in (TenantScope.BRAND, TenantScope.ORG):
            if ctx.tenant is None:
                raise ToolTenantError(f"tool {tool.name!r} requires a tenant context")
            if tool.tenant_scope == TenantScope.BRAND and ctx.tenant.brand_id is None:
                raise ToolTenantError(f"tool {tool.name!r} requires an active brand")
        # 2. permission — reuse the existing RBAC vocabulary; fail closed.
        if tool.permission is not None and not ctx.tenant.has_permission(tool.permission):
            raise ToolPermissionError(
                f"tool {tool.name!r} requires permission {tool.permission!r}"
            )

    def _authorize(self, tool: ToolDefinition, ctx: ExecutionContext) -> None:
        self._authorize_scope_and_permission(tool, ctx)
        # 3. consequential boundary — the public execute path NEVER auto-executes
        #    these. They must go through autonomy.evaluate_policy + the master
        #    switch + a human approval, which then calls `execute_consequential`.
        if tool.operation_class == OperationClass.CONSEQUENTIAL:
            raise ConsequentialExecutionError(
                f"tool {tool.name!r} is CONSEQUENTIAL — it must go through "
                "autonomy.evaluate_policy + the master switch + human approval. "
                "The registry does not auto-execute it."
            )

    # --- execution ---------------------------------------------------------
    async def execute_tool(
        self, name: str, raw_input: dict | None, ctx: ExecutionContext
    ) -> ToolResult:
        """Authorize, validate, run the existing service, validate the result.

        ``ctx`` is the server-derived scope; tenant/session authority is taken
        from it and NEVER from ``raw_input``."""
        tool = self.resolve_tool(name)
        self._authorize(tool, ctx)  # raises before any work on failure
        validated_input = self.validate_input(tool, raw_input)
        result = await tool.handler(ctx, validated_input)
        validated_output = self.validate_output(tool, result)
        log.info(
            "agent.tool.executed",
            tool=tool.name,
            operation_class=tool.operation_class.value,
            organization_id=str(ctx.tenant.organization_id),
            brand_id=str(ctx.tenant.brand_id) if ctx.tenant.brand_id else None,
        )
        return ToolResult(
            tool=tool.name,
            operation_class=tool.operation_class,
            provenance=tool.provenance,
            provenance_note=tool.provenance_note,
            data=validated_output,
        )

    async def execute_consequential(
        self, name: str, raw_input: dict | None, ctx: ExecutionContext
    ) -> ToolResult:
        """Execute a CONSEQUENTIAL tool AFTER a human approval cleared it.

        This path is NEVER reachable from the conversational agent runtime (which
        only ever calls ``execute_tool`` and hard-filters to READ before that).
        It is called ONLY by the approval service, and only once it has verified
        an APPROVED, unexpired, fingerprint-matching, same-tenant approval.

        It still re-applies tenant-scope + permission authorization from the
        server-derived ``ctx`` (never from input) and re-validates input/output.
        Resolving a non-consequential tool here is a hard error — a WRITE/READ
        tool can never be run through the consequential path."""
        tool = self.resolve_tool(name)
        if tool.operation_class != OperationClass.CONSEQUENTIAL:
            raise ToolError(
                f"tool {tool.name!r} is not CONSEQUENTIAL; refuse to run it via the "
                "approved-consequential path"
            )
        self._authorize_scope_and_permission(tool, ctx)
        validated_input = self.validate_input(tool, raw_input)
        result = await tool.handler(ctx, validated_input)
        validated_output = self.validate_output(tool, result)
        log.info(
            "agent.tool.executed_consequential",
            tool=tool.name,
            organization_id=str(ctx.tenant.organization_id),
            brand_id=str(ctx.tenant.brand_id) if ctx.tenant.brand_id else None,
        )
        return ToolResult(
            tool=tool.name,
            operation_class=tool.operation_class,
            provenance=tool.provenance,
            provenance_note=tool.provenance_note,
            data=validated_output,
        )
