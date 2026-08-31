"""Human-in-the-loop control — regression proofs.

DM Tool is an AI *copilot with human control*, never an autonomous robot.
These tests pin the hard product+security requirement that a human remains the
final decision authority. They exercise the REAL service-layer enforcement
(the autonomy policy engine, the operations safety chokepoint, and the
publishing approval state machine) — not a UI demo. Frontend buttons are not a
trust boundary; every proof below runs against backend code.

Each test maps to one of the 15 required invariants:

  01  AI recommendation cannot directly publish
  02  AI recommendation cannot directly spend
  03  Unapproved creative cannot execute
  04  Rejected recommendation cannot execute
  05  Modified creative executes only in its approved form
  06  Cross-tenant users cannot approve another tenant's actions
  07  Approval is recorded in the audit trail
  08  Unauthorized users cannot approve restricted actions
  09  Human approval survives a page refresh (persisted, re-read)
  10  Duplicate approval cannot cause duplicate execution
  11  Failed execution does not incorrectly become APPROVED/published
  12  Human rejection remains authoritative
  13  Insufficient evidence cannot be represented as verified
  14  AI confidence cannot bypass approval
  15  High-risk actions require explicit human approval

Invariants that assert persistence / cross-session reads (07-DB, 09, 15-DB)
run against a real local Postgres and skip when one isn't reachable.
"""

from __future__ import annotations

import asyncio
import inspect
import uuid
from datetime import UTC, datetime
from types import SimpleNamespace

import pytest
from fastapi import HTTPException

from aicmo.modules.autonomy import service as autonomy_service
from aicmo.modules.autonomy.schemas import ActionPolicy, AutonomyPolicyConfig
from aicmo.modules.crm import assistant_service
from aicmo.modules.operations import safety
from aicmo.modules.publishing import queue_service
from aicmo.modules.publishing import service as publishing_service
from aicmo.modules.publishing.queue_service import (
    BLOCKED_APPROVALS,
    PUBLISHABLE_APPROVALS,
)
from aicmo.tenancy.dependencies import require_permission
from aicmo.tenancy.exceptions import NotAuthorized

# ---------------------------------------------------------------------
#  Hermetic doubles — a fake session + row, exactly like the existing
#  publishing queue-ops tests. No DB, no network; the REAL service code
#  under test runs unchanged.
# ---------------------------------------------------------------------

_BRAND = uuid.uuid4()
_ORG = uuid.uuid4()
_TENANT = SimpleNamespace(
    organization_id=_ORG, brand_id=_BRAND, user_id="reviewer-1", user_uuid=uuid.uuid4()
)


def _row(**over):
    now = datetime.now(UTC)
    base = dict(
        id=uuid.uuid4(), brand_id=_BRAND, organization_id=_ORG, user_id="creator-1",
        content_asset_id=uuid.uuid4(), recommendation_id=None, platform="instagram",
        scheduled_at=now, publish_status="scheduled", platform_post_id=None,
        published_at=None, error_message=None, attempt_count=0, next_attempt_at=None,
        approval_status="not_required", approval_required=False,
        reviewed_by_user_id=None, approval_reason=None, schedule_timezone=None,
        created_at=now, updated_at=now,
    )
    base.update(over)
    return SimpleNamespace(**base)


class _Session:
    """Captures add()s so audit writes are observable; get() returns the row."""

    def __init__(self, row):
        self._row = row
        self.added: list = []
        self.committed = False

    async def get(self, _model, _id):
        return self._row

    def add(self, obj):
        self.added.append(obj)

    async def commit(self):
        self.committed = True

    async def refresh(self, _obj):
        pass


def _run(coro):
    return asyncio.run(coro)


def _publish(row):
    return _run(
        publishing_service.publish_scheduled_post(_Session(row), scheduled_post_id=row.id)
    )


