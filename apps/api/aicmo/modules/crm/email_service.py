"""CRM Email Platform service (Phase 6.5, Slice 4).

Templates (+ immutable version history + folders + variable render), sequences
(steps with delays + stop/wait conditions), enrollments (lifecycle + a
brand-scoped tick that advances due enrollments), sending (via the provider
abstraction — stub records, never fabricates delivery), and tracking (open /
click / reply / bounce / unsubscribe by unguessable token). Every sent email
writes a crm_activities row (kind=email) — reuse, no duplicate timeline.
"""

from __future__ import annotations

import re
import secrets
import uuid
from datetime import UTC, datetime, timedelta

from fastapi import HTTPException, status
from sqlalchemy import func, or_, select

from aicmo.modules.audit import service as audit_service
from aicmo.modules.crm import email_providers
from aicmo.modules.crm.email_models import (
    Email,
    EmailEnrollment,
    EmailFolder,
    EmailSequence,
    EmailSequenceStep,
    EmailTemplate,
    EmailTemplateVersion,
)
from aicmo.modules.crm.email_schemas import (
    SequenceCreate,
    TemplateCreate,
    TemplateUpdate,
)
from aicmo.modules.crm.models import Activity, Contact

_PLACEHOLDER = re.compile(r"\{\{\s*([\w.]+)\s*\}\}")


async def _audit(session, *, tenant, action, target_id, metadata=None):
    await audit_service.record(
        session, organization_id=tenant.organization_id, actor_user_id=tenant.user_uuid,
        action=action, brand_id=tenant.brand_id, target_type="crm", target_id=target_id,
        metadata=metadata or {},
    )


# =====================================================================
#  Folders
# =====================================================================
async def create_folder(session, *, tenant, name, parent_id=None) -> EmailFolder:
    row = EmailFolder(
        id=uuid.uuid4(), organization_id=tenant.organization_id, brand_id=tenant.brand_id,
        name=name, parent_id=parent_id, created_by_user_id=tenant.user_id,
    )
    session.add(row)
    await session.commit()
    await session.refresh(row)
    return row


async def list_folders(session, *, tenant) -> list[EmailFolder]:
    rows = await session.execute(
        select(EmailFolder).where(EmailFolder.brand_id == tenant.brand_id).order_by(EmailFolder.name)
    )
    return list(rows.scalars().all())


# =====================================================================
#  Templates (+ version history + render)
# =====================================================================
async def _owned_template(session, *, tenant, template_id) -> EmailTemplate:
    row = await session.get(EmailTemplate, template_id)
    if row is None or row.brand_id != tenant.brand_id:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Template not found.")
    return row


def _snapshot(tenant, tpl: EmailTemplate, edit_summary: str | None) -> EmailTemplateVersion:
    return EmailTemplateVersion(
        id=uuid.uuid4(), organization_id=tenant.organization_id, brand_id=tenant.brand_id,
        template_id=tpl.id, version_no=tpl.current_version, subject=tpl.subject, body=tpl.body,
        variables=tpl.variables, edit_summary=edit_summary, created_by_user_id=tenant.user_id,
    )


async def create_template(session, *, tenant, payload: TemplateCreate) -> EmailTemplate:
    tpl = EmailTemplate(
        id=uuid.uuid4(), organization_id=tenant.organization_id, brand_id=tenant.brand_id,
        name=payload.name, category=payload.category, subject=payload.subject, body=payload.body,
        variables=payload.variables, folder_id=payload.folder_id, current_version=1,
        created_by_user_id=tenant.user_id,
    )
    session.add(tpl)
    session.add(_snapshot(tenant, tpl, "Initial version."))
    await _audit(session, tenant=tenant, action="crm.email_template_created", target_id=tpl.id,
                 metadata={"name": payload.name, "category": payload.category})
    await session.commit()
    await session.refresh(tpl)
    return tpl


async def list_templates(session, *, tenant, category=None, folder_id=None, q=None,
                         active_only=False, limit=100, offset=0) -> tuple[list[EmailTemplate], int]:
    conds = [EmailTemplate.brand_id == tenant.brand_id]
    if category:
        conds.append(EmailTemplate.category == category)
    if folder_id is not None:
        conds.append(EmailTemplate.folder_id == folder_id)
    if active_only:
        conds.append(EmailTemplate.is_active.is_(True))
    if q:
        like = f"%{q.strip()}%"
        conds.append(or_(EmailTemplate.name.ilike(like), EmailTemplate.subject.ilike(like)))
    total = (await session.execute(select(func.count()).select_from(EmailTemplate).where(*conds))).scalar_one()
    rows = await session.execute(
        select(EmailTemplate).where(*conds).order_by(EmailTemplate.updated_at.desc()).limit(limit).offset(offset)
    )
    return list(rows.scalars().all()), int(total)


