"""Approval-gated consequential execution (Phase 4A).

The one server-side path between an agent *proposing* a consequential action and
that action *executing*. Authority is ALWAYS server-derived:

    propose  -> validate tool + input + authz + autonomy snapshot -> PENDING
    approve  -> human decision (real actor) -> APPROVED          [separate step]
    execute  -> RE-validate everything -> run exact action -> EXECUTED / FAILED

The model may influence only the tool name, the (schema-validated) input, and the
human-readable reason/effect. It can never set tenant, user, approval state,
the decision, execution permission, or the fingerprint. Consequential actions
ALWAYS require a human approval — even when autonomy is enabled and the master
switch is on (no autonomous consequential execution in Phase 4A).
"""

from __future__ import annotations

import uuid
from datetime import UTC, datetime, timedelta

import structlog
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from aicmo.agent.consequential_tools import get_action_registry
from aicmo.agent.registry import ToolRegistry
from aicmo.agent.types import (
    ExecutionContext,
    OperationClass,
    ToolError,
    ToolNotFoundError,
)
from aicmo.modules.agent_actions import fingerprint as fp
from aicmo.modules.agent_actions.enums import ApprovalStatus, can_transition
from aicmo.modules.agent_actions.models import AgentActionApproval
from aicmo.modules.agent_actions.schemas import ApprovalView, ProposeActionRequest
from aicmo.modules.audit import service as audit_service
from aicmo.modules.autonomy import service as autonomy_service
from aicmo.tenancy.context import TenantContext

log = structlog.get_logger()

# Short-lived: consequential marketing actions must be acted on promptly, and a
# stale approval must not linger. Server-set; clients cannot extend it.
APPROVAL_TTL = timedelta(minutes=30)
_FALLBACK_ACTION_TYPE = "integration"


class ApprovalError(Exception):
    """Base for approval-pipeline errors."""


class ApprovalNotFoundError(ApprovalError):
    """No such approval for this tenant (also the cross-tenant miss)."""


class ApprovalStateError(ApprovalError):
    """An illegal state transition or an execution attempt on a non-approved /
    expired / stale approval."""


class ActionValidationError(ApprovalError):
    """The proposed action failed validation (unknown tool, wrong class, bad
    input, missing authorization)."""


def _require_brand(tenant: TenantContext) -> uuid.UUID:
    if tenant.brand_id is None:
        raise ActionValidationError("A brand must be selected for consequential actions.")
    return tenant.brand_id


def _view(row: AgentActionApproval) -> ApprovalView:
    return ApprovalView.model_validate(
        {
            "id": row.id,
            "tool_name": row.tool_name,
            "operation_class": row.operation_class,
            "status": row.status,
            "arguments": row.action_input or {},
            "action_fingerprint": row.action_fingerprint,
            "autonomy_action_type": row.autonomy_action_type,
            "policy_mode": row.policy_mode,
            "reason": row.reason,
            "expected_effect": row.expected_effect,
            "requested_by_user_id": row.requested_by_user_id,
            "decided_by_user_id": row.decided_by_user_id,
            "decided_at": row.decided_at,
            "decision_reason": row.decision_reason,
            "expires_at": row.expires_at,
            "executed_at": row.executed_at,
            "result": row.result or {},
            "created_at": row.created_at,
            "updated_at": row.updated_at,
        }
    )


def _transition(row: AgentActionApproval, target: ApprovalStatus) -> None:
    current = ApprovalStatus(row.status)
    if not can_transition(current, target):
        raise ApprovalStateError(
            f"illegal approval transition {current.value} -> {target.value}"
        )
    row.status = target.value


async def _maybe_expire(session: AsyncSession, row: AgentActionApproval, now: datetime) -> None:
    """Lazily expire a PENDING/APPROVED approval whose TTL elapsed. Expiry is a
    legal transition and blocks any later execution."""
    if row.status in (ApprovalStatus.PENDING.value, ApprovalStatus.APPROVED.value):
        expires = row.expires_at
        if expires is not None and expires.tzinfo is None:
            expires = expires.replace(tzinfo=UTC)
        if expires is not None and expires <= now:
            _transition(row, ApprovalStatus.EXPIRED)
            await session.flush()