# =====================================================================
#  01 — AI recommendation cannot directly publish
# =====================================================================
def test_inv01_ai_cannot_directly_publish():
    # The scheduler's due-query only ever selects publishable approval states,
    # and a 'pending' (AI-prepared, not-yet-approved) post is not among them.
    assert set(PUBLISHABLE_APPROVALS).isdisjoint(BLOCKED_APPROVALS)
    assert "pending" in BLOCKED_APPROVALS and "pending" not in PUBLISHABLE_APPROVALS

    # And the manual publish path (defence in depth) refuses it too.
    pending = _row(approval_status="pending", approval_required=True)
    with pytest.raises(HTTPException) as ei:
        _publish(pending)
    assert ei.value.status_code == 409
    assert "approval" in ei.value.detail.lower()


# =====================================================================
#  02 — AI recommendation cannot directly spend
# =====================================================================
def test_inv02_ai_cannot_directly_spend():
    cfg = AutonomyPolicyConfig()  # safe default: always_approve, manual, untrusted
    for action in ("ad_spending", "budget_change"):
        assert safety.is_side_effecting(action)
        # Master switch OFF (platform default) — must require approval.
        d_off = autonomy_service.evaluate_policy(cfg, action, execution_enabled=False)
        assert not d_off.allow_auto and d_off.requires_approval
        # Even with the master switch ON, the default policy still gates spend.
        d_on = autonomy_service.evaluate_policy(cfg, action, execution_enabled=True)
        assert not d_on.allow_auto and d_on.requires_approval


# =====================================================================
#  03 — Unapproved creative cannot execute
# =====================================================================
def test_inv03_unapproved_creative_cannot_execute():
    # A creative/content post that requires approval but hasn't got it cannot
    # be published — execution is blocked at the service layer.
    post = _row(approval_status="pending", approval_required=True, platform="instagram")
    with pytest.raises(HTTPException) as ei:
        _publish(post)
    assert ei.value.status_code == 409


# =====================================================================
#  04 — Rejected recommendation cannot execute
# =====================================================================
def test_inv04_rejected_cannot_execute():
    assert "rejected" in BLOCKED_APPROVALS and "rejected" not in PUBLISHABLE_APPROVALS
    rejected = _row(approval_status="rejected", approval_required=True)
    with pytest.raises(HTTPException) as ei:
        _publish(rejected)
    assert ei.value.status_code == 409


# =====================================================================
#  05 — Modified creative executes only in its approved form
# =====================================================================
def test_inv05_modification_forces_reapproval():
    # Requesting changes on a post moves it to 'changes_requested' — a modified
    # state that is NOT publishable until a human approves the new version.
    row = _row(approval_status="pending", approval_required=True)
    out = _run(
        queue_service.request_changes(_Session(row), tenant=_TENANT, post_id=row.id, reason="fix tone")
    )
    assert out.approval_status == "changes_requested"
    assert "changes_requested" in BLOCKED_APPROVALS
    # The modified post cannot execute until re-approved.
    with pytest.raises(HTTPException) as ei:
        _publish(_row(approval_status="changes_requested"))
    assert ei.value.status_code == 409
    # Publishing exposes NO route to mutate approved content in place — the only
    # content-changing path funnels back through submit → approval.
    import aicmo.modules.publishing.router as prouter

    paths = [r.path for r in prouter.router.routes]
    assert not any(p.endswith("/edit") or p.endswith("/content") for p in paths)


# =====================================================================
#  06 — Cross-tenant users cannot approve another tenant's actions
# =====================================================================
def test_inv06_cross_tenant_cannot_approve():
    # Row belongs to a DIFFERENT brand than the approving tenant.
    foreign = _row(brand_id=uuid.uuid4(), approval_status="pending")
    with pytest.raises(HTTPException) as ei:
        _run(queue_service.approve_post(_Session(foreign), tenant=_TENANT, post_id=foreign.id, reason="x"))
    assert ei.value.status_code == 404  # _owned fails closed on brand mismatch


