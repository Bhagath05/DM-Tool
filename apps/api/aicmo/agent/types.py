"""Declarative tool contract for the (future) Marketing Brain / Jarvis agent.

This module defines the TYPES only — the strongly-typed tool definition, the
operation classes, the server-derived execution context, the typed result
envelope, and the fail-closed error hierarchy. It contains NO business logic and
NO service calls.

Security invariants encoded here:
- A tool input is a Pydantic model with ``extra="forbid"`` — a model can never
  smuggle a ``tenant_id`` / authorization argument through tool input.
- Tenant authority comes ONLY from ``ExecutionContext`` (server-derived), never
  from tool input.
- Tool metadata for discovery exposes NO handler reference and NO module path.
"""

from __future__ import annotations

import enum
from collections.abc import Awaitable, Callable
from dataclasses import dataclass
from typing import TYPE_CHECKING, Any

from pydantic import BaseModel, ConfigDict

if TYPE_CHECKING:
    from sqlalchemy.ext.asyncio import AsyncSession

    from aicmo.tenancy.context import TenantContext


class OperationClass(enum.StrEnum):
    """How consequential a tool is. Drives the execution/approval boundary."""

    READ = "read"  # safe, read-only; no approval
    WRITE = "write"  # creates/changes non-consequential state; normal authz+audit
    CONSEQUENTIAL = "consequential"  # external/irreversible/spend/publish/send/delete


class TenantScope(enum.StrEnum):
    BRAND = "brand"  # requires an active brand in the execution context
    ORG = "org"  # org-level (brand optional)
    NONE = "none"  # not tenant-scoped (none exist in Phase 1)


class Idempotency(enum.StrEnum):
    NOT_REQUIRED = "not_required"  # READ tools
    REQUIRED = "required"  # future WRITE/CONSEQUENTIAL tools


class ToolInput(BaseModel):
    """Base class for every tool input schema.

    ``extra="forbid"`` means unexpected fields (e.g. a smuggled ``tenant_id`` or
    ``brand_id``) are REJECTED, not silently ignored — the model cannot pass
    authorization data through tool input."""

    model_config = ConfigDict(extra="forbid")


# --- fail-closed error hierarchy -------------------------------------------
class ToolError(RuntimeError):
    """Base for all tool-registry errors."""


class ToolNotFoundError(ToolError):
    """The requested tool name is not in the allowlisted registry."""


class DuplicateToolError(ToolError):
    """A tool with this name is already registered."""


class ToolPermissionError(ToolError):
    """The execution context lacks the tool's required permission."""


class ToolTenantError(ToolError):
    """The tool is tenant-scoped but the context has no (or no brand) tenant."""


class ToolInputError(ToolError):
    """The provided input failed the tool's input schema."""


class ToolOutputError(ToolError):
    """The handler returned a value that failed the tool's output schema."""


class ConsequentialExecutionError(ToolError):
    """A CONSEQUENTIAL tool cannot be executed directly by the registry.

    It must go through ``autonomy.evaluate_policy`` + the master switch + human
    approval (Phase 2). The registry never auto-executes a consequential tool —
    model confidence can never bypass this."""


@dataclass(frozen=True)
class ExecutionContext:
    """The server-derived scope a tool runs in — the ONLY source of tenant and
    session authority. Never built from model/tool input."""

    session: AsyncSession
    tenant: TenantContext


# Handlers are validated at runtime (validate_input / validate_output), so the
# static type is intentionally loose — each handler may take/return its own
# concrete Pydantic models.
ToolHandler = Callable[["ExecutionContext", Any], Awaitable[Any]]


@dataclass(frozen=True)
class ToolDefinition:
    """One registered capability. Pure declarative metadata + a bound handler.

    The handler is a Python callable fixed at registration time (module code) —
    tool NAMES resolve only against the registry dict; there is no dynamic import
    or ``globals()[name]`` execution anywhere.
    """

    name: str
    description: str
    category: str
    operation_class: OperationClass
    input_schema: type[BaseModel]
    output_schema: type[BaseModel]
    handler: ToolHandler
    permission: str | None = None  # RBAC slug; None = tenant membership suffices
    tenant_scope: TenantScope = TenantScope.BRAND
    approval_required: bool = False
    idempotency: Idempotency = Idempotency.NOT_REQUIRED
    provenance: bool = False  # does the result carry source/evidence references?
    provenance_note: str | None = None

    def metadata(self) -> dict[str, Any]:
        """Safe declarative metadata for tool discovery.

        Deliberately excludes the handler and any module path — a future agent /
        LLM sees only what it needs to choose and shape a call."""
        return {
            "name": self.name,
            "description": self.description,
            "category": self.category,
            "operation_class": self.operation_class.value,
            "permission": self.permission,
            "tenant_scope": self.tenant_scope.value,
            "approval_required": self.approval_required,
            "idempotency": self.idempotency.value,
            "provenance": self.provenance,
            "provenance_note": self.provenance_note,
            "input_schema": self.input_schema.model_json_schema(),
            "output_schema": self.output_schema.__name__,
        }


class ToolResult(BaseModel):
    """Typed envelope returned from ``execute_tool``.

    Carries only safe, structured, schema-validated ``data`` (a Pydantic model)
    — never a raw ORM object, a DB session, a secret, or an infra detail."""

    model_config = ConfigDict(arbitrary_types_allowed=True)

    tool: str
    operation_class: OperationClass
    provenance: bool
    provenance_note: str | None = None
    data: Any
