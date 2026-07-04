"""CRM AI sales assistant (Phase 6.5, Part 7) — grounded next-action.

Reuses the one LLM router. Builds context from the deal's REAL fields plus the
linked marketing lead (if any) — never fabricated. Returns the recommendation
contract (recommendation/reason/confidence/expected_result) + risk/opportunity
scores, cached onto the deal.
"""

from __future__ import annotations

from sqlalchemy import select
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


# ---- Slice 2: grounded contact / company summaries ----
async def contact_summary(session: AsyncSession, contact):
    from aicmo.modules.crm.models import Company, Deal, DealContact
    from aicmo.modules.crm.schemas import ContactSummary

    lines = [f"Name: {contact.name}"]
    if contact.title:
        lines.append(f"Title: {contact.title}")
    if contact.email:
        lines.append(f"Email: {contact.email}")
    if contact.linkedin:
        lines.append("Has LinkedIn on file")
    if contact.notes:
        lines.append(f"Notes: {contact.notes[:200]}")
    if contact.tags:
        lines.append(f"Tags: {', '.join(str(t) for t in contact.tags)}")
    if contact.company_id:
        company = await session.get(Company, contact.company_id)
        if company is not None and company.brand_id == contact.brand_id:
            lines.append(f"Company: {company.name}" + (f" ({company.industry})" if company.industry else ""))
    deals = (await session.execute(
        select(Deal).join(DealContact, DealContact.deal_id == Deal.id, isouter=True).where(
            Deal.brand_id == contact.brand_id,
            (Deal.primary_contact_id == contact.id) | (DealContact.contact_id == contact.id),
        ).distinct()
    )).scalars().all()
    if deals:
        lines.append(f"Involved in {len(deals)} deal(s); statuses: "
                     + ", ".join(sorted({d.status for d in deals})))

    result = await get_llm_router().generate(
        response_schema=ContactSummary, system=prompts.ENTITY_SUMMARY_SYSTEM,
        messages=[LLMMessage(role="user", content=prompts.build_entity_summary_prompt(
            label="CONTACT", context_lines=lines))],
        max_tokens=600,
    )
    return result.data


async def company_summary(session: AsyncSession, company):
    from aicmo.modules.crm.models import Contact, Deal
    from aicmo.modules.crm.schemas import CompanySummary

    lines = [f"Name: {company.name}"]
    for label, val in (
        ("Industry", company.industry), ("Website", company.website),
        ("Employees", company.employees), ("Revenue", company.annual_revenue),
        ("Location", company.address), ("Timezone", company.timezone),
    ):
        if val:
            lines.append(f"{label}: {val}")
    if company.tech_stack:
        lines.append(f"Tech stack: {', '.join(str(t) for t in company.tech_stack)}")
    contacts = (await session.execute(
        select(Contact).where(Contact.brand_id == company.brand_id, Contact.company_id == company.id)
    )).scalars().all()
    if contacts:
        lines.append(f"{len(contacts)} contact(s) on file")
    deals = (await session.execute(
        select(Deal).where(Deal.brand_id == company.brand_id, Deal.company_id == company.id)
    )).scalars().all()
    if deals:
        won = sum(1 for d in deals if d.status == "won")
        lost = sum(1 for d in deals if d.status == "lost")
        open_ = sum(1 for d in deals if d.status == "open")
        lines.append(f"Deals: {open_} open, {won} won, {lost} lost")

    result = await get_llm_router().generate(
        response_schema=CompanySummary, system=prompts.ENTITY_SUMMARY_SYSTEM,
        messages=[LLMMessage(role="user", content=prompts.build_entity_summary_prompt(
            label="COMPANY", context_lines=lines))],
        max_tokens=650,
    )
    return result.data


async def task_suggestion(session: AsyncSession, task):
    """Grounded suggestion for a task — priority, due date, next step, risk —
    from the task + its linked deal/contact/company real fields only."""
    from aicmo.modules.crm.models import Company, Contact, Deal
    from aicmo.modules.crm.tasks_schemas import TaskSuggestion

    lines = [f"Task: {task.title}", f"Type: {task.activity_type}", f"Status: {task.status}",
             f"Priority: {task.priority}"]
    if task.due_at:
        lines.append(f"Due: {task.due_at.isoformat()}")
    if task.description:
        lines.append(f"Description: {task.description[:200]}")
    if task.deal_id:
        deal = await session.get(Deal, task.deal_id)
        if deal is not None and deal.brand_id == task.brand_id:
            lines.append(f"Deal: {deal.title} — {deal.value} {deal.currency}, "
                         f"status {deal.status}, prob {deal.probability}%")
    if task.contact_id:
        c = await session.get(Contact, task.contact_id)
        if c is not None and c.brand_id == task.brand_id:
            lines.append(f"Contact: {c.name}" + (f" ({c.title})" if c.title else ""))
    if task.company_id:
        co = await session.get(Company, task.company_id)
        if co is not None and co.brand_id == task.brand_id:
            lines.append(f"Company: {co.name}" + (f", {co.industry}" if co.industry else ""))

    result = await get_llm_router().generate(
        response_schema=TaskSuggestion, system=prompts.TASK_SUGGESTION_SYSTEM,
        messages=[LLMMessage(role="user", content=prompts.build_task_suggestion_prompt(
            context_lines=lines))],
        max_tokens=600,
    )
    return result.data
