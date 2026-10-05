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
from datetime import UTC, datetime

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
from aicmo.modules.trust import enforcement as trust_enforcement
from aicmo.modules.trust import shadow as trust_shadow
from aicmo.modules.trust.contracts import (
    CandidateClaim,
    CandidateRecommendation,
    ModelProvenance,
)
from aicmo.modules.trust.contracts import EvidenceRef as TrustEvidenceRef
from aicmo.modules.trust.enforcement import EnforcedResponse, enforce, fail_safe
from aicmo.modules.trust.enums import ClaimType, ConsequenceLevel, SourceTier
from aicmo.modules.trust.provenance import EvidenceKind, EvidenceReference
from aicmo.tenancy.context import TenantContext

log = structlog.get_logger()

# Server-side bounds. The model cannot change these.
MAX_TOOL_CALLS_PER_TURN = 8
MAX_AGENT_ITERATIONS = 1  # single plan → execute → synthesize (Phase 2)
MAX_TOOL_RESULT_CHARS = 4000
MAX_HISTORY_MESSAGES = 10

# The only operation class this runtime will execute.
_ALLOWED_CLASS = OperationClass.READ

# Deterministic consequence mapping for a PROPOSED consequential action, from the
# action registry's own autonomy/category metadata (never from the model). Used
# only for the SHADOW trust result — it never gates approval or execution.
_HIGH_CONSEQUENCE_ACTION_TYPES = frozenset(
    {"social_publishing", "ad_spend", "budget_change", "campaign_launch", "email_send", "crm_write"}
)
_HIGH_CONSEQUENCE_CATEGORIES = frozenset({"publishing", "ads", "email", "crm", "budget"})


def _consequence_for(tool_def) -> ConsequenceLevel:
    if tool_def is None:
        return ConsequenceLevel.HIGH  # unknown consequential tool → safest shadow bar
    action_type = (getattr(tool_def, "autonomy_action_type", "") or "").lower()
    category = (getattr(tool_def, "category", "") or "").lower()
    if action_type in _HIGH_CONSEQUENCE_ACTION_TYPES or category in _HIGH_CONSEQUENCE_CATEGORIES:
        return ConsequenceLevel.HIGH
    return ConsequenceLevel.MEDIUM


def _build_shadow_input(
    *,
    belief_ctx,
    synth,
    tools_consulted: list[str],
    proposed_actions: list[ProposedActionView],
    action_registry: ToolRegistry,
    model_used: str | None,
    now: datetime,
) -> trust_shadow.ShadowInput:
    """Map the turn's STRUCTURED candidate into a Trust ShadowInput.

    The answer is represented as ONE claim backed by the turn's verified
    evidence: each successfully executed READ tool is first-party data the
    *server* produced (asserted directly, never submitted to T1 since it is not
    LLM-supplied), and each consulted belief is submitted to T1 for tenant-scoped
    resolution. Prose is never parsed into imaginary claims; the LLM confidence
    rides along as diagnostic only.
    """
    # The turn's VERIFIED evidence base — supplied by the server, not the model:
    # each successfully executed READ tool is first-party data (asserted directly,
    # never submitted to T1 since it is server-produced); each consulted belief is
    # submitted to T1 for tenant-scoped resolution. The model cannot fabricate
    # evidence — it only proposes claim text/type; the server supplies the pool.
    tool_evidence = [
        TrustEvidenceRef(
            evidence_id=f"tool:{name}", kind="tool",
            source_tier=SourceTier.FIRST_PARTY_DATA, observed_at=now,
        )
        for name in tools_consulted
    ]
    belief_evidence = [
        TrustEvidenceRef(evidence_id=str(cb.belief_id), kind=EvidenceKind.BELIEF.value)
        for cb in belief_ctx.consulted
    ]
    pool = tool_evidence + belief_evidence
    refs = [
        EvidenceReference(evidence_id=str(cb.belief_id), kind=EvidenceKind.BELIEF.value)
        for cb in belief_ctx.consulted
    ]

    if synth.claims:
        # Structured mode (T4): validate each proposed claim individually against
        # the turn's evidence pool. The model's claim_type is a proposal; T0
        # demotes it when the evidence does not support it.
        candidate_claims = [
            CandidateClaim(
                statement=c.statement,
                proposed_type=ClaimType(c.claim_type),
                proposed_confidence=synth.confidence,
                evidence=list(pool),
                is_metric_claim=c.is_metric,
                is_causal_claim=c.is_causal,
            )
            for c in synth.claims
        ]
    else:
        # Fallback: validate the turn as one synthetic overall claim.
        candidate_claims = [
            CandidateClaim(
                statement=trust_enforcement.SYNTHETIC_ANSWER_CLAIM,
                proposed_type=ClaimType.OBSERVATION,
                proposed_confidence=synth.confidence,
                evidence=list(pool),
            )
        ]

    recs = [
        CandidateRecommendation(
            statement=p.tool_name,
            consequence_level=_consequence_for(action_registry.get_tool(p.tool_name)),
        )
        for p in proposed_actions
    ]
    return trust_shadow.ShadowInput(
        candidate_claims=candidate_claims,
        candidate_recommendations=recs,
        proposed_causal_statements=list(synth.key_observations),
        evidence_refs=refs,
        llm_confidence=synth.confidence,
        llm_evidence_status=synth.evidence_status,
        model_provenance=ModelProvenance(model=model_used),
    )


