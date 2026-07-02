"""Module 9 — Autonomy Policy service + the reusable evaluation core.

`evaluate_policy` is pure and is the single place any part of the platform asks
"may the AI do this automatically, or must a human approve?" It FAILS SAFE: any
ambiguity, misconfiguration, or unknown mode resolves to requiring approval.
"""

from __future__ import annotations

import uuid
from datetime import UTC, datetime
from zoneinfo import ZoneInfo

import structlog
from sqlalchemy import desc, select
from sqlalchemy.ext.asyncio import AsyncSession

from aicmo.modules.audit import service as audit_service
from aicmo.modules.autonomy.models import AutonomyPolicy
from aicmo.modules.autonomy.schemas import (
    ActionPolicy,
    AutonomyCatalog,
    AutonomyPolicyConfig,
    AutonomyPolicyUpdate,
    BusinessHours,
    CatalogEntry,
    PolicyDecision,
)
from aicmo.tenancy.context import TenantContext

log = structlog.get_logger()


# ---------------------------------------------------------------------
#  Evaluation core (pure) — the one place autonomy is decided
# ---------------------------------------------------------------------
def _requires_approval(action_type: str, mode: str, reason: str) -> PolicyDecision:
    return PolicyDecision(
        action_type=action_type,
        mode=mode,  # type: ignore[arg-type]
        allow_auto=False,
        requires_approval=True,
        reason=reason,
    )


def _allow_auto(action_type: str, mode: str, reason: str) -> PolicyDecision:
    return PolicyDecision(
        action_type=action_type,
        mode=mode,  # type: ignore[arg-type]
        allow_auto=True,
        requires_approval=False,
        reason=reason,
    )


def _within_business_hours(bh: BusinessHours, now: datetime) -> bool:
    if not bh.enabled:
        return False
    try:
        local = now.astimezone(ZoneInfo(bh.timezone))
    except Exception:
        return False
    if local.weekday() not in (bh.days or []):
        return False
    # Support windows that don't wrap midnight (start < end).
    return bh.start_hour <= local.hour < bh.end_hour


def evaluate_policy(
    config: AutonomyPolicyConfig,
    action_type: str,
    *,
    amount: float | None = None,
    now: datetime | None = None,
) -> PolicyDecision:
    """Decide whether `action_type` may run automatically under `config`.
    Fails safe: unknown modes / missing thresholds → approval required."""
    now = now or datetime.now(UTC)
    ap = config.policies.get(action_type)
    mode = ap.mode if ap is not None else config.default_mode

    if mode == "auto_always":
        return _allow_auto(action_type, mode, "Policy allows automatic execution for this action.")

    if mode == "never":
        return _requires_approval(
            action_type, mode,
            "Policy: the AI never performs this automatically — you do it yourself.",
        )

    if mode == "always_approve":
        return _requires_approval(
            action_type, mode, "Policy requires your approval before this runs."
        )

    if mode == "auto_below_threshold":
        thr = ap.threshold_amount if ap is not None else None
        if thr is None:
            return _requires_approval(
                action_type, mode, "No auto-approve threshold set — approval required."
            )
        if amount is None:
            return _requires_approval(
                action_type, mode,
                "This action has no amount to compare to the threshold — approval required.",
            )
        if amount <= thr:
            return _allow_auto(
                action_type, mode,
                f"Amount {amount:g} is at/under the auto-approve threshold {thr:g}.",
            )
        return _requires_approval(
            action_type, mode,
            f"Amount {amount:g} exceeds the auto-approve threshold {thr:g} — approval required.",
        )

    if mode == "auto_business_hours":
        if _within_business_hours(config.business_hours, now):
            return _allow_auto(action_type, mode, "Within your configured business hours.")
        return _requires_approval(
            action_type, mode, "Outside business hours — approval required."
        )

    if mode == "auto_if_trusted":
        if config.trusted:
            return _allow_auto(action_type, mode, "This workspace is marked trusted.")
        return _requires_approval(
            action_type, mode, "Workspace is not marked trusted — approval required."
        )

    # Unknown / unexpected mode → never fail open.
    return _requires_approval(action_type, mode, "Unrecognised policy — defaulting to approval.")


# ---------------------------------------------------------------------
#  Persistence
# ---------------------------------------------------------------------
def _to_config(row: AutonomyPolicy) -> AutonomyPolicyConfig:
    return AutonomyPolicyConfig(
        default_mode=row.default_mode,  # type: ignore[arg-type]
        policies={k: ActionPolicy.model_validate(v) for k, v in (row.policies or {}).items()},
        business_hours=BusinessHours.model_validate(row.business_hours)
        if row.business_hours
        else BusinessHours(),
        trusted=row.trusted,
        updated_at=row.updated_at,
        configured=True,
    )


