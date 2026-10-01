"""The consequential-tool surface — the approval boundary (Phase 4A).

This registry is SEPARATE from the conversational agent's read-only registry
(`tools.get_default_registry`). The conversational runtime never sees or runs
these tools; only the approval service resolves them, and only after a human
approval clears the exact action.

Phase 4A registers exactly ONE representative consequential tool —
``publish_scheduled_post`` — a publishing operation with a well-defined input
schema that is already idempotent (re-publishing an already-published post is a
no-op) and already refuses unapproved posts. Every other publisher / external
mutation remains unregistered and therefore unreachable through this pipeline.
"""

from __future__ import annotations

import uuid

from aicmo.agent.registry import ToolRegistry
from aicmo.agent.types import (
    ExecutionContext,
    Idempotency,
    OperationClass,
    TenantScope,
    ToolDefinition,
    ToolInput,
)
from aicmo.modules.publishing import service as publishing_service
from aicmo.modules.publishing.schemas import ScheduledPostResponse

# The RBAC slug the publishing module itself requires to publish content.
_PUBLISH_PERMISSION = "content.create"

# Which existing autonomy-policy action type publishing maps to (for the policy
# snapshot recorded on the approval — never to auto-approve).
_PUBLISH_ACTION_TYPE = "social_publishing"


class PublishScheduledPostInput(ToolInput):
    """Publish ONE already-scheduled post. The post must already exist and be
    owned by the active brand; the tool carries no tenant/brand id (authority is
    the ExecutionContext)."""

    scheduled_post_id: uuid.UUID


async def _publish_scheduled_post(
    ctx: ExecutionContext, inp: PublishScheduledPostInput
) -> ScheduledPostResponse:
    # Thin adapter over the EXISTING publishing service. Tenant comes from the
    # server-derived context; the service enforces brand ownership + the post's
    # own approval/hold gates, and is idempotent on an already-published post.
    return await publishing_service.publish_scheduled_post(
        ctx.session, scheduled_post_id=inp.scheduled_post_id, tenant=ctx.tenant
    )


PUBLISH_SCHEDULED_POST = ToolDefinition(
    name="publish_scheduled_post",
    description="Publish one already-scheduled social post to its connected platform.",
    category="publishing",
    operation_class=OperationClass.CONSEQUENTIAL,
    input_schema=PublishScheduledPostInput,
    output_schema=ScheduledPostResponse,
    handler=_publish_scheduled_post,
    permission=_PUBLISH_PERMISSION,
    tenant_scope=TenantScope.BRAND,
    approval_required=True,
    idempotency=Idempotency.REQUIRED,
    provenance=True,
    provenance_note="Published post id + platform post id from the publishing service.",
    autonomy_action_type=_PUBLISH_ACTION_TYPE,
)

CONSEQUENTIAL_TOOLS: list[ToolDefinition] = [PUBLISH_SCHEDULED_POST]

_ACTION_REGISTRY: ToolRegistry | None = None


def register_consequential_tools(registry: ToolRegistry) -> None:
    for tool in CONSEQUENTIAL_TOOLS:
        registry.register_tool(tool)


def get_action_registry() -> ToolRegistry:
    """The process-wide consequential-action registry (built once). Used ONLY by
    the approval service — never by the conversational agent runtime."""
    global _ACTION_REGISTRY
    if _ACTION_REGISTRY is None:
        registry = ToolRegistry()
        register_consequential_tools(registry)
        _ACTION_REGISTRY = registry
    return _ACTION_REGISTRY