async def _enforce_trust(
    session: AsyncSession,
    *,
    tenant: TenantContext,
    belief_ctx,
    synth,
    tools_consulted: list[str],
    proposed_actions: list[ProposedActionView],
    action_registry: ToolRegistry,
    model_used: str | None,
    request_id: str | None,
) -> EnforcedResponse:
    """T3 ENFORCEMENT. Validate the candidate with T0+T1, derive the
    server-authoritative outcome, record a safe audit row, and return the
    enforced confidence / evidence_status / trust envelope for the runtime to
    apply. The LLM is never the authority.

    FAIL-SAFE: unlike T2, any unexpected validation error degrades the
    trust-sensitive output to INSUFFICIENT_EVIDENCE (never a preserved
    high-confidence claim) — the unrelated answer text is still returned.
    """
    try:
        shadow_input = _build_shadow_input(
            belief_ctx=belief_ctx, synth=synth, tools_consulted=tools_consulted,
            proposed_actions=proposed_actions, action_registry=action_registry,
            model_used=model_used, now=datetime.now(UTC),
        )
        result = await trust_shadow.validate_turn_shadow(session, tenant=tenant, shadow_input=shadow_input)
        enforced = enforce(result)
        audit = dict(result.audit)
        audit["enforcement_outcome"] = enforced.envelope.status.value
        audit["enforced_confidence"] = enforced.confidence
        audit["degraded"] = enforced.envelope.degraded
        await ai_audit.record_ai_generation(
            session, tenant=tenant, action_type="trust.enforcement",
            model_used=model_used, request_id=request_id, metadata=audit,
        )
        return enforced
    except Exception as exc:  # enforcement must degrade safely, never crash the turn
        log.info("trust.enforcement.error", error=type(exc).__name__)
        enforced = fail_safe()
        try:
            await ai_audit.record_ai_generation(
                session, tenant=tenant, action_type="trust.enforcement",
                model_used=model_used, request_id=request_id,
                generation_status="error", error_class=type(exc).__name__,
                metadata={
                    "validator_version": trust_shadow.VALIDATOR_VERSION,
                    "enforcement_error": True, "degraded": True,
                    "enforcement_outcome": enforced.envelope.status.value,
                },
            )
        except Exception:  # never let audit-of-failure fail the turn
            pass
        return enforced


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

    # 6. T3 ENFORCEMENT. The server (not the LLM) is the authority on what this
    # turn may claim. Confidence + evidence status are replaced with
    # server-derived values; unsupported causal wording is corrected with an
    # authoritative note; high-consequence recommendations stay review-gated. The
    # answer text is preserved and annotated — never rewritten. Fail-safe.
    enforced = await _enforce_trust(
        session,
        tenant=tenant,
        belief_ctx=belief_ctx,
        synth=synth,
        tools_consulted=tools_consulted,
        proposed_actions=proposed_actions,
        action_registry=action_registry,
        model_used=model_used,
        request_id=request_id,
    )
    final_answer = synth.answer + (enforced.answer_suffix or "")

    reasoning = ReasoningSummary(
        intent=plan.intent,
        tools_consulted=tools_consulted,
        evidence_used=[e.label for e in evidence],
        key_observations=synth.key_observations,
        uncertainty=synth.uncertainty,
        conclusion=final_answer[:280],
    )

    # 7. persist the assistant message with SAFE, server-enforced metadata only
    assistant_meta = {
        "tools_consulted": tools_consulted,
        "beliefs_consulted": belief_ctx.beliefs_consulted,
        "evidence_status": enforced.evidence_status,
        "confidence": enforced.confidence,
        "trust_status": enforced.envelope.status.value,
        "actions_blocked": [b.model_dump() for b in actions_blocked],
        "approvals_requested": [str(p.approval_id) for p in proposed_actions],
    }
    assistant_msg = await _add_message(
        session, conversation=conversation, role="assistant", content=final_answer, meta=assistant_meta
    )

    # 8. safe audit metadata (never content, tokens/creds, or chain-of-thought)
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
            "evidence_status": enforced.evidence_status,
            "trust_status": enforced.envelope.status.value,
        },
    )

    return AgentResponse(
        conversation_id=conversation.id,
        message_id=assistant_msg.id,
        answer=final_answer,
        evidence_status=enforced.evidence_status,
        confidence=enforced.confidence,
        tools_consulted=tools_consulted,
        evidence=evidence,
        actions_blocked=actions_blocked,
        approval_required=bool(proposed_actions),
        proposed_actions=proposed_actions,
        reasoning_summary=reasoning,
        trust=enforced.envelope,
    )