# ---------------------------------------------------------------------
#  Propose
# ---------------------------------------------------------------------
async def propose_action(
    session: AsyncSession,
    *,
    tenant: TenantContext,
    request: ProposeActionRequest,
    registry: ToolRegistry | None = None,
    request_id: str | None = None,
) -> AgentActionApproval:
    """Validate and record a proposed consequential action as a PENDING approval.

    NEVER executes. Resolves the tool against the consequential registry ONLY
    (unknown tool → rejected), validates input against the tool's schema,
    enforces tenant-scope + permission from the server-derived context, snapshots
    the autonomy decision, and binds the approval to the exact-action
    fingerprint computed from the VALIDATED input."""
    brand_id = _require_brand(tenant)
    registry = registry or get_action_registry()

    try:
        tool = registry.resolve_tool(request.tool_name)
    except ToolNotFoundError as exc:
        raise ActionValidationError(f"unknown consequential tool: {request.tool_name!r}") from exc
    if tool.operation_class != OperationClass.CONSEQUENTIAL:
        raise ActionValidationError(f"tool {tool.name!r} is not a consequential action")

    ctx = ExecutionContext(session=session, tenant=tenant)
    # Authorize (tenant scope + permission) from the server context; fail closed.
    try:
        registry._authorize_scope_and_permission(tool, ctx)
    except ToolError as exc:
        raise ActionValidationError(str(exc)) from exc

    # Validate the LLM-proposed arguments against the tool's schema. Only the
    # canonical validated input is ever stored or fingerprinted.
    try:
        validated = registry.validate_input(tool, request.arguments)
    except ToolError as exc:
        raise ActionValidationError(str(exc)) from exc
    action_input = validated.model_dump(mode="json")

    # Autonomy snapshot. Consequential actions ALWAYS require human approval in
    # Phase 4A, so we record the policy decision but never auto-approve from it.
    action_type = tool.autonomy_action_type or _FALLBACK_ACTION_TYPE
    cfg = await autonomy_service.get_or_default(session, brand_id=brand_id)
    decision = autonomy_service.evaluate_policy(
        cfg, action_type, execution_enabled=cfg.execution_enabled
    )

    fingerprint = fp.fingerprint_action(
        organization_id=tenant.organization_id,
        brand_id=brand_id,
        tool_name=tool.name,
        operation_class=tool.operation_class.value,
        action_input=action_input,
    )
    now = datetime.now(UTC)
    row = AgentActionApproval(
        organization_id=tenant.organization_id,
        brand_id=brand_id,
        requested_by_user_id=tenant.user_uuid,
        tool_name=tool.name,
        operation_class=tool.operation_class.value,
        action_input=action_input,
        action_fingerprint=fingerprint,
        idempotency_key=fp.idempotency_key(fingerprint),
        autonomy_action_type=action_type,
        policy_mode=decision.mode,
        reason=request.reason or None,
        expected_effect=request.expected_effect or None,
        status=ApprovalStatus.PENDING.value,
        expires_at=now + APPROVAL_TTL,
        request_id=request_id,
    )
    session.add(row)
    await session.flush()

    await audit_service.record(
        session,
        organization_id=tenant.organization_id,
        brand_id=brand_id,
        actor_user_id=tenant.user_uuid,
        action="agent_action.proposed",
        target_type="agent_action_approval",
        target_id=row.id,
        after={"status": row.status},
        metadata={
            "tool": tool.name,
            "operation_class": tool.operation_class.value,
            "action_fingerprint": fingerprint,
            "policy_mode": decision.mode,
            "request_id": request_id,
        },
    )
    log.info(
        "agent_action.proposed",
        approval_id=str(row.id),
        tool=tool.name,
        organization_id=str(tenant.organization_id),
        brand_id=str(brand_id),
    )
    return row


# ---------------------------------------------------------------------
#  Read
# ---------------------------------------------------------------------
async def get_approval(
    session: AsyncSession, *, tenant: TenantContext, approval_id: uuid.UUID
) -> AgentActionApproval:
    brand_id = _require_brand(tenant)
    row = (
        await session.execute(
            select(AgentActionApproval).where(
                AgentActionApproval.id == approval_id,
                AgentActionApproval.brand_id == brand_id,
                AgentActionApproval.organization_id == tenant.organization_id,
            )
        )
    ).scalar_one_or_none()
    if row is None:
        # Nonexistent OR another tenant's approval → fail closed, never leak.
        raise ApprovalNotFoundError(str(approval_id))
    await _maybe_expire(session, row, datetime.now(UTC))
    return row


async def list_approvals(
    session: AsyncSession, *, tenant: TenantContext, status: str | None = None, limit: int = 50
) -> list[AgentActionApproval]:
    brand_id = _require_brand(tenant)
    stmt = select(AgentActionApproval).where(
        AgentActionApproval.brand_id == brand_id,
        AgentActionApproval.organization_id == tenant.organization_id,
    )
    if status is not None:
        stmt = stmt.where(AgentActionApproval.status == status)
    stmt = stmt.order_by(AgentActionApproval.created_at.desc()).limit(max(1, min(limit, 200)))
    rows = list((await session.execute(stmt)).scalars().all())
    now = datetime.now(UTC)
    for row in rows:
        await _maybe_expire(session, row, now)
    return rows


