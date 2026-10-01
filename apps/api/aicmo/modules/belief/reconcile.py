"""Cross-belief contradiction / supersession detection (Phase 3D).

Within a single ``subject_key`` the belief service already reconciles evidence
(supports vs. contradicts) and flips a belief to CONTRADICTED when the evidence
turns. This module handles the *cross-belief* case: two DIFFERENT active beliefs
that make opposing claims about the **same scoped slice**.

The hard safety rule (heavily tested): **beliefs with different scopes must
never contradict each other.** Two beliefs may only conflict when they are
"comparable" — same category, and in agreement on every distinguishing scope
dimension they both specify (channel / audience / metric / measurement window /
action kind / …). A belief about Instagram cannot contradict a belief about
email; a belief about a 7-day window cannot contradict one about 90 days.

When a genuine conflict is found, we DO NOT delete anything. We reuse the
Phase-3A ``supersede_belief`` primitive so the losing belief keeps its
confidence, evidence, timestamps, scope, and provenance, and gains a
``superseded_by_id`` pointer — the historical chain stays fully auditable.

Everything here is deterministic and server-side: no LLM decides what conflicts
or which belief wins.
"""

from __future__ import annotations

import uuid
from dataclasses import dataclass, field

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from aicmo.modules.belief import service as belief_service
from aicmo.modules.belief.enums import BeliefStatus
from aicmo.modules.belief.models import Belief
from aicmo.tenancy.context import TenantContext

# Scope keys that make two beliefs "about different things". If two beliefs both
# specify one of these and disagree on its value, they are NOT comparable and can
# never contradict. (Provenance-only keys like ``measured_via`` are excluded —
# they describe HOW a belief was learned, not WHAT slice it is about.)
_DISTINGUISHING_KEYS: frozenset[str] = frozenset(
    {
        "channel",
        "platform",
        "audience",
        "segment",
        "icp",
        "metric",
        "window",
        "measurement_window",
        "action_kind",
        "record_type",
        "market",
        "campaign",
        "content_type",
        "creative_format",
        "offer",
    }
)

# Direction vocabulary → normalized {up, down}. A belief's claim points a metric
# either up or down; two active beliefs pointing the SAME metric opposite ways on
# a comparable slice are a contradiction.
_UP_WORDS = frozenset({"increase", "up", "positive", "helps", "improves", "raises", "higher"})
_DOWN_WORDS = frozenset({"decrease", "down", "negative", "hurts", "reduces", "lowers", "lower"})

_DEFAULT_METRIC_BY_CATEGORY: dict[str, str] = {
    "performance": "lead_volume",
    "channel": "lead_volume",
    "campaign": "lead_volume",
    "content": "engagement",
    "creative": "engagement",
    "audience": "engagement",
}
_FALLBACK_METRIC = "outcome"


@dataclass(frozen=True)
class Stance:
    metric: str
    direction: str  # "up" | "down"


@dataclass
class ReconcileResult:
    belief_id: uuid.UUID
    status: str  # no_conflict | reconciled
    winner_id: uuid.UUID | None = None
    superseded_ids: list[uuid.UUID] = field(default_factory=list)


def _norm(value: object) -> str:
    return str(value).strip().lower()


def _direction(word: str) -> str:
    if word in _DOWN_WORDS:
        return "down"
    if word in _UP_WORDS:
        return "up"
    return "up"  # a plain claim asserts the subject *helps* the metric


def scopes_comparable(a: dict, b: dict) -> bool:
    """True only when two scopes describe the same slice.

    They must share at least one distinguishing dimension, and must AGREE on
    every distinguishing dimension they both specify. Disagreement on any shared
    distinguishing key (or no shared distinguishing key at all) ⇒ not comparable,
    so the two beliefs can never be treated as contradicting each other.
    """
    if not isinstance(a, dict) or not isinstance(b, dict):
        return False
    shared = [k for k in _DISTINGUISHING_KEYS if k in a and k in b]
    if not shared:
        return False
    return all(_norm(a[k]) == _norm(b[k]) for k in shared)


