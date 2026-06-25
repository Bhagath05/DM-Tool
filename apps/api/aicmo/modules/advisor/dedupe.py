"""Fingerprint + suppression rules for advisor recommendations."""

from __future__ import annotations

import hashlib
import uuid
from datetime import UTC, datetime, timedelta

from aicmo.modules.advisor.models import AdvisorRecommendation
from aicmo.modules.opportunities.schemas import GeneratorHint, OpportunityKind

_SUPPRESS_COMPLETED_DAYS = 90
_SUPPRESS_SKIPPED_DAYS = 30


def fingerprint_for_opportunity(
    *,
    kind: OpportunityKind,
    generator: GeneratorHint,
    recommended_action: str,
) -> str:
    payload = "|".join(
        [
            kind,
            generator.target,
            generator.format,
            (generator.platform or "").lower(),
            (generator.objective or "").lower(),
            " ".join(recommended_action.lower().split()),
        ]
    )
    return hashlib.sha256(payload.encode("utf-8")).hexdigest()[:64]


def fingerprint_for_hero(recommendation: str) -> str:
    normalised = " ".join(recommendation.lower().split())
    return hashlib.sha256(f"hero|{normalised}".encode("utf-8")).hexdigest()[:64]


def recommendation_id_from_fingerprint(fingerprint: str) -> uuid.UUID:
    namespace = uuid.UUID("a1b2c3d4-e5f6-7890-abcd-ef1234567890")
    return uuid.uuid5(namespace, fingerprint)


def should_suppress(
    fingerprint: str,
    memory_rows: list[AdvisorRecommendation],
    *,
    now: datetime | None = None,
) -> bool:
    """True when this action was recently completed or skipped."""
    now = now or datetime.now(UTC)
    for row in memory_rows:
        if row.source_fingerprint != fingerprint:
            continue
        if row.status == "completed" and row.completed_at:
            if row.completed_at >= now - timedelta(days=_SUPPRESS_COMPLETED_DAYS):
                return True
        if row.status == "skipped" and row.skipped_at:
            if row.skipped_at >= now - timedelta(days=_SUPPRESS_SKIPPED_DAYS):
                return True
    return False


def impact_label(score: int) -> str:
    if score >= 70:
        return "High"
    if score >= 40:
        return "Medium"
    return "Low"
