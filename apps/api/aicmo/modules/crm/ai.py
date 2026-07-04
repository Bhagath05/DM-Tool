"""CRM AI sales assistant (Phase 6.5, Part 7) — grounded next-action.

Reuses the one LLM router. Builds context from the deal's REAL fields plus the
linked marketing lead (if any) — never fabricated. Returns the recommendation
contract (recommendation/reason/confidence/expected_result) + risk/opportunity
scores, cached onto the deal.
"""

from __future__ import annotations

from sqlalchemy.ext.asyncio import AsyncSession

from aicmo.llm import get_llm_router
from aicmo.llm.providers.base import LLMMessage
from aicmo.modules.crm import prompts
from aicmo.modules.crm.models import Deal, PipelineStage
from aicmo.modules.crm.schemas import DealNextAction
from aicmo.modules.leads.models import Lead


async def _context_lines(session: AsyncSession, deal: Deal) -> list[str]:
    lines: list[str] = [f"Title: {deal.title}"]
    if deal.company:
        lines.append(f"Company: {deal.company}")
    if deal.contact_name or deal.contact_email:
        lines.append(f"Contact: {deal.contact_name or ''} {deal.contact_email or ''}".strip())
    lines.append(f"Value: {deal.value} {deal.currency}")
    lines.append(f"Status: {deal.status}; priority: {deal.priority}")
    if deal.probability is not None:
        lines.append(f"Win probability: {deal.probability}%")
    if deal.expected_close_date:
        lines.append(f"Expected close: {deal.expected_close_date.isoformat()}")
    if deal.competitors:
        lines.append(f"Competitors: {', '.join(str(c) for c in deal.competitors)}")
    if deal.products:
        lines.append(f"Products: {len(deal.products)} line item(s)")
    if deal.source:
        lines.append(f"Source: {deal.source}")

    # Stage context (grounds 'where in the pipeline').
    if deal.stage_id is not None:
        stage = await session.get(PipelineStage, deal.stage_id)
        if stage is not None:
            lines.append(f"Stage: {stage.name} (default prob {stage.probability}%)")

    # Linked marketing lead — reuse its real intent signals, never invent.
    if deal.lead_id is not None:
        lead = await session.get(Lead, deal.lead_id)
        if lead is not None and lead.brand_id == deal.brand_id:
            if lead.message:
                lines.append(f"Lead message: {lead.message[:200]}")
            if lead.utm_source or lead.utm_campaign:
                lines.append(f"Lead source: {lead.utm_source or ''}/{lead.utm_campaign or ''}")
            if lead.tags:
                lines.append(f"Lead tags: {', '.join(str(t) for t in lead.tags)}")
    return lines


async def next_action(session: AsyncSession, deal: Deal) -> DealNextAction:
    """Grounded next-action for a deal. Raises nothing — the router validates
    the structured output against DealNextAction."""
    result = await get_llm_router().generate(
        response_schema=DealNextAction,
        system=prompts.SYSTEM_PROMPT,
        messages=[
            LLMMessage(role="user", content=prompts.build_next_action_prompt(
                context_lines=await _context_lines(session, deal),
            )),
        ],
        max_tokens=700,
    )
    return result.data
