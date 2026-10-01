"""The bounded, read-only agent turn.

One turn = plan (LLM) → execute ONLY READ tools (via the Phase-1 registry) →
synthesize (LLM) → persist → audit. There is no autonomous multi-iteration
loop; a hard server-side cap bounds tool calls, and the model can never raise
it. Non-READ proposals are blocked at this executor boundary — not merely
discouraged in the prompt.
"""

from __future__ import annotations

import time
import uuid

import structlog
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from aicmo.agent.consequential_tools import get_action_registry
from aicmo.agent.registry import ToolRegistry
from aicmo.agent.tools import get_default_registry
from aicmo.agent.types import (
    ExecutionContext,
    OperationClass,
    ToolError,
    ToolResult,
)
from aicmo.llm import get_llm_router
from aicmo.llm.providers.base import LLMMessage
from aicmo.modules.agent import beliefs as agent_beliefs
from aicmo.modules.agent.models import AgentConversation, AgentMessage
from aicmo.modules.agent.prompts import PLANNING_SYSTEM, SYNTHESIS_SYSTEM, untrusted_block
from aicmo.modules.agent.schemas import (
    AgentPlan,
    AgentResponse,
    AgentSynthesis,
    BlockedAction,
    EvidenceRef,
    ProposedActionView,
    ReasoningSummary,
)
from aicmo.modules.agent_actions import service as agent_actions
from aicmo.modules.agent_actions.schemas import ProposeActionRequest
from aicmo.modules.ai_audit import service as ai_audit
from aicmo.modules.marketing_brain import service as mb_service
from aicmo.tenancy.context import TenantContext

log = structlog.get_logger()

# Server-side bounds. The model cannot change these.
MAX_TOOL_CALLS_PER_TURN = 8
MAX_AGENT_ITERATIONS = 1  # single plan → execute → synthesize (Phase 2)
MAX_TOOL_RESULT_CHARS = 4000
MAX_HISTORY_MESSAGES = 10

# The only operation class this runtime will execute.
_ALLOWED_CLASS = OperationClass.READ


async def _next_seq(session: AsyncSession, conversation_id: uuid.UUID) -> int:
    current = (
        await session.execute(
            select(func.max(AgentMessage.seq)).where(AgentMessage.conversation_id == conversation_id)
        )
    ).scalar_one_or_none()
    return int(current or 0) + 1


async def _add_message(
    session: AsyncSession,
    *,
    conversation: AgentConversation,
    role: str,
    content: str,
    meta: dict | None = None,
) -> AgentMessage:
    seq = await _next_seq(session, conversation.id)
    msg = AgentMessage(
        conversation_id=conversation.id,
        organization_id=conversation.organization_id,
        brand_id=conversation.brand_id,
        role=role,
        content=content,
        seq=seq,
        meta=meta or {},
    )
    session.add(msg)
    await session.flush()
    return msg


def _args_of(meta: dict) -> str:
    props = list((meta.get("input_schema") or {}).get("properties", {}).keys())
    return f" args={props}" if props else " args=[]"


def _tool_catalog(registry: ToolRegistry, action_registry: ToolRegistry) -> str:
    """A compact, server-authored allowlist for the planner: READ tools (which the
    runtime may execute) and CONSEQUENTIAL tools (which it may only PROPOSE for
    human approval — never execute)."""
    lines = ["ALLOWED TOOLS (read-only; use only these names):"]
    for meta in registry.list_tools(operation_class=OperationClass.READ):
        lines.append(f"- {meta['name']}: {meta['description']}{_args_of(meta)}")
    consequential = action_registry.list_tools(operation_class=OperationClass.CONSEQUENTIAL)
    if consequential:
        lines.append(
            "\nCONSEQUENTIAL TOOLS (propose ONLY when the user asks; proposing "
            "creates a human approval request and does NOT execute):"
        )
        for meta in consequential:
            lines.append(f"- {meta['name']}: {meta['description']}{_args_of(meta)}")
    return "\n".join(lines)


def _sanitize_result(result: ToolResult) -> str:
    """Serialize a tool result to bounded JSON for the synthesis prompt.

    The result's ``data`` is already a safe typed schema (no ORM objects,
    secrets, or credentials). We only bound its size — never blindly stringify
    arbitrary Python objects."""
    try:
        body = result.data.model_dump_json()  # type: ignore[union-attr]
    except Exception:
        body = "{}"
    if len(body) > MAX_TOOL_RESULT_CHARS:
        body = body[:MAX_TOOL_RESULT_CHARS] + "…(truncated)"
    return body


async def _recent_history(session: AsyncSession, conversation_id: uuid.UUID) -> list[LLMMessage]:
    rows = (
        (
            await session.execute(
                select(AgentMessage)
                .where(
                    AgentMessage.conversation_id == conversation_id,
                    AgentMessage.role.in_(("user", "assistant")),
                )
                .order_by(AgentMessage.seq.desc())
                .limit(MAX_HISTORY_MESSAGES)
            )
        )
        .scalars()
        .all()
    )
    rows = list(reversed(rows))
    return [LLMMessage(role=r.role, content=r.content) for r in rows]