async def get_template(session, *, tenant, template_id) -> EmailTemplate:
    return await _owned_template(session, tenant=tenant, template_id=template_id)


async def update_template(session, *, tenant, template_id, payload: TemplateUpdate) -> EmailTemplate:
    tpl = await _owned_template(session, tenant=tenant, template_id=template_id)
    data = payload.model_dump(exclude_unset=True, exclude={"edit_summary"})
    content_changed = any(k in data for k in ("subject", "body", "variables"))
    for k, v in data.items():
        setattr(tpl, k, v)
    if content_changed:
        tpl.current_version += 1
        session.add(_snapshot(tenant, tpl, payload.edit_summary))
    await session.commit()
    await session.refresh(tpl)
    return tpl


async def delete_template(session, *, tenant, template_id) -> None:
    tpl = await _owned_template(session, tenant=tenant, template_id=template_id)
    await session.delete(tpl)
    await session.commit()


async def template_versions(session, *, tenant, template_id) -> list[EmailTemplateVersion]:
    await _owned_template(session, tenant=tenant, template_id=template_id)
    rows = await session.execute(
        select(EmailTemplateVersion).where(EmailTemplateVersion.template_id == template_id)
        .order_by(EmailTemplateVersion.version_no.desc())
    )
    return list(rows.scalars().all())


def render(subject: str, body: str, variables: dict[str, str]) -> tuple[str, str, list[str]]:
    """Substitute {{var}} placeholders. Unknown placeholders are LEFT INTACT
    and reported (never fabricated with made-up values)."""
    def sub(text: str) -> str:
        return _PLACEHOLDER.sub(lambda m: variables.get(m.group(1), m.group(0)), text)
    rendered_subject, rendered_body = sub(subject), sub(body)
    unresolved = sorted(set(_PLACEHOLDER.findall(rendered_subject + " " + rendered_body)))
    return rendered_subject, rendered_body, unresolved


async def render_template(session, *, tenant, template_id, variables: dict[str, str],
                          contact_id=None) -> tuple[str, str, list[str]]:
    tpl = await _owned_template(session, tenant=tenant, template_id=template_id)
    merged = dict(variables)
    if contact_id is not None:
        c = await session.get(Contact, contact_id)
        if c is not None and c.brand_id == tenant.brand_id:
            merged.setdefault("contact_name", c.name)
            merged.setdefault("contact_first_name", c.name.split(" ")[0])
            if c.email:
                merged.setdefault("contact_email", c.email)
            if c.title:
                merged.setdefault("contact_title", c.title)
    return render(tpl.subject, tpl.body, merged)


# =====================================================================
#  Sequences
# =====================================================================
async def _owned_sequence(session, *, tenant, sequence_id) -> EmailSequence:
    row = await session.get(EmailSequence, sequence_id)
    if row is None or row.brand_id != tenant.brand_id:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Sequence not found.")
    return row


async def _steps(session, sequence_id) -> list[EmailSequenceStep]:
    rows = await session.execute(
        select(EmailSequenceStep).where(EmailSequenceStep.sequence_id == sequence_id)
        .order_by(EmailSequenceStep.position)
    )
    return list(rows.scalars().all())


async def create_sequence(session, *, tenant, payload: SequenceCreate) -> tuple[EmailSequence, list]:
    seq = EmailSequence(
        id=uuid.uuid4(), organization_id=tenant.organization_id, brand_id=tenant.brand_id,
        name=payload.name, description=payload.description, created_by_user_id=tenant.user_id,
    )
    session.add(seq)
    for i, step in enumerate(payload.steps):
        session.add(EmailSequenceStep(
            id=uuid.uuid4(), organization_id=tenant.organization_id, brand_id=tenant.brand_id,
            sequence_id=seq.id, position=i, template_id=step.template_id,
            delay_hours=step.delay_hours, wait_for_open=step.wait_for_open, stop_on_reply=step.stop_on_reply,
        ))
    await _audit(session, tenant=tenant, action="crm.email_sequence_created", target_id=seq.id,
                 metadata={"name": payload.name, "steps": len(payload.steps)})
    await session.commit()
    await session.refresh(seq)
    return seq, await _steps(session, seq.id)


