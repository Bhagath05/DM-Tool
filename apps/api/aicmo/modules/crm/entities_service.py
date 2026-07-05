"""CRM entities service (Phase 6.5, Slice 2) — companies, contacts, activities.

Extends the CRM core with the people/orgs graph: Company ↔ Contacts ↔ Deals ↔
Activities. Everything brand-scoped + audited. Merge reassigns every association
(deals, activities, links) onto the survivor before deleting the duplicate.
Duplicate detection is deterministic (email / domain / name) — never guessed.
Health score is DERIVED from real signals (pipeline, wins, activity recency),
never fabricated.
"""

from __future__ import annotations

import uuid
from datetime import UTC, datetime
from urllib.parse import urlparse

from fastapi import HTTPException, status
from sqlalchemy import delete, func, or_, select, update
from sqlalchemy.ext.asyncio import AsyncSession

from aicmo.modules.crm import ai
from aicmo.modules.crm._shared import record_crm_audit as _audit
from aicmo.modules.crm.models import (
    Activity,
    Company,
    Contact,
    Deal,
    DealContact,
)
from aicmo.modules.crm.schemas import (
    ActivityCreate,
    CompanyCreate,
    CompanyUpdate,
    ContactCreate,
    ContactUpdate,
    DuplicateMatch,
)
from aicmo.tenancy.context import TenantContext


def _domain(website: str | None) -> str | None:
    if not website:
        return None
    raw = website.strip().lower()
    if "://" not in raw:
        raw = "http://" + raw
    host = urlparse(raw).netloc or ""
    return host[4:] if host.startswith("www.") else host or None


# =====================================================================
#  Companies
# =====================================================================
async def _owned_company(session: AsyncSession, *, tenant: TenantContext, company_id: uuid.UUID) -> Company:
    row = await session.get(Company, company_id)
    if row is None or row.brand_id != tenant.brand_id:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Company not found.")
    return row


async def create_company(session: AsyncSession, *, tenant: TenantContext, payload: CompanyCreate) -> Company:
    row = Company(
        id=uuid.uuid4(), organization_id=tenant.organization_id, brand_id=tenant.brand_id,
        name=payload.name, website=payload.website, domain=_domain(payload.website),
        industry=payload.industry, annual_revenue=payload.annual_revenue, employees=payload.employees,
        tech_stack=payload.tech_stack, social_links=payload.social_links, address=payload.address,
        timezone=payload.timezone, owner_user_id=payload.owner_user_id or tenant.user_id,
        tags=payload.tags, custom_fields=payload.custom_fields,
    )
    session.add(row)
    await _audit(session, tenant=tenant, action="crm.company_created", target_id=row.id,
                 metadata={"name": payload.name})
    await session.commit()
    await session.refresh(row)
    return row


async def list_companies(
    session: AsyncSession, *, tenant: TenantContext, q: str | None = None,
    industry: str | None = None, include_archived: bool = False,
    limit: int = 100, offset: int = 0,
) -> tuple[list[Company], int]:
    conds = [Company.brand_id == tenant.brand_id]
    if not include_archived:
        conds.append(Company.archived.is_(False))
    if industry:
        conds.append(Company.industry == industry)
    if q:
        like = f"%{q.strip()}%"
        conds.append(or_(Company.name.ilike(like), Company.domain.ilike(like)))
    total = (await session.execute(select(func.count()).select_from(Company).where(*conds))).scalar_one()
    rows = await session.execute(
        select(Company).where(*conds).order_by(Company.name).limit(limit).offset(offset)
    )
    return list(rows.scalars().all()), int(total)


async def update_company(
    session: AsyncSession, *, tenant: TenantContext, company_id: uuid.UUID, payload: CompanyUpdate
) -> Company:
    row = await _owned_company(session, tenant=tenant, company_id=company_id)
    data = payload.model_dump(exclude_unset=True)
    if "website" in data:
        row.domain = _domain(data.get("website"))
    for k, v in data.items():
        setattr(row, k, v)
    await session.commit()
    await session.refresh(row)
    return row