# =====================================================================
#  07 — Approval is recorded in the audit trail
# =====================================================================
def test_inv07_approval_is_audited():
    from aicmo.modules.publishing.models import PublishEvent

    row = _row(approval_status="pending", approval_required=True)
    sess = _Session(row)
    _run(queue_service.approve_post(sess, tenant=_TENANT, post_id=row.id, reason="looks good"))
    events = [o for o in sess.added if isinstance(o, PublishEvent)]
    assert events, "approval must write a PublishEvent audit row"
    ev = events[0]
    assert ev.event_type == "approval_approved"
    assert ev.detail.get("by") == _TENANT.user_id  # WHO approved is recorded
    assert row.reviewed_by_user_id == _TENANT.user_id
    assert row.approval_reason == "looks good"


# =====================================================================
#  08 — Unauthorized users cannot approve restricted actions
# =====================================================================
def test_inv08_unauthorized_cannot_approve():
    dep = require_permission("content.approve")

    def _ctx(perms):
        return SimpleNamespace(
            permissions=frozenset(perms), user_uuid=uuid.uuid4(),
            organization_id=_ORG, role_slugs=frozenset({"viewer"}),
        )

    # Missing content.approve → denied.
    with pytest.raises(NotAuthorized):
        _run(dep(tenant=_ctx({"analytics.view"})))
    # Has content.approve → allowed (returns the tenant).
    ok = _run(dep(tenant=_ctx({"content.approve"})))
    assert "content.approve" in ok.permissions


# =====================================================================
#  10 — Duplicate approval cannot cause duplicate execution
# =====================================================================
def test_inv10_no_duplicate_approval_or_execution():
    # (a) You cannot re-decide a post that is not 'pending' — a second approve
    #     of an already-approved post is a 409, so approval isn't re-applied.
    already = _row(approval_status="approved")
    with pytest.raises(HTTPException) as ei:
        _run(queue_service.approve_post(_Session(already), tenant=_TENANT, post_id=already.id, reason=None))
    assert ei.value.status_code == 409
    # (b) Publishing an already-published post is idempotent — it returns the
    #     existing record without a second publish.
    published = _row(publish_status="published", approval_status="approved")
    out = _publish(published)
    assert out.publish_status == "published"
    assert published.attempt_count == 0  # no new publish attempt was made


# =====================================================================
#  11 — Failed execution does not incorrectly become APPROVED/published
# =====================================================================
def test_inv11_failed_execution_is_not_published():
    # Approved + out of attempts → the publish call marks it FAILED, never
    # 'published', and never mints a fresh approval.
    row = _row(
        approval_status="approved",
        publish_status="scheduled",
        attempt_count=publishing_service.MAX_PUBLISH_ATTEMPTS,
    )
    out = _publish(row)
    assert out.publish_status == "failed"
    assert out.publish_status != "published"
    assert row.approval_status == "approved"  # unchanged — failure ≠ new approval


# =====================================================================
#  12 — Human rejection remains authoritative
# =====================================================================
def test_inv12_rejection_is_authoritative():
    # A rejected post cannot be flipped by another automated decide() call —
    # only a human re-submission (→ pending) reopens it.
    rejected = _row(approval_status="rejected")
    with pytest.raises(HTTPException) as ei:
        _run(queue_service.approve_post(_Session(rejected), tenant=_TENANT, post_id=rejected.id, reason=None))
    assert ei.value.status_code == 409
    # The policy engine's explicit 'never' mode always requires approval,
    # regardless of the master switch or any amount.
    cfg = AutonomyPolicyConfig(policies={"social_publishing": ActionPolicy(mode="never")})
    d = autonomy_service.evaluate_policy(cfg, "social_publishing", execution_enabled=True)
    assert not d.allow_auto and d.requires_approval