async def list_sequences(session, *, tenant) -> list[tuple[EmailSequence, list]]:
    rows = await session.execute(
        select(EmailSequence).where(EmailSequence.brand_id == tenant.brand_id).order_by(EmailSequence.created_at.desc())
    )
    seqs = list(rows.scalars().all())
    return [(s, await _steps(session, s.id)) for s in seqs]


async def get_sequence(session, *, tenant, sequence_id) -> tuple[EmailSequence, list]:
    seq = await _owned_sequence(session, tenant=tenant, sequence_id=sequence_id)
    return seq, await _steps(session, seq.id)


async def update_sequence(session, *, tenant, sequence_id, name=None, description=None, seq_status=None):
    seq = await _owned_sequence(session, tenant=tenant, sequence_id=sequence_id)
    if name is not None:
        seq.name = name
    if description is not None:
        seq.description = description
    if seq_status is not None:
        seq.status = seq_status
    await session.commit()
    await session.refresh(seq)
    return seq, await _steps(session, seq.id)


# =====================================================================
#  Enrollments (lifecycle + tick)
# =====================================================================
async def _owned_enrollment(session, *, tenant, enrollment_id) -> EmailEnrollment:
    row = await session.get(EmailEnrollment, enrollment_id)
    if row is None or row.brand_id != tenant.brand_id:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Enrollment not found.")
    return row


async def _resolve_email(session, *, tenant, contact_id, to_email) -> tuple[str, uuid.UUID | None, uuid.UUID | None]:
    """Return (to_email, contact_id, company_id) — from a real contact or an
    explicit address. Never invents an address."""
    if contact_id is not None:
        c = await session.get(Contact, contact_id)
        if c is None or c.brand_id != tenant.brand_id:
            raise HTTPException(status.HTTP_404_NOT_FOUND, "Contact not found.")
        addr = to_email or c.email
        if not addr:
            raise HTTPException(status.HTTP_400_BAD_REQUEST, "Contact has no email; provide to_email.")
        return addr, c.id, c.company_id
    if not to_email:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, "Provide a contact_id or to_email.")
    return to_email, None, None


async def enroll(session, *, tenant, sequence_id, contact_id=None, to_email=None,
                 lead_id=None, company_id=None, deal_id=None, campaign_id=None) -> EmailEnrollment:
    seq = await _owned_sequence(session, tenant=tenant, sequence_id=sequence_id)
    steps = await _steps(session, seq.id)
    addr, resolved_contact, resolved_company = await _resolve_email(
        session, tenant=tenant, contact_id=contact_id, to_email=to_email
    )
    first_delay = steps[0].delay_hours if steps else 0
    row = EmailEnrollment(
        id=uuid.uuid4(), organization_id=tenant.organization_id, brand_id=tenant.brand_id,
        sequence_id=seq.id, to_email=addr, status="active", current_step=0,
        next_run_at=datetime.now(UTC) + timedelta(hours=first_delay),
        contact_id=resolved_contact, lead_id=lead_id,
        company_id=company_id or resolved_company, deal_id=deal_id, campaign_id=campaign_id,
        enrolled_by_user_id=tenant.user_id,
    )
    session.add(row)
    await _audit(session, tenant=tenant, action="crm.email_enrolled", target_id=row.id,
                 metadata={"sequence_id": str(seq.id)})
    await session.commit()
    await session.refresh(row)
    return row


async def bulk_enroll(session, *, tenant, sequence_id, contact_ids: list[uuid.UUID]) -> list[EmailEnrollment]:
    out: list[EmailEnrollment] = []
    for cid in contact_ids:
        try:
            out.append(await enroll(session, tenant=tenant, sequence_id=sequence_id, contact_id=cid))
        except HTTPException:
            continue  # skip contacts without email / not owned
    return out


async def list_enrollments(session, *, tenant, sequence_id=None, enrollment_status=None,
                           limit=100, offset=0) -> tuple[list[EmailEnrollment], int]:
    conds = [EmailEnrollment.brand_id == tenant.brand_id]
    if sequence_id is not None:
        conds.append(EmailEnrollment.sequence_id == sequence_id)
    if enrollment_status is not None:
        conds.append(EmailEnrollment.status == enrollment_status)
    total = (await session.execute(select(func.count()).select_from(EmailEnrollment).where(*conds))).scalar_one()
    rows = await session.execute(
        select(EmailEnrollment).where(*conds).order_by(EmailEnrollment.created_at.desc()).limit(limit).offset(offset)
    )
    return list(rows.scalars().all()), int(total)