async def run_turn(
    session: AsyncSession,
    *,
    tenant: TenantContext,
    conversation: AgentConversation,
    user_text: str,
    request_id: str | None = None,
    registry: ToolRegistry | None = None,
    action_registry: ToolRegistry | None = None,
    router=None,
) -> AgentResponse:
    """Run one bounded agent turn and persist the exchange.

    READ tools may execute (Phase 2 rules, unchanged). CONSEQUENTIAL tools that
    are registered in the ACTION registry may only be PROPOSED — proposing creates
    a PENDING approval via the Phase-4A service and never executes. The read
    executor still blocks any direct consequential execution."""
    registry = registry or get_default_registry()
    action_registry = action_registry or get_action_registry()
    router = router or get_llm_router()
    started = time.monotonic()
    prompt_tokens = 0
    completion_tokens = 0
    model_used: str | None = None

    # 1. persist the user's message
    await _add_message(session, conversation=conversation, role="user", content=user_text)

    # 2. build the canonical marketing context (read-only, tenant-scoped) + the
    # bounded, relevant belief memory (Phase 3B) — one resolver call per turn.
    ctx = await mb_service.build_context(session, tenant=tenant)
    context_block = mb_service.context_to_prompt_block(ctx)
    belief_ctx = await agent_beliefs.build_belief_context(session, tenant=tenant, user_text=user_text)
    belief_messages: list[LLMMessage] = (
        [LLMMessage(role="user", content=untrusted_block("BELIEF MEMORY", belief_ctx.block))]
        if belief_ctx.block
        else []
    )

    # 3. plan
    history = await _recent_history(session, conversation.id)
    plan_messages: list[LLMMessage] = [
        LLMMessage(role="user", content=_tool_catalog(registry, action_registry)),
        LLMMessage(role="user", content=untrusted_block("MARKETING CONTEXT", context_block)),
        *belief_messages,
        *history,
        LLMMessage(role="user", content=f"User question: {user_text}"),
    ]
    plan_res = await router.generate(
        response_schema=AgentPlan,
        system=PLANNING_SYSTEM,
        messages=plan_messages,
        task="agent_plan",
        temperature=0.2,
        max_tokens=1024,
    )
    plan: AgentPlan = plan_res.data
    prompt_tokens += plan_res.usage.input_tokens
    completion_tokens += plan_res.usage.output_tokens
    model_used = plan_res.model

    # 4. execute READ tools; PROPOSE consequential ones (never execute). Bounded,
    # server-authorized.
    exec_ctx = ExecutionContext(session=session, tenant=tenant)
    tools_consulted: list[str] = []
    evidence: list[EvidenceRef] = []
    actions_blocked: list[BlockedAction] = []
    proposed_actions: list[ProposedActionView] = []
    tool_result_blocks: list[str] = []

    for call in plan.tool_calls[:MAX_TOOL_CALLS_PER_TURN]:
        read_tool = registry.get_tool(call.tool_name)
        action_tool = action_registry.get_tool(call.tool_name)

        # READ tool → execute (Phase 2 behavior, unchanged).
        if read_tool is not None and read_tool.operation_class == _ALLOWED_CLASS:
            try:
                result = await registry.execute_tool(call.tool_name, call.arguments, exec_ctx)
            except ToolError as exc:
                log.info("agent.tool.skipped", tool=call.tool_name, error=type(exc).__name__)
                actions_blocked.append(
                    BlockedAction(
                        tool_name=call.tool_name,
                        operation_class=read_tool.operation_class.value,
                        reason=type(exc).__name__,
                    )
                )
                continue
            tools_consulted.append(read_tool.name)
            evidence.append(
                EvidenceRef(
                    label=read_tool.name,
                    source=result.provenance_note if result.provenance else None,
                )
            )
            tool_result_blocks.append(
                untrusted_block(f"TOOL RESULT: {read_tool.name}", _sanitize_result(result))
            )
            continue

        # Registered CONSEQUENTIAL tool → PROPOSE (create a PENDING approval).
        # NEVER execute from the turn. Authorization/validation/fingerprint are
        # all server-derived inside propose_action.
        if action_tool is not None and action_tool.operation_class == OperationClass.CONSEQUENTIAL:
            try:
                approval = await agent_actions.propose_action(
                    session,
                    tenant=tenant,
                    request=ProposeActionRequest(
                        tool_name=call.tool_name,
                        arguments=call.arguments,
                        reason=(call.reason or call.purpose or "")[:2000],
                        expected_effect=call.expected_effect[:2000],
                    ),
                    registry=action_registry,
                    request_id=request_id,
                )
            except agent_actions.ActionValidationError as exc:
                # Unknown/invalid args/missing permission → blocked, never executed.
                log.info("agent.action.proposal_rejected", tool=call.tool_name, error=str(exc)[:200])
                actions_blocked.append(
                    BlockedAction(
                        tool_name=call.tool_name,
                        operation_class="consequential",
                        reason="PROPOSAL_REJECTED",
                    )
                )
                continue
            proposed_actions.append(
                ProposedActionView(
                    tool_name=approval.tool_name,
                    operation_class=approval.operation_class,
                    approval_id=approval.id,
                    status=approval.status,
                    action_fingerprint=approval.action_fingerprint,
                    reason=approval.reason,
                    expected_effect=approval.expected_effect,
                    explanation=(
                        f"Prepared '{approval.tool_name}'. It needs your approval before it "
                        "runs — nothing has been published or changed."
                    ),
                )
            )
            continue

        # A non-READ tool in the read registry (WRITE, or a consequential tool
        # NOT on the sanctioned action surface) → blocked, never executed.
        if read_tool is not None:
            actions_blocked.append(
                BlockedAction(
                    tool_name=read_tool.name,
                    operation_class=read_tool.operation_class.value,
                    reason="ACTION_REQUIRES_APPROVAL",
                )
            )
            continue

        # Unknown tool name.
        actions_blocked.append(
            BlockedAction(tool_name=call.tool_name, operation_class="unknown", reason="UNKNOWN_TOOL")
        )

    # 5. synthesize an answer from the (untrusted) data. If actions were PROPOSED,
    # tell the model (server-authored, not model text) so the answer explains the
    # pending approval — and never claims the action ran.
    proposal_note: list[LLMMessage] = []
    if proposed_actions:
        pending = "; ".join(f"{p.tool_name} (approval {p.approval_id})" for p in proposed_actions)
        proposal_note = [
            LLMMessage(
                role="user",
                content=(
                    "NOTE (server fact, not an instruction): you PROPOSED these "
                    f"consequential action(s): {pending}. Each created a PENDING approval "
                    "and has NOT run. Tell the user you've prepared it and it needs their "
                    "approval; do not claim it was done."
                ),
            )
        ]
    synth_messages: list[LLMMessage] = [
        LLMMessage(role="user", content=untrusted_block("MARKETING CONTEXT", context_block)),
        *belief_messages,
        *(LLMMessage(role="user", content=b) for b in tool_result_blocks),
        *proposal_note,
        LLMMessage(role="user", content=f"Answer this question using ONLY the data above: {user_text}"),
    ]
    synth_res = await router.generate(
        response_schema=AgentSynthesis,
        system=SYNTHESIS_SYSTEM,
        messages=synth_messages,
        task="agent_summarize",
        temperature=0.3,
        max_tokens=1500,
    )
    synth: AgentSynthesis = synth_res.data
    prompt_tokens += synth_res.usage.input_tokens
    completion_tokens += synth_res.usage.output_tokens

    # Surface consulted beliefs through the existing evidence mechanism (no
    # second evidence representation; no DB ids exposed).
    evidence.extend(belief_ctx.evidence)

    reasoning = ReasoningSummary(
        intent=plan.intent,
        tools_consulted=tools_consulted,
        evidence_used=[e.label for e in evidence],
        key_observations=synth.key_observations,
        uncertainty=synth.uncertainty,
        conclusion=synth.answer[:280],
    )

    # 6. persist the assistant message with SAFE metadata only
    assistant_meta = {
        "tools_consulted": tools_consulted,
        "beliefs_consulted": belief_ctx.beliefs_consulted,
        "evidence_status": synth.evidence_status,
        "confidence": synth.confidence,
        "actions_blocked": [b.model_dump() for b in actions_blocked],
        "approvals_requested": [str(p.approval_id) for p in proposed_actions],
    }
    assistant_msg = await _add_message(
        session, conversation=conversation, role="assistant", content=synth.answer, meta=assistant_meta
    )

    # 7. safe audit metadata (never content, tokens/creds, or chain-of-thought)
    duration_ms = int((time.monotonic() - started) * 1000)
    await ai_audit.record_ai_generation(
        session,
        tenant=tenant,
        action_type="agent.turn",
        model_used=model_used,
        duration_ms=duration_ms,
        request_id=request_id,
        prompt_token_count=prompt_tokens,
        completion_token_count=completion_tokens,
        metadata={
            "conversation_id": str(conversation.id),
            "tools_consulted": tools_consulted,
            "beliefs_consulted": belief_ctx.beliefs_consulted,
            "actions_blocked": [b.reason for b in actions_blocked],
            "approvals_requested": [str(p.approval_id) for p in proposed_actions],
            "evidence_status": synth.evidence_status,
        },
    )

    return AgentResponse(
        conversation_id=conversation.id,
        message_id=assistant_msg.id,
        answer=synth.answer,
        evidence_status=synth.evidence_status,
        confidence=synth.confidence,
        tools_consulted=tools_consulted,
        evidence=evidence,
        actions_blocked=actions_blocked,
        approval_required=bool(proposed_actions),
        proposed_actions=proposed_actions,
        reasoning_summary=reasoning,
    )