# =====================================================================
#  13 — Insufficient evidence cannot be represented as verified
# =====================================================================
def test_inv13_insufficient_evidence_is_honest():
    tenant = SimpleNamespace(organization_id=_ORG, brand_id=_BRAND, user_id="u1")
    ins = assistant_service._insufficient(
        tenant, "lead", uuid.uuid4(), "lead_intelligence", []
    )
    assert ins.insufficient_evidence is True
    assert ins.recommendation is None      # no fabricated recommendation
    assert ins.confidence == 0             # not dressed up as confident
    assert ins.model is None               # no LLM was invoked
    assert ins.summary == "Not enough evidence."


# =====================================================================
#  14 — AI confidence cannot bypass approval
# =====================================================================
def test_inv14_confidence_cannot_bypass_approval():
    # The gate takes no 'confidence' input at all — confidence is structurally
    # incapable of changing the decision.
    params = inspect.signature(autonomy_service.evaluate_policy).parameters
    assert "confidence" not in params
    # And a high-stakes action under the default policy requires approval even
    # with the master switch ON (there is no confidence override).
    cfg = AutonomyPolicyConfig()
    d = autonomy_service.evaluate_policy(cfg, "social_publishing", execution_enabled=True)
    assert not d.allow_auto and d.requires_approval


# =====================================================================
#  15 — High-risk actions require explicit human approval (by default)
# =====================================================================
def test_inv15_high_risk_actions_gated_by_default():
    cfg = AutonomyPolicyConfig()  # unconfigured workspace = safe default
    for action in safety.SIDE_EFFECTING_ACTIONS:
        d_off = autonomy_service.evaluate_policy(cfg, action, execution_enabled=False)
        d_on = autonomy_service.evaluate_policy(cfg, action, execution_enabled=True)
        assert not d_off.allow_auto, f"{action} auto-ran with master switch off"
        assert not d_on.allow_auto, f"{action} auto-ran under default policy"


# =====================================================================
#  Real-Postgres integration proofs (persistence / cross-session).
#  Skip cleanly when a local Postgres isn't reachable.
# =====================================================================


def _pg():
    from tests._dbtest import pg_reachable

    if not pg_reachable():
        pytest.skip("Postgres not reachable")


def _engine():
    from sqlalchemy.ext.asyncio import create_async_engine

    from tests._dbtest import async_dsn

    return create_async_engine(async_dsn())


async def _seed_pending_post(conn_exec, *, org, brand, user, post_id, brand_of_post=None):
    """Insert the minimal tenant graph + a pending scheduled post via raw SQL."""
    from sqlalchemy import text

    bop = brand_of_post or brand
    tag = uuid.uuid4().hex[:8]
    asset_id = uuid.uuid4()
    await conn_exec(text(
        "INSERT INTO users (id, clerk_user_id, email) VALUES (:i,:c,:e)"
    ), {"i": user, "c": f"clerk_{tag}", "e": f"{tag}@t.local"})
    await conn_exec(text(
        "INSERT INTO organizations (id, slug, name, owner_user_id) VALUES (:i,:s,:n,:o)"
    ), {"i": org, "s": f"org-{tag}", "n": "Gov Org", "o": user})
    await conn_exec(text(
        "INSERT INTO brands (id, organization_id, slug, name, created_by_user_id) "
        "VALUES (:i,:o,:s,:n,:u)"
    ), {"i": brand, "o": org, "s": f"brand-{tag}", "n": "Gov Brand", "u": user})
    await conn_exec(text(
        "INSERT INTO content_assets (id, user_id, asset_type, source_table, source_id, "
        "organization_id, brand_id, payload) VALUES (:i,:u,'post','manual',:src,:o,:b,'{}'::jsonb)"
    ), {"i": asset_id, "u": str(user), "src": uuid.uuid4(), "o": org, "b": bop})
    await conn_exec(text(
        "INSERT INTO scheduled_posts (id, user_id, content_asset_id, platform, scheduled_at, "
        "publish_status, approval_status, approval_required, organization_id, brand_id) "
        "VALUES (:i,:u,:a,'instagram',:t,'scheduled','pending',true,:o,:b)"
    ), {"i": post_id, "u": str(user), "a": asset_id, "t": datetime.now(UTC), "o": org, "b": bop})