async def set_enrollment_status(session, *, tenant, enrollment_id, new_status) -> EmailEnrollment:
    row = await _owned_enrollment(session, tenant=tenant, enrollment_id=enrollment_id)
    if row.status in ("completed", "cancelled", "stopped") and new_status != "cancelled":
        raise HTTPException(status.HTTP_409_CONFLICT, f"Enrollment is {row.status}.")
    row.status = new_status
    await session.commit()
    await session.refresh(row)
    return row


async def run_due_enrollments(session, *, tenant, limit: int = 50) -> int:
    """Advance the brand's due active enrollments — send the current step's
    email, honour stop/wait conditions, schedule the next step. Idempotent-ish:
    only enrollments with next_run_at<=now are touched."""
    now = datetime.now(UTC)
    rows = (await session.execute(
        select(EmailEnrollment).where(
            EmailEnrollment.brand_id == tenant.brand_id,
            EmailEnrollment.status == "active",
            EmailEnrollment.next_run_at.isnot(None),
            EmailEnrollment.next_run_at <= now,
        ).limit(limit)
    )).scalars().all()

    processed = 0
    for enr in rows:
        steps = await _steps(session, enr.sequence_id)
        if enr.current_step >= len(steps):
            enr.status = "completed"
            continue
        step = steps[enr.current_step]

        # Stop condition — a prior email in this enrollment got a reply.
        if step.stop_on_reply:
            replied = (await session.execute(
                select(func.count()).select_from(Email).where(
                    Email.enrollment_id == enr.id, Email.replied_at.isnot(None)
                )
            )).scalar_one()
            if replied:
                enr.status = "stopped"
                continue

        # Wait condition — hold until the previous email was opened.
        if step.wait_for_open and enr.current_step > 0:
            last_opened = (await session.execute(
                select(func.max(Email.opened_at)).where(Email.enrollment_id == enr.id)
            )).scalar_one()
            if last_opened is None:
                enr.next_run_at = now + timedelta(hours=max(1, step.delay_hours or 24))
                continue

        # Send this step.
        subject, body = "(no template)", ""
        if step.template_id is not None:
            tpl = await session.get(EmailTemplate, step.template_id)
            if tpl is not None and tpl.brand_id == tenant.brand_id:
                variables: dict[str, str] = {}
                subject, body, _ = render(tpl.subject, tpl.body, variables)
        await _stage_and_send(
            session, tenant=tenant, to_email=enr.to_email, subject=subject, body=body,
            template_id=step.template_id, sequence_id=enr.sequence_id, enrollment_id=enr.id,
            contact_id=enr.contact_id, company_id=enr.company_id, deal_id=enr.deal_id,
            lead_id=enr.lead_id, campaign_id=enr.campaign_id,
        )

        enr.current_step += 1
        if enr.current_step >= len(steps):
            enr.status = "completed"
            enr.next_run_at = None
        else:
            enr.next_run_at = now + timedelta(hours=steps[enr.current_step].delay_hours)
        processed += 1

    await session.commit()
    return processed


# =====================================================================
#  Sending + tracking
# =====================================================================
async def _stage_and_send(session, *, tenant, to_email, subject, body, template_id=None,
                          sequence_id=None, enrollment_id=None, contact_id=None, company_id=None,
                          deal_id=None, lead_id=None, campaign_id=None) -> Email:
    """Create the email record, hand it to the provider, and write a timeline
    activity. Commits are the caller's responsibility."""
    token = secrets.token_urlsafe(24)
    email = Email(
        id=uuid.uuid4(), organization_id=tenant.organization_id, brand_id=tenant.brand_id,
        template_id=template_id, sequence_id=sequence_id, enrollment_id=enrollment_id,
        to_email=to_email, subject=subject, body=body, status="queued", track_token=token,
        contact_id=contact_id, company_id=company_id, deal_id=deal_id, lead_id=lead_id,
        campaign_id=campaign_id, sent_by_user_id=tenant.user_id,
    )
    session.add(email)

    result = await email_providers.get_email_provider().send(
        email_providers.EmailSendRequest(to_email=to_email, subject=subject, html=body)
    )
    email.provider = result.provider
    email.provider_message_id = result.message_id
    email.status = "sent" if result.delivered or result.status in ("queued", "recorded") else "failed"
    email.sent_at = datetime.now(UTC)
    if result.delivered:
        email.delivered_at = email.sent_at

    # Timeline activity (reuse crm_activities) — links the email into the record.
    activity = Activity(
        id=uuid.uuid4(), organization_id=tenant.organization_id, brand_id=tenant.brand_id,
        kind="email", subject=subject, body=(body[:500] if body else None),
        contact_id=contact_id, company_id=company_id, deal_id=deal_id,
        occurred_at=email.sent_at, actor_user_id=tenant.user_id,
        meta={"to": to_email, "email_status": email.status},
    )
    session.add(activity)
    await session.flush()
    email.activity_id = activity.id
    return email


