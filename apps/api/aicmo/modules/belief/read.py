"""Read-only projection of belief memory for the UI (Phase 3D).

Maps the internal ``BeliefResolution`` (resolver output) into UI-facing
``BeliefCard`` rows: the freshness-adjusted confidence up front, the original
confidence retained for honesty, evidence flattened to kind/relation/note, and
internal tenant ids dropped. No new querying happens here — this is a pure,
deterministic shape transform.
"""

from __future__ import annotations

from datetime import datetime

from aicmo.modules.belief.schemas import (
    BeliefCard,
    BeliefEvidenceCard,
    BeliefReadResponse,
    BeliefResolution,
    BeliefView,
)


def _card(view: BeliefView, *, is_current: bool) -> BeliefCard:
    confidence = view.effective_confidence if view.effective_confidence is not None else view.confidence
    return BeliefCard(
        id=view.id,
        category=view.category,
        subject=view.subject_key,
        statement=view.statement,
        scope=view.scope,
        status=view.status,
        confidence=confidence,
        original_confidence=view.confidence,
        confidence_reason=view.confidence_reason,
        freshness_reason=view.freshness_reason,
        evidence_count=view.evidence_count,
        evidence=[
            BeliefEvidenceCard(kind=e.ref_kind, relation=e.relation, note=e.note)
            for e in view.evidence
        ],
        established_at=view.valid_from,
        last_validated_at=view.validated_at,
        valid_until=view.valid_until,
        is_current=is_current,
        superseded_by_id=view.superseded_by_id,
    )


def to_read_response(
    resolution: BeliefResolution, *, now: datetime, includes_history: bool
) -> BeliefReadResponse:
    active = [_card(v, is_current=True) for v in resolution.active]
    historical = [
        _card(v, is_current=False)
        for v in (resolution.superseded + resolution.contradicted)
    ]
    return BeliefReadResponse(
        as_of=now,
        active=active,
        historical=historical,
        truncated=resolution.truncated,
        includes_history=includes_history,
    )