async def _get_row(session: AsyncSession, *, brand_id: uuid.UUID) -> AutonomyPolicy | None:
    stmt = (
        select(AutonomyPolicy)
        .where(AutonomyPolicy.brand_id == brand_id)
        .order_by(desc(AutonomyPolicy.created_at))
        .limit(1)
    )
    return (await session.execute(stmt)).scalar_one_or_none()


async def get_or_default(
    session: AsyncSession, *, brand_id: uuid.UUID
) -> AutonomyPolicyConfig:
    """The brand's policy, or the SAFE default (approve everything) if none."""
    row = await _get_row(session, brand_id=brand_id)
    if row is None:
        return AutonomyPolicyConfig()  # default_mode=always_approve, configured=False
    return _to_config(row)


async def upsert(
    session: AsyncSession, *, tenant: TenantContext, payload: AutonomyPolicyUpdate
) -> AutonomyPolicyConfig:
    row = await _get_row(session, brand_id=tenant.brand_id)
    before = _to_config(row).model_dump(mode="json") if row is not None else None

    if row is None:
        row = AutonomyPolicy(
            id=uuid.uuid4(),
            user_id=tenant.user_id,
            organization_id=tenant.organization_id,
            brand_id=tenant.brand_id,
        )
        session.add(row)

    if payload.default_mode is not None:
        row.default_mode = payload.default_mode
    if payload.policies is not None:
        row.policies = {k: v.model_dump(mode="json") for k, v in payload.policies.items()}
    if payload.business_hours is not None:
        row.business_hours = payload.business_hours.model_dump(mode="json")
    if payload.trusted is not None:
        row.trusted = payload.trusted
    row.user_id = tenant.user_id

    await session.flush()
    after = _to_config(row).model_dump(mode="json")

    # Audit trail — autonomy changes are security-relevant.
    await audit_service.record(
        session,
        organization_id=tenant.organization_id,
        brand_id=tenant.brand_id,
        actor_user_id=tenant.user_uuid,
        action="autonomy.policy_updated",
        target_type="autonomy_policy",
        target_id=row.id,
        before=before,
        after=after,
    )
    await session.commit()
    return _to_config(row)


# ---------------------------------------------------------------------
#  Catalog for the settings UI
# ---------------------------------------------------------------------
_ACTION_LABELS: dict[str, tuple[str, str]] = {
    "content_generation": ("Content generation", "Drafting posts, captions, and copy."),
    "campaign_creation": ("Campaign creation", "Assembling a campaign from a brief."),
    "campaign_launch": ("Campaign launch", "Publishing/launching a campaign live."),
    "social_publishing": ("Social publishing", "Posting to connected social accounts."),
    "email_sending": ("Email sending", "Sending marketing emails to contacts."),
    "budget_change": ("Budget changes", "Changing ad or campaign budgets."),
    "ad_creation": ("Ad creation", "Creating ad creatives and sets."),
    "ad_spending": ("Ad spending", "Committing real ad spend."),
    "image_generation": ("Image generation", "Generating images/visuals (uses credits)."),
    "ai_recommendation": ("AI recommendations", "Producing coaching recommendations."),
    "ai_decision": ("AI decisions", "Producing strategic decisions."),
    "crm_update": ("CRM updates", "Updating leads/contacts in the CRM."),
    "integration": ("Integrations", "Actions via future third-party integrations."),
}

_MODE_LABELS: dict[str, tuple[str, str]] = {
    "always_approve": ("Always require approval", "The AI prepares it; you approve every time."),
    "never": ("Never automate", "The AI never does this — you do it yourself."),
    "auto_below_threshold": ("Auto below a threshold", "Runs automatically under a set amount; approval above it."),
    "auto_business_hours": ("Auto during business hours", "Runs automatically inside your business hours; approval outside."),
    "auto_if_trusted": ("Auto for trusted workspaces", "Runs automatically only if this workspace is marked trusted."),
    "auto_always": ("Full autonomy", "Runs automatically without approval."),
}


def catalog() -> AutonomyCatalog:
    return AutonomyCatalog(
        action_types=[
            CatalogEntry(key=k, label=v[0], description=v[1])
            for k, v in _ACTION_LABELS.items()
        ],
        modes=[
            CatalogEntry(key=k, label=v[0], description=v[1])
            for k, v in _MODE_LABELS.items()
        ],
    )