# ---------------------------------------------------------------------
#  Human decision
# ---------------------------------------------------------------------
def _assert_binding_current(
    tenant: TenantContext, row: AgentActionApproval, registry: ToolRegistry
) -> None:
    """Fail closed unless the approval still binds its EXACT action under the
    CURRENT tool definition: the tool must still be a registered consequential
    tool, the stored input must still satisfy its schema, and the recomputed
    fingerprint must equal the stored one. Does NOT change state — a drifted
    action simply cannot be approved; it must be re-proposed."""
    try:
        tool = registry.resolve_tool(row.tool_name)
    except ToolNotFoundError as exc:
        raise ApprovalStateError(
            f"tool {row.tool_name!r} is no longer registered — a new approval is required"
        ) from exc
    if tool.operation_class != OperationClass.CONSEQUENTIAL:
        raise ApprovalStateError(f"tool {row.tool_name!r} is no longer a consequential action")
    try:
        registry.validate_input(tool, row.action_input)
    except ToolError as exc:
        raise ApprovalStateError("stored action input no longer matches the tool schema") from exc
    expected_fp = fp.fingerprint_action(
        organization_id=tenant.organization_id,
        brand_id=row.brand_id,
        tool_name=tool.name,
        operation_class=tool.operation_class.value,
        action_input=row.action_input,
    )
    if expected_fp != row.action_fingerprint:
        raise ApprovalStateError(
            "action fingerprint no longer matches — a new approval is required"
        )


async def approve(
    session: AsyncSession,
    *,
    tenant: TenantContext,
    approval_id: uuid.UUID,
    reason: str | None = None,
    registry: ToolRegistry | None = None,
) -> AgentActionApproval:
    """Record a HUMAN approval of the exact action. The actor is the
    authenticated user from the server-derived tenant — never model-supplied.

    Before transitioning, re-validate that the action still binds exactly (tool
    exists + input still valid + fingerprint unchanged). A human can only approve
    the precise action that was proposed; drift fails closed."""
    registry = registry or get_action_registry()
    row = await get_approval(session, tenant=tenant, approval_id=approval_id)
    # Re-validate the binding BEFORE the state check so a drifted action cannot be
    # approved even while still PENDING.
    _assert_binding_current(tenant, row, registry)
    before = {"status": row.status}
    _transition(row, ApprovalStatus.APPROVED)  # raises if not PENDING
    row.decided_by_user_id = tenant.user_uuid
    row.decided_at = datetime.now(UTC)
    row.decision_reason = reason
    await session.flush()
    await audit_service.record(
        session,
        organization_id=tenant.organization_id,
        brand_id=row.brand_id,
        actor_user_id=tenant.user_uuid,
        action="agent_action.approved",
        target_type="agent_action_approval",
        target_id=row.id,
        before=before,
        after={"status": row.status},
        metadata={"action_fingerprint": row.action_fingerprint, "tool": row.tool_name},
    )
    return row


async def reject(
    session: AsyncSession, *, tenant: TenantContext, approval_id: uuid.UUID, reason: str | None = None
) -> AgentActionApproval:
    row = await get_approval(session, tenant=tenant, approval_id=approval_id)
    before = {"status": row.status}
    _transition(row, ApprovalStatus.REJECTED)  # raises if not PENDING
    row.decided_by_user_id = tenant.user_uuid
    row.decided_at = datetime.now(UTC)
    row.decision_reason = reason
    await session.flush()
    await audit_service.record(
        session,
        organization_id=tenant.organization_id,
        brand_id=row.brand_id,
        actor_user_id=tenant.user_uuid,
        action="agent_action.rejected",
        target_type="agent_action_approval",
        target_id=row.id,
        before=before,
        after={"status": row.status},
        metadata={"action_fingerprint": row.action_fingerprint, "tool": row.tool_name},
    )
    return row


# ---------------------------------------------------------------------
#  Execution (only if approved)
# ---------------------------------------------------------------------
def _summarize_result(data: object) -> tuple[bool, dict]:
    """Validate the structured result and decide success. Never fabricate
    success: a publish is successful only when the post reports 'published' with
    an external post id. Only safe, non-secret fields enter the summary."""
    publish_status = getattr(data, "publish_status", None)
    platform_post_id = getattr(data, "platform_post_id", None)
    scheduled_post_id = getattr(data, "id", None)
    published = str(publish_status) == "published" and bool(platform_post_id)
    summary = {
        "published": published,
        "publish_status": str(publish_status) if publish_status is not None else None,
        "has_platform_post_id": bool(platform_post_id),
        "scheduled_post_id": str(scheduled_post_id) if scheduled_post_id is not None else None,
    }
    return published, summary


