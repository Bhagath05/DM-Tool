"""AI Sales Assistant service (Phase 6.5, Slice 5).

The evidence-contract engine. For any CRM subject it (1) resolves + tenant-scopes
the record, (2) GATHERS real evidence from the CRM graph (fields + activities +
tasks + emails + related deals/contacts), (3) applies a GROUNDING GATE — if the
evidence is too thin it returns the honest "Not enough evidence." verdict WITHOUT
calling the LLM (so nothing is hallucinated), and only otherwise (4) calls the
one LLM router with the anti-hallucination contract, then persists the insight
(generated_at / expires_at) and records it in AI history + audit.
"""

from __future__ import annotations

import uuid
from datetime import UTC, datetime, timedelta

from fastapi import HTTPException, status
from sqlalchemy import desc, func, select
from sqlalchemy.ext.asyncio import AsyncSession

from aicmo.llm import get_llm_router
from aicmo.llm.providers.base import LLMMessage
from aicmo.modules.ai_audit import service as ai_audit
from aicmo.modules.audit import service as audit_service
from aicmo.modules.crm import assistant_prompts as prompts
from aicmo.modules.crm.assistant_models import AIInsight
from aicmo.modules.crm.assistant_schemas import SalesInsight
from aicmo.modules.crm.email_models import Email
from aicmo.modules.crm.models import Activity, Company, Contact, Deal, PipelineStage, Task
from aicmo.modules.leads.models import Lead
from aicmo.tenancy.context import TenantContext

INSIGHT_TTL_HOURS = 24
# Minimum real signals (beyond bare identity) required before we call the LLM.
_MIN_SIGNALS = 2

_DEFAULT_KIND = {
    "lead": "lead_intelligence",
    "deal": "deal_intelligence",
    "contact": "contact_intelligence",
    "company": "company_intelligence",
    "email": "email_intelligence",
}
_ALLOWED_KINDS = {
    "lead": {"lead_intelligence", "automation_suggestions"},
    "deal": {"deal_intelligence", "deal_prediction", "deal_coaching", "automation_suggestions"},
    "contact": {"contact_intelligence", "automation_suggestions"},
    "company": {"company_intelligence", "automation_suggestions"},
    "task": {"meeting_intelligence", "call_intelligence", "automation_suggestions"},
    "email": {"email_intelligence", "automation_suggestions"},
}
_MODEL_MAP = {"lead": Lead, "deal": Deal, "contact": Contact, "company": Company, "task": Task, "email": Email}


async def _own(session: AsyncSession, *, tenant: TenantContext, subject_type: str, subject_id: uuid.UUID):
    model = _MODEL_MAP.get(subject_type)
    if model is None:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, f"Unknown subject type {subject_type!r}.")
    row = await session.get(model, subject_id)
    if row is None or row.brand_id != tenant.brand_id:
        raise HTTPException(status.HTTP_404_NOT_FOUND, f"{subject_type.title()} not found.")
    return row


async def _count(session, model, *conds) -> int:
    return int((await session.execute(select(func.count()).select_from(model).where(*conds))).scalar_one())


async def _recent_activities(session, *, brand_id, **link) -> list[Activity]:
    conds = [Activity.brand_id == brand_id]
    for k, v in link.items():
        conds.append(getattr(Activity, k) == v)
    rows = await session.execute(
        select(Activity).where(*conds).order_by(desc(Activity.occurred_at)).limit(8)
    )
    return list(rows.scalars().all())