async def delete_company(session: AsyncSession, *, tenant: TenantContext, company_id: uuid.UUID) -> None:
    row = await _owned_company(session, tenant=tenant, company_id=company_id)
    await session.delete(row)  # contacts.company_id / deals.company_id → SET NULL
    await session.commit()


async def company_duplicates(
    session: AsyncSession, *, tenant: TenantContext, company_id: uuid.UUID
) -> list[DuplicateMatch]:
    row = await _owned_company(session, tenant=tenant, company_id=company_id)
    matches: dict[uuid.UUID, DuplicateMatch] = {}
    if row.domain:
        for c in (await session.execute(
            select(Company).where(
                Company.brand_id == tenant.brand_id, Company.id != company_id,
                Company.archived.is_(False), func.lower(Company.domain) == row.domain.lower(),
            )
        )).scalars():
            matches[c.id] = DuplicateMatch(id=c.id, name=c.name, reason="same domain")
    for c in (await session.execute(
        select(Company).where(
            Company.brand_id == tenant.brand_id, Company.id != company_id,
            Company.archived.is_(False), func.lower(Company.name) == row.name.lower(),
        )
    )).scalars():
        matches.setdefault(c.id, DuplicateMatch(id=c.id, name=c.name, reason="same name"))
    return list(matches.values())


async def merge_companies(
    session: AsyncSession, *, tenant: TenantContext, survivor_id: uuid.UUID, duplicate_id: uuid.UUID
) -> Company:
    if survivor_id == duplicate_id:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, "Cannot merge a company into itself.")
    survivor = await _owned_company(session, tenant=tenant, company_id=survivor_id)
    dup = await _owned_company(session, tenant=tenant, company_id=duplicate_id)

    # Reassign every association onto the survivor.
    await session.execute(update(Contact).where(Contact.company_id == dup.id).values(company_id=survivor.id))
    await session.execute(update(Deal).where(Deal.company_id == dup.id).values(company_id=survivor.id))
    await session.execute(update(Activity).where(Activity.company_id == dup.id).values(company_id=survivor.id))

    # Fill survivor blanks + union list/dict fields (survivor wins on conflict).
    for attr in ("website", "domain", "industry", "annual_revenue", "employees", "address", "timezone"):
        if getattr(survivor, attr) in (None, "") and getattr(dup, attr) not in (None, ""):
            setattr(survivor, attr, getattr(dup, attr))
    survivor.tags = sorted({*survivor.tags, *dup.tags})
    survivor.tech_stack = sorted({*survivor.tech_stack, *dup.tech_stack})
    survivor.social_links = {**dup.social_links, **survivor.social_links}
    survivor.custom_fields = {**dup.custom_fields, **survivor.custom_fields}

    await session.delete(dup)
    await _audit(session, tenant=tenant, action="crm.company_merged", target_id=survivor.id,
                 metadata={"merged": str(duplicate_id)})
    await session.commit()
    await session.refresh(survivor)
    return survivor


async def company_health(session: AsyncSession, *, tenant: TenantContext, company_id: uuid.UUID) -> int:
    """Deterministic 0-100 health from REAL signals — open pipeline, win/loss
    balance, contact coverage, and activity recency. Never fabricated."""
    await _owned_company(session, tenant=tenant, company_id=company_id)
    base = 50.0

    async def _count(model, *conds) -> int:
        return int((await session.execute(select(func.count()).select_from(model).where(*conds))).scalar_one())

    won = await _count(Deal, Deal.brand_id == tenant.brand_id, Deal.company_id == company_id, Deal.status == "won")
    lost = await _count(Deal, Deal.brand_id == tenant.brand_id, Deal.company_id == company_id, Deal.status == "lost")
    open_deals = await _count(Deal, Deal.brand_id == tenant.brand_id, Deal.company_id == company_id, Deal.status == "open")
    contacts = await _count(Contact, Contact.brand_id == tenant.brand_id, Contact.company_id == company_id, Contact.archived.is_(False))

    score = base + won * 10 - lost * 8 + min(open_deals, 5) * 4 + min(contacts, 5) * 2

    last_activity = (await session.execute(
        select(func.max(Activity.occurred_at)).where(
            Activity.brand_id == tenant.brand_id, Activity.company_id == company_id
        )
    )).scalar_one()
    if last_activity is not None:
        days = (datetime.now(UTC) - last_activity).days
        score += 10 if days <= 7 else 5 if days <= 30 else -10 if days > 90 else 0
    else:
        score -= 5  # no logged touch yet

    final = max(0, min(100, round(score)))
    row = await session.get(Company, company_id)
    if row is not None:
        row.health_score = final
        row.health_computed_at = datetime.now(UTC)
        await session.commit()
    return final


