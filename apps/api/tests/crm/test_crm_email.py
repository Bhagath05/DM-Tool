"""Phase 6.5 Slice 4 — CRM email: variable render, send + timeline activity,
tracking, template versioning, provider events, guards. Hermetic — fake session,
provider stub (no delivery), audit stubbed."""

from __future__ import annotations

import asyncio
import uuid
from types import SimpleNamespace

import pytest
from fastapi import HTTPException

from aicmo.modules.crm import email_service as svc
from aicmo.modules.crm.email_models import (
    Email,
    EmailEnrollment,
    EmailSequence,
    EmailTemplate,
    EmailTemplateVersion,
)
from aicmo.modules.crm.email_schemas import TemplateCreate, TemplateUpdate
from aicmo.modules.crm.models import Activity, Contact

_ORG = uuid.uuid4()
_BRAND = uuid.uuid4()
_TENANT = SimpleNamespace(
    organization_id=_ORG, brand_id=_BRAND, user_id="rep-1", user_uuid=uuid.uuid4()
)


class _Result:
    def __init__(self, one=None):
        self._one = one

    def scalar_one_or_none(self):
        return self._one

    def scalars(self):
        return self

    def all(self):
        return []

    def scalar_one(self):
        return 0


class _Session:
    def __init__(self, store=None, token_email=None):
        self._store = store or {}
        self.token_email = token_email
        self.added: list = []

    async def get(self, _m, i):
        return self._store.get(i)

    async def execute(self, _stmt):
        return _Result(one=self.token_email)

    def add(self, o):
        self.added.append(o)

    async def commit(self):
        pass

    async def refresh(self, _o):
        pass

    async def flush(self):
        pass

    async def delete(self, _o):
        pass


@pytest.fixture(autouse=True)
def _stub_audit(monkeypatch):
    async def _noop(*_a, **_k):
        return None

    monkeypatch.setattr(svc.audit_service, "record", _noop)


def run(c):
    return asyncio.run(c)


# ---- variable render ----
def test_render_substitutes_known_and_keeps_unknown():
    subj, body, unresolved = svc.render(
        "Hi {{contact_first_name}}", "From {{sender}} at {{company}}",
        {"contact_first_name": "Sam", "company": "Acme"},
    )
    assert subj == "Hi Sam"
    assert "Acme" in body and "{{sender}}" in body  # unknown left intact
    assert unresolved == ["sender"]  # reported, never fabricated


# ---- templates + version history ----
def test_create_template_writes_v1_snapshot():
    session = _Session()
    tpl = run(svc.create_template(session, tenant=_TENANT,
              payload=TemplateCreate(name="Welcome", category="welcome",
                                     subject="Hi", body="Hello {{contact_name}}")))
    assert tpl.current_version == 1
    versions = [o for o in session.added if isinstance(o, EmailTemplateVersion)]
    assert len(versions) == 1 and versions[0].version_no == 1


def test_update_template_bumps_version_on_content_change():
    tpl = EmailTemplate(id=uuid.uuid4(), organization_id=_ORG, brand_id=_BRAND,
                        name="W", category="welcome", subject="Hi", body="v1",
                        variables=[], current_version=1)
    session = _Session({tpl.id: tpl})
    run(svc.update_template(session, tenant=_TENANT, template_id=tpl.id,
        payload=TemplateUpdate(body="v2", edit_summary="tweak")))
    assert tpl.current_version == 2
    assert any(isinstance(o, EmailTemplateVersion) for o in session.added)


def test_update_template_no_version_bump_on_metadata_only():
    tpl = EmailTemplate(id=uuid.uuid4(), organization_id=_ORG, brand_id=_BRAND,
                        name="W", category="welcome", subject="Hi", body="v1",
                        variables=[], current_version=1, is_active=True)
    session = _Session({tpl.id: tpl})
    run(svc.update_template(session, tenant=_TENANT, template_id=tpl.id,
        payload=TemplateUpdate(is_active=False)))
    assert tpl.current_version == 1  # metadata-only edit, no new version


def test_cross_tenant_template_404():
    other = EmailTemplate(id=uuid.uuid4(), organization_id=_ORG, brand_id=uuid.uuid4(),
                          name="X", subject="s", body="b", variables=[])
    with pytest.raises(HTTPException) as ei:
        run(svc._owned_template(_Session({other.id: other}), tenant=_TENANT, template_id=other.id))
    assert ei.value.status_code == 404