def derive_stance(*, scope: dict, status: str, category: str) -> Stance | None:
    """Deterministic (metric, direction) for an ACTIVE belief, else None.

    Only a live, held belief has a stance that can conflict with another. The
    metric comes from the scope (falling back to a per-category default) and the
    direction from the scope's declared ``effect`` (default: the claim points the
    metric up). No LLM involvement — a pure read of structured fields.
    """
    if status != BeliefStatus.ACTIVE.value:
        return None
    scope = scope if isinstance(scope, dict) else {}
    metric = _norm(scope.get("metric") or _DEFAULT_METRIC_BY_CATEGORY.get(category, _FALLBACK_METRIC))
    direction = _direction(_norm(scope.get("effect", "increase")))
    return Stance(metric=metric, direction=direction)


def _opposite(a: Stance, b: Stance) -> bool:
    return a.metric == b.metric and a.direction != b.direction


async def find_conflicts(
    session: AsyncSession, *, tenant: TenantContext, belief: Belief
) -> list[Belief]:
    """Active beliefs that contradict ``belief`` on a comparable slice.

    Empty unless ``belief`` is itself ACTIVE with a derivable stance. Candidates
    are same-tenant, same-category, ACTIVE beliefs whose scope is comparable and
    whose stance points the same metric the opposite way.
    """
    stance = derive_stance(scope=belief.scope, status=belief.status, category=belief.category)
    if stance is None:
        return []
    brand_id = belief_service._require_brand(tenant)
    rows = (
        (
            await session.execute(
                select(Belief).where(
                    Belief.brand_id == brand_id,
                    Belief.organization_id == tenant.organization_id,
                    Belief.category == belief.category,
                    Belief.status == BeliefStatus.ACTIVE.value,
                    Belief.id != belief.id,
                )
            )
        )
        .scalars()
        .all()
    )
    conflicts: list[Belief] = []
    for other in rows:
        other_stance = derive_stance(
            scope=other.scope, status=other.status, category=other.category
        )
        if other_stance is None:
            continue
        if not _opposite(stance, other_stance):
            continue
        if not scopes_comparable(belief.scope, other.scope):
            continue
        conflicts.append(other)
    return conflicts


def _rank_key(b: Belief) -> tuple:
    """Higher is better: more confidence, then more recently validated/created,
    then a stable id tiebreak so the winner is fully deterministic."""
    validated = b.validated_at or b.valid_from
    return (b.confidence, validated, b.created_at, str(b.id))


async def reconcile_belief(
    session: AsyncSession, *, tenant: TenantContext, belief_id: uuid.UUID
) -> ReconcileResult:
    """Detect and resolve cross-belief contradictions for one belief.

    If ``belief`` conflicts with other active beliefs on a comparable slice, the
    strongest / most recent belief survives and the rest are SUPERSEDED (history
    preserved). Safe to call repeatedly — a belief with no comparable opposite is
    left untouched.
    """
    belief = await belief_service.get_belief(session, tenant=tenant, belief_id=belief_id)
    conflicts = await find_conflicts(session, tenant=tenant, belief=belief)
    if not conflicts:
        return ReconcileResult(belief_id=belief_id, status="no_conflict")

    contenders = [belief, *conflicts]
    winner = max(contenders, key=_rank_key)
    superseded: list[uuid.UUID] = []
    for loser in contenders:
        if loser.id == winner.id:
            continue
        await belief_service.supersede_belief(
            session, tenant=tenant, old_belief_id=loser.id, new_belief_id=winner.id
        )
        superseded.append(loser.id)
    return ReconcileResult(
        belief_id=belief_id,
        status="reconciled",
        winner_id=winner.id,
        superseded_ids=superseded,
    )
