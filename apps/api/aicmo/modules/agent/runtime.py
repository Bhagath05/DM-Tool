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
from aicmo.modules.agent.models import AgentConversation, AgentMessage
from aicmo.modules.agent.prompts import PLANNING_SYSTEM, SYNTHESIS_SYSTEM, untrusted_block
from aicmo.modules.agent.schemas import (
    AgentPlan,
    AgentResponse,
    AgentSynthesis,
    BlockedAction,
    EvidenceRef,
    ReasoningSummary,
)
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


def _tool_catalog(registry: ToolRegistry) -> str:
    """A compact, server-authored allowlist for the planner (READ tools only)."""
    lines = ["ALLOWED TOOLS (use only these names):"]
    for meta in registry.list_tools(operation_class=OperationClass.READ):
        props = list((meta.get("input_schema") or {}).get("properties", {}).keys())
        args = f" args={props}" if props else " args=[]"
        lines.append(f"- {meta['name']}: {meta['description']}{args}")
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
    router=None,
) -> AgentResponse:
    """Run one bounded, read-only agent turn and persist the exchange."""
    registry = registry or get_default_registry()
    router = router or get_llm_router()
    started = time.monotonic()
    prompt_tokens = 0
    completion_tokens = 0
    model_used: str | None = None

    # 1. persist the user's message
    await _add_message(session, conversation=conversation, role="user", content=user_text)

    # 2. build the canonical marketing context (read-only, tenant-scoped)
    ctx = await mb_service.build_context(session, tenant=tenant)
    context_block = mb_service.context_to_prompt_block(ctx)

    # 3. plan
    history = await _recent_history(session, conversation.id)
    plan_messages: list[LLMMessage] = [
        LLMMessage(role="user", content=_tool_catalog(registry)),
        LLMMessage(role="user", content=untrusted_block("MARKETING CONTEXT", context_block)),
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

    # 4. execute ONLY READ tools, bounded, server-authorized
    exec_ctx = ExecutionContext(session=session, tenant=tenant)
    tools_consulted: list[str] = []
    evidence: list[EvidenceRef] = []
    actions_blocked: list[BlockedAction] = []
    tool_result_blocks: list[str] = []

    for call in plan.tool_calls[:MAX_TOOL_CALLS_PER_TURN]:
        tool = registry.get_tool(call.tool_name)
        if tool is None:
            actions_blocked.append(
                BlockedAction(tool_name=call.tool_name, operation_class="unknown", reason="UNKNOWN_TOOL")
            )
            continue
        # READ-ONLY ENFORCEMENT at the executor boundary — not the prompt.
        if tool.operation_class != _ALLOWED_CLASS:
            actions_blocked.append(
                BlockedAction(
                    tool_name=tool.name,
                    operation_class=tool.operation_class.value,
                    reason="ACTION_REQUIRES_APPROVAL",
                )
            )
            continue
        try:
            result = await registry.execute_tool(call.tool_name, call.arguments, exec_ctx)
        except ToolError as exc:
            # Permission/tenant/input failure for one tool never fails the turn.
            log.info("agent.tool.skipped", tool=call.tool_name, error=type(exc).__name__)
            actions_blocked.append(
                BlockedAction(
                    tool_name=call.tool_name,
                    operation_class=tool.operation_class.value,
                    reason=type(exc).__name__,
                )
            )
            continue
        tools_consulted.append(tool.name)
        evidence.append(
            EvidenceRef(label=tool.name, source=result.provenance_note if result.provenance else None)
        )
        tool_result_blocks.append(untrusted_block(f"TOOL RESULT: {tool.name}", _sanitize_result(result)))

    # 5. synthesize an answer from the (untrusted) data
    synth_messages: list[LLMMessage] = [
        LLMMessage(role="user", content=untrusted_block("MARKETING CONTEXT", context_block)),
        *(LLMMessage(role="user", content=b) for b in tool_result_blocks),
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
        "evidence_status": synth.evidence_status,
        "confidence": synth.confidence,
        "actions_blocked": [b.model_dump() for b in actions_blocked],
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
            "actions_blocked": [b.reason for b in actions_blocked],
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
        reasoning_summary=reasoning,
    )