async def send_email(session, *, tenant, payload) -> Email:
    addr, resolved_contact, resolved_company = await _resolve_email(
        session, tenant=tenant, contact_id=payload.contact_id, to_email=payload.to_email
    )
    email = await _stage_and_send(
        session, tenant=tenant, to_email=addr, subject=payload.subject, body=payload.body,
        template_id=payload.template_id, contact_id=resolved_contact,
        company_id=payload.company_id or resolved_company, deal_id=payload.deal_id,
        lead_id=payload.lead_id, campaign_id=payload.campaign_id,
    )
    await _audit(session, tenant=tenant, action="crm.email_sent", target_id=email.id,
                 metadata={"to": addr, "status": email.status})
    await session.commit()
    await session.refresh(email)
    return email


async def list_emails(session, *, tenant, contact_id=None, deal_id=None, email_status=None,
                      limit=100, offset=0) -> tuple[list[Email], int]:
    conds = [Email.brand_id == tenant.brand_id]
    if contact_id is not None:
        conds.append(Email.contact_id == contact_id)
    if deal_id is not None:
        conds.append(Email.deal_id == deal_id)
    if email_status is not None:
        conds.append(Email.status == email_status)
    total = (await session.execute(select(func.count()).select_from(Email).where(*conds))).scalar_one()
    rows = await session.execute(
        select(Email).where(*conds).order_by(Email.created_at.desc()).limit(limit).offset(offset)
    )
    return list(rows.scalars().all()), int(total)


async def email_stats(session, *, tenant) -> dict:
    async def _c(*extra) -> int:
        return int((await session.execute(
            select(func.count()).select_from(Email).where(Email.brand_id == tenant.brand_id, *extra)
        )).scalar_one())

    sent = await _c(Email.status.in_(("sent", "delivered")))
    delivered = await _c(Email.delivered_at.isnot(None))
    opened = await _c(Email.opened_at.isnot(None))
    clicked = await _c(Email.clicked_at.isnot(None))
    replied = await _c(Email.replied_at.isnot(None))
    bounced = await _c(Email.bounced_at.isnot(None))
    unsub = await _c(Email.unsubscribed_at.isnot(None))
    denom = sent or 1
    return {
        "sent": sent, "delivered": delivered, "opened": opened, "clicked": clicked,
        "replied": replied, "bounced": bounced, "unsubscribed": unsub,
        "open_rate": round(opened / denom, 4), "click_rate": round(clicked / denom, 4),
        "reply_rate": round(replied / denom, 4), "bounce_rate": round(bounced / denom, 4),
    }


# ---- tracking by token (public, no tenant header) ----
async def _by_token(session, token: str) -> Email | None:
    return (await session.execute(select(Email).where(Email.track_token == token))).scalar_one_or_none()


async def mark_opened(session, token: str) -> None:
    email = await _by_token(session, token)
    if email is not None:
        email.open_count += 1
        if email.opened_at is None:
            email.opened_at = datetime.now(UTC)
        await session.commit()


async def mark_clicked(session, token: str) -> None:
    email = await _by_token(session, token)
    if email is not None:
        email.click_count += 1
        now = datetime.now(UTC)
        if email.clicked_at is None:
            email.clicked_at = now
        if email.opened_at is None:  # a click implies an open
            email.opened_at = now
        await session.commit()


async def mark_unsubscribed(session, token: str) -> None:
    email = await _by_token(session, token)
    if email is not None and email.unsubscribed_at is None:
        email.unsubscribed_at = datetime.now(UTC)
        await session.commit()


async def apply_provider_event(session, *, event: str, message_id=None, track_token=None, detail=None) -> bool:
    email = None
    if track_token:
        email = await _by_token(session, track_token)
    if email is None and message_id:
        email = (await session.execute(
            select(Email).where(Email.provider_message_id == message_id)
        )).scalar_one_or_none()
    if email is None:
        return False
    now = datetime.now(UTC)
    if event == "delivered":
        email.delivered_at = email.delivered_at or now
        if email.status == "sent":
            email.status = "delivered"
    elif event == "bounced":
        email.bounced_at = now
        email.status = "bounced"
        email.error_message = (detail or "")[:500]
    elif event == "replied":
        email.replied_at = email.replied_at or now
    elif event == "complained":
        email.unsubscribed_at = email.unsubscribed_at or now
    await session.commit()
    return True