async def _gather(session, *, tenant, subject_type, subject) -> tuple[list[str], int, list[str]]:
    """Return (context_lines, signal_count, affected_records). signal_count is a
    count of REAL data points beyond bare identity — the grounding gate uses it."""
    brand = tenant.brand_id
    lines: list[str] = []
    affected: list[str] = []
    signals = 0

    if subject_type == "lead":
        lines.append(f"Lead: {subject.name or subject.email}")
        affected.append(f"lead: {subject.name or subject.email}")
        for label, val in (("Company", subject.company), ("Message", subject.message),
                           ("Status", subject.status), ("Source", subject.utm_source)):
            if val:
                lines.append(f"{label}: {val}")
                signals += 1
        if subject.tags:
            lines.append(f"Tags: {', '.join(str(t) for t in subject.tags)}")
            signals += 1
        if subject.notes:
            lines.append(f"Notes: {subject.notes[:300]}")
            signals += 1

    elif subject_type == "deal":
        lines.append(f"Deal: {subject.title} — {subject.value} {subject.currency}")
        affected.append(f"deal: {subject.title}")
        lines.append(f"Status: {subject.status}; probability: {subject.probability}%")
        signals += 1
        if subject.stage_id:
            stage = await session.get(PipelineStage, subject.stage_id)
            if stage is not None:
                lines.append(f"Stage: {stage.name}")
                signals += 1
        age_days = (datetime.now(UTC) - subject.created_at).days if subject.created_at else None
        if age_days is not None:
            lines.append(f"Deal age: {age_days} days")
        if subject.competitors:
            lines.append(f"Competitors: {', '.join(str(c) for c in subject.competitors)}")
            signals += 1
        if subject.lost_reason:
            lines.append(f"Loss reason: {subject.lost_reason}")
            signals += 1
        acts = await _recent_activities(session, brand_id=brand, deal_id=subject.id)
        tasks_open = await _count(session, Task, Task.brand_id == brand, Task.deal_id == subject.id,
                                  Task.status.notin_(("completed", "cancelled")))
        emails = await _count(session, Email, Email.brand_id == brand, Email.deal_id == subject.id)
        if acts:
            lines.append(f"Recent activity: {len(acts)} events; latest '{acts[0].kind}'")
            signals += 1
        if tasks_open:
            lines.append(f"Open tasks: {tasks_open}")
            signals += 1
        if emails:
            lines.append(f"Emails on this deal: {emails}")
            signals += 1

    elif subject_type == "contact":
        lines.append(f"Contact: {subject.name}" + (f" ({subject.title})" if subject.title else ""))
        affected.append(f"contact: {subject.name}")
        for label, val in (("Email", subject.email), ("Notes", subject.notes)):
            if val:
                lines.append(f"{label}: {val[:300]}")
                signals += 1
        acts = await _recent_activities(session, brand_id=brand, contact_id=subject.id)
        emails = await _count(session, Email, Email.brand_id == brand, Email.contact_id == subject.id)
        deals = await _count(session, Deal, Deal.brand_id == brand, Deal.primary_contact_id == subject.id)
        if acts:
            kinds = ", ".join(sorted({a.kind for a in acts}))
            lines.append(f"Activity: {len(acts)} events ({kinds})")
            signals += 1
        if emails:
            lines.append(f"Emails: {emails}")
            signals += 1
        if deals:
            lines.append(f"Deals as primary contact: {deals}")
            signals += 1

    elif subject_type == "company":
        lines.append(f"Company: {subject.name}" + (f", {subject.industry}" if subject.industry else ""))
        affected.append(f"company: {subject.name}")
        contacts = await _count(session, Contact, Contact.brand_id == brand, Contact.company_id == subject.id)
        won = await _count(session, Deal, Deal.brand_id == brand, Deal.company_id == subject.id, Deal.status == "won")
        lost = await _count(session, Deal, Deal.brand_id == brand, Deal.company_id == subject.id, Deal.status == "lost")
        open_ = await _count(session, Deal, Deal.brand_id == brand, Deal.company_id == subject.id, Deal.status == "open")
        acts = await _recent_activities(session, brand_id=brand, company_id=subject.id)
        for label, n in (("Contacts", contacts), ("Won deals", won), ("Lost deals", lost), ("Open deals", open_)):
            if n:
                lines.append(f"{label}: {n}")
                signals += 1
        if subject.annual_revenue:
            lines.append(f"Revenue: {subject.annual_revenue}")
        if acts:
            lines.append(f"Recent activity: {len(acts)} events")
            signals += 1

    elif subject_type == "task":
        lines.append(f"{subject.activity_type.title()}: {subject.title}")
        affected.append(f"task: {subject.title}")
        for label, val in (("Description", subject.description), ("Notes", subject.notes)):
            if val:
                lines.append(f"{label}: {val[:500]}")
                signals += 2  # the notes ARE the meeting/call content — weight them
        if subject.deal_id:
            deal = await session.get(Deal, subject.deal_id)
            if deal is not None and deal.brand_id == brand:
                lines.append(f"Related deal: {deal.title} ({deal.status})")
                signals += 1

    elif subject_type == "email":
        lines.append(f"Email to {subject.to_email}: {subject.subject}")
        affected.append(f"email: {subject.subject}")
        if subject.body:
            lines.append(f"Body: {subject.body[:600]}")
            signals += 1
        lines.append(f"Status: {subject.status}; opened: {subject.opened_at is not None}; "
                     f"replied: {subject.replied_at is not None}")
        if subject.replied_at is not None or subject.opened_at is not None:
            signals += 1

    return lines, signals, affected


def _default_kind(subject_type: str, subject) -> str:
    if subject_type == "task":
        at = getattr(subject, "activity_type", "")
        return "meeting_intelligence" if at in ("meeting", "demo") else \
            "call_intelligence" if at == "call" else "automation_suggestions"
    return _DEFAULT_KIND.get(subject_type, "automation_suggestions")