async def execute_approved(
    session: AsyncSession,
    *,
    tenant: TenantContext,
    approval_id: uuid.UUID,
    registry: ToolRegistry | None = None,
    request_id: str | None = None,
) -> AgentActionApproval:
    """Execute the EXACT approved action after re-validating everything.

    Re-checks (never trusts the validation done at proposal time): authenticated
    user + tenant (via the tenant-scoped load), approval state, expiration,
    action fingerprint, current tool definition, input schema, and idempotency.
    Idempotent: an already-executed approval returns its stored result without
    re-running the underlying service."""
    registry = registry or get_action_registry()
    row = await get_approval(session, tenant=tenant, approval_id=approval_id)

    # Idempotency: the same approved action never executes twice. A retry on an
    # already-executed approval returns the prior result; no second external call.
    if row.status == ApprovalStatus.EXECUTED.value:
        return row
    if row.status != ApprovalStatus.APPROVED.value:
        raise ApprovalStateError(
            f"approval {approval_id} is {row.status}; only an APPROVED, unexpired "
            "action can execute"
        )

    # Re-resolve the tool from the current registry — a removed tool fails closed.
    try:
        tool = registry.resolve_tool(row.tool_name)
    except ToolNotFoundError as exc:
        await _fail(session, tenant, row, reason="tool_no_longer_registered", request_id=request_id)
        raise ApprovalStateError(f"tool {row.tool_name!r} is no longer registered") from exc

    # Re-check the exact-action binding against the CURRENT tool definition.
    expected_fp = fp.fingerprint_action(
        organization_id=tenant.organization_id,
        brand_id=row.brand_id,
        tool_name=tool.name,
        operation_class=tool.operation_class.value,
        action_input=row.action_input,
    )
    if expected_fp != row.action_fingerprint:
        await _fail(session, tenant, row, reason="fingerprint_mismatch", request_id=request_id)
        raise ApprovalStateError("action fingerprint no longer matches — a new approval is required")

    ctx = ExecutionContext(session=session, tenant=tenant)
    try:
        # execute_consequential re-applies tenant-scope + permission authz and
        # re-validates input/output. The stored validated input is replayed.
        result = await registry.execute_consequential(tool.name, row.action_input, ctx)
    except ToolError as exc:
        await _fail(session, tenant, row, reason=type(exc).__name__, request_id=request_id)
        raise ApprovalStateError(f"execution authorization/validation failed: {type(exc).__name__}") from exc
    except Exception as exc:  # record the failure, never claim success
        await _fail(session, tenant, row, reason="execution_error", request_id=request_id)
        log.warning("agent_action.execution_error", approval_id=str(row.id), error=str(exc)[:200])
        return row

    published, summary = _summarize_result(result.data)
    row.executed_at = datetime.now(UTC)
    row.result = summary
    if published:
        _transition(row, ApprovalStatus.EXECUTED)
        audit_action = "agent_action.executed"
    else:
        _transition(row, ApprovalStatus.FAILED)
        audit_action = "agent_action.failed"
    await session.flush()
    await audit_service.record(
        session,
        organization_id=tenant.organization_id,
        brand_id=row.brand_id,
        actor_user_id=tenant.user_uuid,
        action=audit_action,
        target_type="agent_action_approval",
        target_id=row.id,
        after={"status": row.status},
        metadata={
            "tool": tool.name,
            "action_fingerprint": row.action_fingerprint,
            "idempotency_key": row.idempotency_key,
            "result": summary,
            "request_id": request_id,
        },
    )
    return row


async def _fail(
    session: AsyncSession,
    tenant: TenantContext,
    row: AgentActionApproval,
    *,
    reason: str,
    request_id: str | None,
) -> None:
    """Mark an APPROVED action FAILED and audit it (never silently)."""
    if row.status == ApprovalStatus.APPROVED.value:
        _transition(row, ApprovalStatus.FAILED)
        row.executed_at = datetime.now(UTC)
        row.result = {"published": False, "error": reason}
        await session.flush()
    await audit_service.record(
        session,
        organization_id=tenant.organization_id,
        brand_id=row.brand_id,
        actor_user_id=tenant.user_uuid,
        action="agent_action.failed",
        target_type="agent_action_approval",
        target_id=row.id,
        after={"status": row.status},
        metadata={"action_fingerprint": row.action_fingerprint, "error": reason, "request_id": request_id},
    )