# =====================================================================
#  Contacts
# =====================================================================
async def _owned_contact(session: AsyncSession, *, tenant: TenantContext, contact_id: uuid.UUID) -> Contact:
    row = await session.get(Contact, contact_id)
    if row is None or row.brand_id != tenant.brand_id:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Contact not found.")
    return row


async def create_contact(session: AsyncSession, *, tenant: TenantContext, payload: ContactCreate) -> Contact:
    if payload.company_id is not None:
        await _owned_company(session, tenant=tenant, company_id=payload.company_id)
    row = Contact(
        id=uuid.uuid4(), organization_id=tenant.organization_id, brand_id=tenant.brand_id,
        company_id=payload.company_id, lead_id=payload.lead_id, name=payload.name, title=payload.title,
        email=payload.email, phone=payload.phone, linkedin=payload.linkedin,
        owner_user_id=payload.owner_user_id or tenant.user_id, tags=payload.tags,
        custom_fields=payload.custom_fields, notes=payload.notes,
    )
    session.add(row)
    # Slice 3 automation — auto-draft an intro follow-up (staged, atomic).
    from aicmo.modules.crm import automation

    automation.on_contact_created(session, tenant=tenant, contact=row)
    await _audit(session, tenant=tenant, action="crm.contact_created", target_id=row.id,
                 metadata={"name": payload.name})
    await session.commit()
    await session.refresh(row)
    return row


async def list_contacts(
    session: AsyncSession, *, tenant: TenantContext, q: str | None = None,
    company_id: uuid.UUID | None = None, include_archived: bool = False,
    limit: int = 100, offset: int = 0,
) -> tuple[list[Contact], int]:
    conds = [Contact.brand_id == tenant.brand_id]
    if not include_archived:
        conds.append(Contact.archived.is_(False))
    if company_id is not None:
        conds.append(Contact.company_id == company_id)
    if q:
        like = f"%{q.strip()}%"
        conds.append(or_(Contact.name.ilike(like), Contact.email.ilike(like)))
    total = (await session.execute(select(func.count()).select_from(Contact).where(*conds))).scalar_one()
    rows = await session.execute(
        select(Contact).where(*conds).order_by(Contact.name).limit(limit).offset(offset)
    )
    return list(rows.scalars().all()), int(total)


async def update_contact(
    session: AsyncSession, *, tenant: TenantContext, contact_id: uuid.UUID, payload: ContactUpdate
) -> Contact:
    row = await _owned_contact(session, tenant=tenant, contact_id=contact_id)
    data = payload.model_dump(exclude_unset=True)
    if data.get("company_id") is not None:
        await _owned_company(session, tenant=tenant, company_id=data["company_id"])
    for k, v in data.items():
        setattr(row, k, v)
    await session.commit()
    await session.refresh(row)
    return row


async def delete_contact(session: AsyncSession, *, tenant: TenantContext, contact_id: uuid.UUID) -> None:
    row = await _owned_contact(session, tenant=tenant, contact_id=contact_id)
    await session.delete(row)
    await session.commit()