@pytest.mark.asyncio
async def test_inv09_approval_survives_refresh_and_is_audited_in_db():
    """09 + 07(DB): a human approval persists and is readable from a FRESH
    session (a page refresh / new request sees it), with an audit row."""
    _pg()
    from sqlalchemy import text
    from sqlalchemy.ext.asyncio import AsyncSession

    org, brand, user, post = uuid.uuid4(), uuid.uuid4(), uuid.uuid4(), uuid.uuid4()
    eng = _engine()
    try:
        async with eng.begin() as conn:
            await _seed_pending_post(conn.execute, org=org, brand=brand, user=user, post_id=post)

        tenant = SimpleNamespace(organization_id=org, brand_id=brand, user_id=str(user))
        # Approve through the REAL service, which commits.
        async with AsyncSession(eng) as s:
            await queue_service.approve_post(s, tenant=tenant, post_id=post, reason="ship it")

        # A brand-new session (simulating a refresh / next request) must see it.
        async with AsyncSession(eng) as s2:
            row = (await s2.execute(text(
                "SELECT approval_status, reviewed_by_user_id FROM scheduled_posts WHERE id=:i"
            ), {"i": post})).one()
            assert row[0] == "approved"
            assert str(row[1]) == str(user)
            n_events = (await s2.execute(text(
                "SELECT count(*) FROM publish_events WHERE scheduled_post_id=:i "
                "AND event_type='approval_approved'"
            ), {"i": post})).scalar_one()
            assert n_events == 1  # audit trail persisted
    finally:
        async with eng.begin() as conn:
            await conn.execute(text("DELETE FROM organizations WHERE id=:i"), {"i": org})
            await conn.execute(text("DELETE FROM users WHERE id=:i"), {"i": user})
        await eng.dispose()


@pytest.mark.asyncio
async def test_inv06_cross_tenant_approve_is_404_in_db():
    """06(DB): approving with the wrong tenant fails closed against real rows."""
    _pg()
    from sqlalchemy import text
    from sqlalchemy.ext.asyncio import AsyncSession

    org, brand, user, post = uuid.uuid4(), uuid.uuid4(), uuid.uuid4(), uuid.uuid4()
    eng = _engine()
    try:
        async with eng.begin() as conn:
            await _seed_pending_post(conn.execute, org=org, brand=brand, user=user, post_id=post)
        # A tenant scoped to a DIFFERENT brand tries to approve → 404.
        foreign = SimpleNamespace(organization_id=uuid.uuid4(), brand_id=uuid.uuid4(), user_id=str(user))
        async with AsyncSession(eng) as s:
            with pytest.raises(HTTPException) as ei:
                await queue_service.approve_post(s, tenant=foreign, post_id=post, reason="x")
            assert ei.value.status_code == 404
        # The post is untouched — still pending.
        async with AsyncSession(eng) as s2:
            st = (await s2.execute(text(
                "SELECT approval_status FROM scheduled_posts WHERE id=:i"
            ), {"i": post})).scalar_one()
            assert st == "pending"
    finally:
        async with eng.begin() as conn:
            await conn.execute(text("DELETE FROM organizations WHERE id=:i"), {"i": org})
            await conn.execute(text("DELETE FROM users WHERE id=:i"), {"i": user})
        await eng.dispose()


@pytest.mark.asyncio
async def test_inv15_safety_chokepoint_blocks_spend_in_db():
    """15(DB): the operations safety chokepoint fails closed for a real brand
    with no policy row — spend/publish cannot auto-run."""
    _pg()
    from sqlalchemy.ext.asyncio import AsyncSession

    eng = _engine()
    try:
        async with AsyncSession(eng) as s:
            for action in ("ad_spending", "social_publishing", "budget_change"):
                with pytest.raises(safety.ActionNotPermitted):
                    await safety.assert_action_permitted(
                        s, brand_id=uuid.uuid4(), action_type=action
                    )
    finally:
        await eng.dispose()