def _insufficient(tenant, subject_type, subject_id, kind, affected) -> AIInsight:
    return AIInsight(
        id=uuid.uuid4(), organization_id=tenant.organization_id, brand_id=tenant.brand_id,
        subject_type=subject_type, subject_id=subject_id, kind=kind,
        summary="Not enough evidence.", recommendation=None, evidence=[],
        reasoning="This record has too little CRM data to ground a recommendation. "
                  "Log activity, emails, or notes and try again.",
        confidence=0, affected_records=affected, expected_outcome=None,
        insufficient_evidence=True, model=None, generated_by_user_id=tenant.user_id,
        generated_at=datetime.now(UTC), expires_at=None,
    )


async def generate(
    session: AsyncSession, *, tenant: TenantContext, subject_type: str,
    subject_id: uuid.UUID, kind: str | None = None, force: bool = False,
) -> AIInsight:
    subject = await _own(session, tenant=tenant, subject_type=subject_type, subject_id=subject_id)
    kind = kind or _default_kind(subject_type, subject)
    if kind not in _ALLOWED_KINDS.get(subject_type, set()):
        raise HTTPException(status.HTTP_400_BAD_REQUEST, f"Kind {kind!r} not valid for {subject_type}.")

    now = datetime.now(UTC)
    if not force:
        cached = (await session.execute(
            select(AIInsight).where(
                AIInsight.brand_id == tenant.brand_id, AIInsight.subject_type == subject_type,
                AIInsight.subject_id == subject_id, AIInsight.kind == kind,
                AIInsight.insufficient_evidence.is_(False),
                AIInsight.expires_at.isnot(None), AIInsight.expires_at > now,
            ).order_by(desc(AIInsight.generated_at)).limit(1)
        )).scalar_one_or_none()
        if cached is not None:
            return cached

    lines, signals, affected = await _gather(session, tenant=tenant, subject_type=subject_type, subject=subject)

    # Grounding gate — refuse to hallucinate from thin data.
    if signals < _MIN_SIGNALS:
        row = _insufficient(tenant, subject_type, subject_id, kind, affected)
        session.add(row)
        await _audit(session, tenant=tenant, action="crm.insight_insufficient", target_id=row.id,
                     metadata={"subject_type": subject_type, "kind": kind})
        await session.commit()
        await session.refresh(row)
        return row

    result = await get_llm_router().generate(
        response_schema=SalesInsight, system=prompts.SYSTEM,
        messages=[LLMMessage(role="user", content=prompts.build_prompt(kind=kind, context_lines=lines))],
        max_tokens=900,
    )
    data: SalesInsight = result.data
    # Merge the canonical subject into affected_records (dedupe).
    merged_affected = sorted({*affected, *data.affected_records})
    row = AIInsight(
        id=uuid.uuid4(), organization_id=tenant.organization_id, brand_id=tenant.brand_id,
        subject_type=subject_type, subject_id=subject_id, kind=kind,
        summary=data.summary, recommendation=data.recommendation,
        evidence=[e.model_dump() for e in data.evidence], reasoning=data.reasoning,
        confidence=data.confidence, affected_records=merged_affected,
        expected_outcome=data.expected_outcome, insufficient_evidence=False,
        model=getattr(result, "model", None) or "llm", generated_by_user_id=tenant.user_id,
        generated_at=now, expires_at=now + timedelta(hours=INSIGHT_TTL_HOURS),
    )
    session.add(row)
    await ai_audit.record_ai_generation(
        session, tenant=tenant, action_type=f"crm.insight.{kind}", asset_id=row.id,
        model_used=row.model,
    )
    await _audit(session, tenant=tenant, action="crm.insight_generated", target_id=row.id,
                 metadata={"subject_type": subject_type, "kind": kind, "confidence": data.confidence})
    await session.commit()
    await session.refresh(row)
    return row


async def _audit(session, *, tenant, action, target_id, metadata=None):
    await audit_service.record(
        session, organization_id=tenant.organization_id, actor_user_id=tenant.user_uuid,
        action=action, brand_id=tenant.brand_id, target_type="crm", target_id=target_id,
        metadata=metadata or {},
    )


async def list_insights(
    session: AsyncSession, *, tenant: TenantContext, subject_type: str | None = None,
    subject_id: uuid.UUID | None = None, limit: int = 50,
) -> list[AIInsight]:
    conds = [AIInsight.brand_id == tenant.brand_id]
    if subject_type is not None:
        conds.append(AIInsight.subject_type == subject_type)
    if subject_id is not None:
        conds.append(AIInsight.subject_id == subject_id)
    rows = await session.execute(
        select(AIInsight).where(*conds).order_by(desc(AIInsight.generated_at)).limit(limit)
    )
    return list(rows.scalars().all())