async def contact_duplicates(
    session: AsyncSession, *, tenant: TenantContext, contact_id: uuid.UUID
) -> list[DuplicateMatch]:
    row = await _owned_contact(session, tenant=tenant, contact_id=contact_id)
    matches: dict[uuid.UUID, DuplicateMatch] = {}
    if row.email:
        for c in (await session.execute(
            select(Contact).where(
                Contact.brand_id == tenant.brand_id, Contact.id != contact_id,
                Contact.archived.is_(False), func.lower(Contact.email) == row.email.lower(),
            )
        )).scalars():
            matches[c.id] = DuplicateMatch(id=c.id, name=c.name, reason="same email")
    name_conds = [
        Contact.brand_id == tenant.brand_id, Contact.id != contact_id,
        Contact.archived.is_(False), func.lower(Contact.name) == row.name.lower(),
    ]
    if row.company_id is not None:
        name_conds.append(Contact.company_id == row.company_id)
    for c in (await session.execute(select(Contact).where(*name_conds))).scalars():
        matches.setdefault(c.id, DuplicateMatch(id=c.id, name=c.name, reason="same name"))
    return list(matches.values())


async def generate_contact_summary(
    session: AsyncSession, *, tenant: TenantContext, contact_id: uuid.UUID
) -> Contact:
    row = await _owned_contact(session, tenant=tenant, contact_id=contact_id)
    summary = await ai.contact_summary(session, row)
    row.ai_summary = summary.model_dump()
    row.ai_generated_at = datetime.now(UTC)
    await _audit(session, tenant=tenant, action="crm.contact_summary", target_id=row.id,
                 metadata={"confidence": summary.confidence})
    await session.commit()
    await session.refresh(row)
    return row


async def generate_company_summary(
    session: AsyncSession, *, tenant: TenantContext, company_id: uuid.UUID
) -> Company:
    row = await _owned_company(session, tenant=tenant, company_id=company_id)
    summary = await ai.company_summary(session, row)
    row.ai_summary = summary.model_dump()
    row.ai_generated_at = datetime.now(UTC)
    await _audit(session, tenant=tenant, action="crm.company_summary", target_id=row.id,
                 metadata={"confidence": summary.confidence})
    await session.commit()
    await session.refresh(row)
    return row


async def merge_contacts(
    session: AsyncSession, *, tenant: TenantContext, survivor_id: uuid.UUID, duplicate_id: uuid.UUID
) -> Contact:
    if survivor_id == duplicate_id:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, "Cannot merge a contact into itself.")
    survivor = await _owned_contact(session, tenant=tenant, contact_id=survivor_id)
    dup = await _owned_contact(session, tenant=tenant, contact_id=duplicate_id)

    # Deal links — move dup's links to survivor, skipping deals already linked to
    # survivor (composite PK would collide), then drop the leftovers.
    await session.execute(
        update(DealContact).where(
            DealContact.contact_id == dup.id,
            DealContact.deal_id.notin_(
                select(DealContact.deal_id).where(DealContact.contact_id == survivor.id)
            ),
        ).values(contact_id=survivor.id)
    )
    await session.execute(delete(DealContact).where(DealContact.contact_id == dup.id))
    await session.execute(update(Deal).where(Deal.primary_contact_id == dup.id).values(primary_contact_id=survivor.id))
    await session.execute(update(Activity).where(Activity.contact_id == dup.id).values(contact_id=survivor.id))

    for attr in ("title", "email", "phone", "linkedin", "company_id", "notes"):
        if getattr(survivor, attr) in (None, "") and getattr(dup, attr) not in (None, ""):
            setattr(survivor, attr, getattr(dup, attr))
    survivor.tags = sorted({*survivor.tags, *dup.tags})
    survivor.custom_fields = {**dup.custom_fields, **survivor.custom_fields}

    await session.delete(dup)
    await _audit(session, tenant=tenant, action="crm.contact_merged", target_id=survivor.id,
                 metadata={"merged": str(duplicate_id)})
    await session.commit()
    await session.refresh(survivor)
    return survivor


