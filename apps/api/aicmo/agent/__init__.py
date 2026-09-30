"""Agent boundary package.

Phase 1 ships ONLY the declarative Tool Registry — the controlled interface
through which a future Marketing Brain / Jarvis agent will discover and invoke
existing DM Tool capabilities. No agent runtime, conversation state, tool-calling
loop, or approval execution lives here yet (those are Phase 2+).
"""

from aicmo.agent.registry import ToolRegistry
from aicmo.agent.tools import get_default_registry, register_builtin_tools
from aicmo.agent.types import (
    ConsequentialExecutionError,
    DuplicateToolError,
    ExecutionContext,
    Idempotency,
    OperationClass,
    TenantScope,
    ToolDefinition,
    ToolError,
    ToolInput,
    ToolInputError,
    ToolNotFoundError,
    ToolOutputError,
    ToolPermissionError,
    ToolResult,
    ToolTenantError,
)

__all__ = [
    "ConsequentialExecutionError",
    "DuplicateToolError",
    "ExecutionContext",
    "Idempotency",
    "OperationClass",
    "TenantScope",
    "ToolDefinition",
    "ToolError",
    "ToolInput",
    "ToolInputError",
    "ToolNotFoundError",
    "ToolOutputError",
    "ToolPermissionError",
    "ToolRegistry",
    "ToolResult",
    "ToolTenantError",
    "get_default_registry",
    "register_builtin_tools",
]
