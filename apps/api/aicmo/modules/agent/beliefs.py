"""Agent-side adapter that turns the tenant's belief memory into a bounded,
read-only context block for one conversational turn.

It calls the Phase-3A resolver ONCE per turn (no N+1), selects only beliefs
relevant to the user's question, renders a deterministic bounded block (active
beliefs by default; historical only on explicit request), and exposes safe
evidence references. It never surfaces ORM rows, DB ids, secrets, or tenant
identifiers, and there is no write path — beliefs are data for reasoning only.
"""

from __future__ import annotations

from dataclasses import dataclass, field

from sqlalchemy.ext.asyncio import AsyncSession

from aicmo.modules.agent.schemas import EvidenceRef
from aicmo.modules.belief import resolver
from aicmo.modules.belief.enums import BeliefCategory
from aicmo.modules.belief.schemas import BeliefView
from aicmo.tenancy.context import TenantContext

# Bounds — the belief block is always small and deterministic.
_RESOLVE_LIMIT = 25
_MAX_ACTIVE = 8
_MAX_HISTORY = 5

# Deterministic keyword → category mapping. Substring match on the lowercased
# question; used only to NARROW which active beliefs are relevant.
_CATEGORY_KEYWORDS: dict[BeliefCategory, tuple[str, ...]] = {
    BeliefCategory.BUSINESS: ("business", "company", "product", "service", "goal"),
    BeliefCategory.AUDIENCE: ("audience", "customer", "persona", "icp", "segment", "buyer"),
    BeliefCategory.MARKET: ("market", "competitor", "trend", "demand", "industry"),
    BeliefCategory.POSITIONING: ("positioning", "position", "differentiat", "messaging"),
    BeliefCategory.OFFER: ("offer", "pricing", "price", "discount", "bundle"),
    BeliefCategory.CONTENT: ("content", "blog", "post copy", "caption"),
    BeliefCategory.CHANNEL: ("channel", "platform", "instagram", "facebook", "linkedin", "youtube", "email"),
    BeliefCategory.CAMPAIGN: ("campaign", "promotion", "launch"),
    BeliefCategory.CREATIVE: ("creative", "ad ", "ads", "reel", "video", "image", "poster", "post "),
    BeliefCategory.PERFORMANCE: ("perform", "ctr", "conversion", "roas", "leads", "engagement", "results", "metric"),
    BeliefCategory.LEARNING: ("learn", "lesson", "experiment", "test"),
}

# Specific phrases that signal the user wants the historical chain.
_HISTORY_PHRASES: tuple[str, ...] = (
    "previously belie",
    "used to",
    "why did you change",
    "why did we change",
    "were we wrong",
    "was i wrong",
    "what changed",
    "changed your recommendation",
    "changed our mind",
    "past belief",
    "old belief",
    "no longer",
)


@dataclass
class BeliefContext:
    block: str | None = None
    beliefs_consulted: list[str] = field(default_factory=list)
    historical: bool = False
    evidence: list[EvidenceRef] = field(default_factory=list)


def _relevant_categories(user_text: str) -> set[BeliefCategory]:
    low = user_text.lower()
    return {cat for cat, kws in _CATEGORY_KEYWORDS.items() if any(k in low for k in kws)}


def _wants_history(user_text: str) -> bool:
    low = user_text.lower()
    return any(p in low for p in _HISTORY_PHRASES)


def _scope_str(view: BeliefView) -> str:
    items = list(view.scope.items())[:4]
    return ", ".join(f"{k}={v}" for k, v in items) or "unscoped"


async def build_belief_context(
    session: AsyncSession, *, tenant: TenantContext, user_text: str
) -> BeliefContext:
    """Resolve a bounded, relevant belief block for this turn.

    Returns an empty context (no block) when relevance cannot be established
    safely — never dumps the whole memory. Tenant/brand come from ``tenant``."""
    historical = _wants_history(user_text)
    categories = _relevant_categories(user_text)

    # Nothing to anchor relevance on → provide no belief context (not a dump).
    if not categories and not historical:
        return BeliefContext()

    try:
        resolution = await resolver.resolve_beliefs(
            session, tenant=tenant, include_history=historical, limit=_RESOLVE_LIMIT
        )
    except Exception:
        # Fail closed: any resolution problem (e.g. missing brand) → no belief
        # context. Belief memory is best-effort and never breaks the turn.
        return BeliefContext(historical=historical)

    cat_values = {c.value for c in categories}

    def _keep(view: BeliefView) -> bool:
        return not cat_values or str(view.category) in cat_values

    active = [b for b in resolution.active if _keep(b)][:_MAX_ACTIVE]
    history = [b for b in (resolution.superseded + resolution.contradicted) if _keep(b)][:_MAX_HISTORY]

    if not active and not history:
        return BeliefContext(historical=historical)

    lines = [
        "DM Tool's current evidence-backed beliefs — learned hypotheses/conclusions, "
        "NOT universal truths. Confidence is evidence-derived.",
    ]
    for b in active:
        conf = b.effective_confidence if b.effective_confidence is not None else b.confidence
        lines.append(
            f"- [{b.category}] {b.statement[:240]} "
            f"(confidence {conf}%; {b.confidence_reason[:120]}; "
            f"status={b.status}; {b.evidence_count} evidence; scope: {_scope_str(b)})"
        )
    if historical and history:
        lines.append("PREVIOUS / CHANGED BELIEFS (historical — NOT current truth):")
        for b in history:
            changed = "superseded" if b.superseded_by_id else b.status
            lines.append(
                f"- [{b.category}] {b.statement[:200]} (was confidence {b.confidence}%; {changed})"
            )

    consulted = [f"{b.category}:{b.subject_key}" for b in active]
    evidence = [
        EvidenceRef(
            label=f"belief:{b.category}:{b.subject_key}",
            source=b.confidence_reason or None,
            confidence=(b.effective_confidence if b.effective_confidence is not None else b.confidence),
            status=b.status,
        )
        for b in active
    ]
    return BeliefContext(
        block="\n".join(lines),
        beliefs_consulted=consulted,
        historical=historical,
        evidence=evidence,
    )
