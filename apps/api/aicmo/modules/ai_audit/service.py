"""AI generation audit-trail writer.

Public API:
    record_ai_generation(session, *, tenant, action_type, ...)

Same call semantics as the existing `modules.audit.service.record` and
`modules.learning.recorder.record_generation`: best-effort, never
raises, swallows failures so an audit write can never block the
user's action.

Action-type catalog — keep in sync with the user-facing list:
    generate_ad
    generate_content      (text / social / email)
    generate_reel
    generate_creative     (image render)
    generate_campaign
    generate_bundle
    generate_coach_brief

`generation_status` enum (string by design — DB enums are migration-
heavy and we'd rather add new statuses freely):
    success
    failed
    partial               (some platforms in a multi-platform call failed)
    rate_limited
    moderation_blocked

CRITICAL: the `metadata` dict you pass is allowed to carry
non-content signals (e.g. platform name, ad_type, brief id). It is
NOT allowed to carry generated text or image data. The schema does
not validate this — caller is responsible. Reviewer enforces it via
code review.
"""

from __future__ import annotations

import uuid
from typing import Any

import structlog
from sqlalchemy.ext.asyncio import AsyncSession

from aicmo.modules.ai_audit.models import AiAuditEvent
from aicmo.tenancy.context import TenantContext

log = structlog.get_logger()

# Action constants — referenced by callsites. Kept here so a typo in
# a service-layer call is caught at import time instead of producing a
# silent unaudited generation.
ACTION_GENERATE_AD = "generate_ad"
ACTION_GENERATE_CONTENT = "generate_content"
ACTION_GENERATE_REEL = "generate_reel"
ACTION_GENERATE_CREATIVE = "generate_creative"
ACTION_GENERATE_CAMPAIGN = "generate_campaign"
ACTION_GENERATE_BUNDLE = "generate_bundle"
ACTION_GENERATE_COACH_BRIEF = "generate_coach_brief"

STATUS_SUCCESS = "success"
STATUS_FAILED = "failed"
STATUS_PARTIAL = "partial"
STATUS_RATE_LIMITED = "rate_limited"
STATUS_MODERATION_BLOCKED = "moderation_blocked"


async def record_ai_generation(
    session: AsyncSession,
    *,
    tenant: TenantContext,
    action_type: str,
    asset_id: uuid.UUID | None = None,
    model_used: str | None = None,
    generation_status: str = STATUS_SUCCESS,
    error_class: str | None = None,
    duration_ms: int | None = None,
    request_id: str | None = None,
    prompt_token_count: int | None = None,
    completion_token_count: int | None = None,
    ip_address: str | None = None,
    metadata: dict[str, Any] | None = None,
) -> None:
    """Append one row to ai_audit_events. Never raises.

    Same-transaction semantics as the legacy `audit_service.record`:
    if the caller rolls back, this row rolls back too — which is
    correct, because we don't want audit-of-something-that-didn't-
    happen.
    """
    try:
        evt = AiAuditEvent(
            user_id=tenant.user_uuid,
            organization_id=tenant.organization_id,
            brand_id=tenant.brand_id,
            action_type=action_type,
            model_used=model_used,
            asset_id=asset_id,
            generation_status=generation_status,
            error_class=error_class,
            duration_ms=duration_ms,
            request_id=request_id,
            prompt_token_count=prompt_token_count,
            completion_token_count=completion_token_count,
            ip_address=ip_address,
            metadata_json=_strip_content(metadata or {}),
        )
        session.add(evt)
        await session.flush()
    except Exception as e:  # noqa: BLE001 — audit MUST NOT block generation
        log.warning(
            "ai_audit.write_failed",
            action=action_type,
            error=str(e),
            organization_id=str(tenant.organization_id),
        )


# ---------------------------------------------------------------------
# Defensive content scrubber.
#
# The schema can't enforce "no generated content" — that's a caller-
# discipline rule. But we do a paranoid second pass that strips any
# common content keys callers might accidentally pass. Cheap insurance.
# ---------------------------------------------------------------------

_FORBIDDEN_CONTENT_KEYS = frozenset(
    {
        # Free-text generated copy / captions
        "output",
        "generated",
        "generated_text",
        "generated_content",
        "caption",
        "captions",
        "primary_text",
        "headline",
        "headlines",
        "description",
        "descriptions",
        "hook",
        "hooks",
        "script",
        "body",
        # Image data
        "image",
        "image_b64",
        "image_url",
        "rendered_url",
        "raw_response",
    }
)


def _strip_content(metadata: dict[str, Any]) -> dict[str, Any]:
    """Drop keys that smell like generated content. Cheap defence."""
    cleaned: dict[str, Any] = {}
    for k, v in metadata.items():
        if k in _FORBIDDEN_CONTENT_KEYS:
            continue
        # Truncate any unexpectedly long string — even a benign field
        # shouldn't be storing prose in the audit.
        if isinstance(v, str) and len(v) > 512:
            cleaned[k] = v[:512] + "…[truncated]"
        else:
            cleaned[k] = v
    return cleaned