# =====================================================================
#  Activities (timeline) + deal ↔ contact links
# =====================================================================
async def create_activity(session: AsyncSession, *, tenant: TenantContext, payload: ActivityCreate) -> Activity:
    if payload.contact_id is not None:
        await _owned_contact(session, tenant=tenant, contact_id=payload.contact_id)
    if payload.company_id is not None:
        await _owned_company(session, tenant=tenant, company_id=payload.company_id)
    if payload.deal_id is not None:
        deal = await session.get(Deal, payload.deal_id)
        if deal is None or deal.brand_id != tenant.brand_id:
            raise HTTPException(status.HTTP_404_NOT_FOUND, "Deal not found.")
    row = Activity(
        id=uuid.uuid4(), organization_id=tenant.organization_id, brand_id=tenant.brand_id,
        kind=payload.kind, subject=payload.subject, body=payload.body, contact_id=payload.contact_id,
        company_id=payload.company_id, deal_id=payload.deal_id,
        occurred_at=payload.occurred_at or datetime.now(UTC), actor_user_id=tenant.user_id,
        meta=payload.meta,
    )
    session.add(row)
    await session.commit()
    await session.refresh(row)
    return row


async def list_activities(
    session: AsyncSession, *, tenant: TenantContext,
    contact_id: uuid.UUID | None = None, company_id: uuid.UUID | None = None,
    deal_id: uuid.UUID | None = None, limit: int = 100,
) -> list[Activity]:
    conds = [Activity.brand_id == tenant.brand_id]
    if contact_id is not None:
        conds.append(Activity.contact_id == contact_id)
    if company_id is not None:
        conds.append(Activity.company_id == company_id)
    if deal_id is not None:
        conds.append(Activity.deal_id == deal_id)
    rows = await session.execute(
        select(Activity).where(*conds).order_by(Activity.occurred_at.desc()).limit(limit)
    )
    return list(rows.scalars().all())


async def link_contact_to_deal(
    session: AsyncSession, *, tenant: TenantContext, deal_id: uuid.UUID, contact_id: uuid.UUID, role: str | None
) -> None:
    deal = await session.get(Deal, deal_id)
    if deal is None or deal.brand_id != tenant.brand_id:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Deal not found.")
    await _owned_contact(session, tenant=tenant, contact_id=contact_id)
    existing = await session.get(DealContact, {"deal_id": deal_id, "contact_id": contact_id})
    if existing is None:
        session.add(DealContact(
            organization_id=tenant.organization_id, brand_id=tenant.brand_id,
            deal_id=deal_id, contact_id=contact_id, role=role,
        ))
        await session.commit()


async def deal_contacts(session: AsyncSession, *, tenant: TenantContext, deal_id: uuid.UUID) -> list[Contact]:
    deal = await session.get(Deal, deal_id)
    if deal is None or deal.brand_id != tenant.brand_id:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Deal not found.")
    rows = await session.execute(
        select(Contact).join(DealContact, DealContact.contact_id == Contact.id)
        .where(DealContact.deal_id == deal_id, Contact.brand_id == tenant.brand_id)
    )
    return list(rows.scalars().all())


# ---- detail composers (relationships) ----
async def company_detail(session: AsyncSession, *, tenant: TenantContext, company_id: uuid.UUID):
    company = await _owned_company(session, tenant=tenant, company_id=company_id)
    contacts = (await session.execute(
        select(Contact).where(
            Contact.brand_id == tenant.brand_id, Contact.company_id == company_id,
            Contact.archived.is_(False),
        ).order_by(Contact.name)
    )).scalars().all()
    deals = (await session.execute(
        select(Deal).where(Deal.brand_id == tenant.brand_id, Deal.company_id == company_id)
        .order_by(Deal.updated_at.desc())
    )).scalars().all()
    return company, list(contacts), list(deals)


async def contact_detail(session: AsyncSession, *, tenant: TenantContext, contact_id: uuid.UUID):
    contact = await _owned_contact(session, tenant=tenant, contact_id=contact_id)
    company = await session.get(Company, contact.company_id) if contact.company_id else None
    deals = (await session.execute(
        select(Deal).join(DealContact, DealContact.deal_id == Deal.id, isouter=True)
        .where(
            Deal.brand_id == tenant.brand_id,
            or_(Deal.primary_contact_id == contact_id, DealContact.contact_id == contact_id),
        ).order_by(Deal.updated_at.desc()).distinct()
    )).scalars().all()
    return contact, company, list(deals)