# ---- send + timeline activity ----
def test_send_creates_email_and_activity_via_stub():
    session = _Session()
    payload = SimpleNamespace(to_email="lead@acme.com", subject="Hi", body="<p>Hello</p>",
                              template_id=None, contact_id=None, company_id=None,
                              deal_id=None, lead_id=None, campaign_id=None)
    email = run(svc.send_email(session, tenant=_TENANT, payload=payload))
    assert email.status == "sent"  # stub 'recorded' → counts as sent, NOT delivered
    assert email.delivered_at is None  # never fabricate delivery
    assert email.provider == "stub" and email.track_token
    # a timeline activity (kind=email) was written
    acts = [o for o in session.added if isinstance(o, Activity)]
    assert len(acts) == 1 and acts[0].kind == "email"


def test_send_requires_recipient():
    payload = SimpleNamespace(to_email=None, subject="s", body="b", template_id=None,
                              contact_id=None, company_id=None, deal_id=None,
                              lead_id=None, campaign_id=None)
    with pytest.raises(HTTPException) as ei:
        run(svc.send_email(_Session(), tenant=_TENANT, payload=payload))
    assert ei.value.status_code == 400


def test_resolve_email_uses_real_contact():
    c = Contact(id=uuid.uuid4(), organization_id=_ORG, brand_id=_BRAND, name="Jane",
                email="jane@acme.com", company_id=None)
    addr, cid, _ = run(svc._resolve_email(_Session({c.id: c}), tenant=_TENANT,
                                          contact_id=c.id, to_email=None))
    assert addr == "jane@acme.com" and cid == c.id


# ---- tracking ----
def test_mark_opened_sets_timestamp_and_counts():
    email = Email(id=uuid.uuid4(), organization_id=_ORG, brand_id=_BRAND, to_email="x@y.com",
                  subject="s", body="b", track_token="tok", open_count=0)
    session = _Session(token_email=email)
    run(svc.mark_opened(session, "tok"))
    assert email.opened_at is not None and email.open_count == 1


def test_mark_clicked_implies_open():
    email = Email(id=uuid.uuid4(), organization_id=_ORG, brand_id=_BRAND, to_email="x@y.com",
                  subject="s", body="b", track_token="tok", open_count=0, click_count=0)
    session = _Session(token_email=email)
    run(svc.mark_clicked(session, "tok"))
    assert email.clicked_at is not None and email.opened_at is not None and email.click_count == 1


def test_provider_event_bounce_and_reply():
    email = Email(id=uuid.uuid4(), organization_id=_ORG, brand_id=_BRAND, to_email="x@y.com",
                  subject="s", body="b", track_token="tok", status="sent")
    session = _Session(token_email=email)
    run(svc.apply_provider_event(session, event="bounced", track_token="tok", detail="hard bounce"))
    assert email.status == "bounced" and email.bounced_at is not None

    email2 = Email(id=uuid.uuid4(), organization_id=_ORG, brand_id=_BRAND, to_email="x@y.com",
                   subject="s", body="b", track_token="t2", status="sent")
    run(svc.apply_provider_event(_Session(token_email=email2), event="replied", track_token="t2"))
    assert email2.replied_at is not None


# ---- enrollment guard ----
def test_cannot_reactivate_cancelled_enrollment():
    enr = EmailEnrollment(id=uuid.uuid4(), organization_id=_ORG, brand_id=_BRAND,
                          sequence_id=uuid.uuid4(), to_email="x@y.com", status="cancelled")
    with pytest.raises(HTTPException) as ei:
        run(svc.set_enrollment_status(_Session({enr.id: enr}), tenant=_TENANT,
            enrollment_id=enr.id, new_status="active"))
    assert ei.value.status_code == 409


def test_cross_tenant_sequence_404():
    other = EmailSequence(id=uuid.uuid4(), organization_id=_ORG, brand_id=uuid.uuid4(), name="X")
    with pytest.raises(HTTPException) as ei:
        run(svc._owned_sequence(_Session({other.id: other}), tenant=_TENANT, sequence_id=other.id))
    assert ei.value.status_code == 404
