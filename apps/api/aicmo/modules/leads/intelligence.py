"""Lead Intelligence orchestrator — Phase 5.

Composition layer over the leads table + analytics. The composer pulls
the inbox snapshot deterministically, scores up to ~10 candidate leads
with a heuristic prescorer, then hands them to the LLM which writes
the narrative + ranks.

Failure policy: identical to Reality Engine / Weekly Plan — the founder
always gets a usable report. If the LLM fails OR returns invalid lead
indices, we fall back to a deterministic plan derived from the same
prescorer score, so the inbox page never 5xx's.

Cost: one LLM call per request. Frontend caches for 30 minutes via
localStorage (mirrors `analytics-summary`'s pattern) so a busy founder
refreshing the inbox isn't burning credits.
"""

from __future__ import annotations

import uuid
from datetime import UTC, datetime, timedelta

import structlog
from sqlalchemy import desc, select
from sqlalchemy.ext.asyncio import AsyncSession

from aicmo.llm import get_llm_router
from aicmo.llm.providers.base import LLMMessage
from aicmo.modules.analytics import service as analytics_service
from aicmo.modules.leads.models import Lead
from aicmo.modules.leads.prompts import (
    LEAD_INTELLIGENCE_SYSTEM_PROMPT,
    build_lead_intelligence_user_prompt,
)
from aicmo.modules.leads.schemas import (
    EstimatedValueBand,
    LeadCountsSnapshot,
    LeadHeroRecommendation,
    LeadIntelligenceReport,
    LeadPriority,
    _LeadIntelligenceNarrative,
    _NarrativeLeadPriority,
)
from aicmo.modules.onboarding.schemas import BusinessProfileResponse

log = structlog.get_logger()

# Cap on how many leads we send to the LLM. Keeps the prompt cheap and
# focused. The inbox can still hold thousands of historical leads — we
# only ask the LLM to rank the actionable ones.
MAX_CANDIDATES = 10

# Cap on how many priorities the LLM can return. Mirror in the prompt.
MAX_PRIORITIES = 5

# Heuristic prescore — used to pick which leads even go to the LLM and
# to produce a deterministic fallback ranking when the LLM fails.
_RECENT_HOURS = 24
_WEEKLY_HOURS = 24 * 7


# ---------------------------------------------------------------------
#  Public entry point
# ---------------------------------------------------------------------


async def build_lead_intelligence(
    session: AsyncSession,
    *,
    profile: BusinessProfileResponse,
) -> LeadIntelligenceReport:
    """Single read-only entry point. No DB writes."""
    composed = await _compose(session, profile=profile)

    # If there are literally zero leads, skip the LLM call entirely and
    # return a deterministic "get your first lead" report — saves a
    # credit and the LLM has nothing useful to say with no inbox.
    if composed["counts"].total == 0:
        return _zero_state_report(composed)

    narrative = await _generate_narrative(profile=profile, composed=composed)

    return _assemble_report(narrative=narrative, composed=composed)


# ---------------------------------------------------------------------
#  Composer
# ---------------------------------------------------------------------


async def _compose(
    session: AsyncSession, *, profile: BusinessProfileResponse
) -> dict:
    """Pull every signal needed to score + narrate the inbox."""
    now = datetime.now(UTC)
    signals: list[str] = []

    # 1) Counts snapshot — drives the inbox header card.
    counts = await _load_counts(session, brand_id=profile.brand_id, now=now)
    if counts.total == 0:
        signals.append("Inbox is empty — pre-traction.")
    else:
        signals.append(
            f"{counts.total} leads total · {counts.last_7d} in the last 7 days · "
            f"{counts.last_24h} in the last 24 hours · {counts.new_count} unactioned · "
            f"{counts.hot_count} marked hot."
        )

    # 2) Candidate set — recent + actionable. Sorted by prescorer.
    candidates = await _load_candidates(
        session, brand_id=profile.brand_id, limit=MAX_CANDIDATES, now=now
    )
    if candidates:
        signals.append(
            f"{len(candidates)} candidate leads ranked by the heuristic prescorer."
        )
    scored = [(_prescore_lead(c, now=now), c) for c in candidates]
    scored.sort(key=lambda x: x[0], reverse=True)
    ordered_candidates = [c for _, c in scored]

    # 3) Top channel — what's actually working. Helps the LLM say
    # "this lead came from your best channel, double down".
    top_source_summary: str | None = None
    try:
        sources = await analytics_service.by_source(
            session, brand_id=profile.brand_id, limit=1
        )
        if sources.items:
            top = sources.items[0]
            label = (
                top.utm_campaign
                or top.utm_source
                or top.source_asset_type
                or "(unknown)"
            )
            top_source_summary = f"{label} — {top.leads} leads, {top.hot_leads} hot."
            signals.append(f"Top channel so far: {top_source_summary}")
    except Exception as e:
        log.warning("leads.intelligence.sources_lookup_failed", error=str(e))

    # 4) Profile context the LLM uses as prior — stage, audience, channels.
    if profile.current_monthly_leads_band:
        signals.append(f"Stated traction band: {profile.current_monthly_leads_band}.")
    if profile.monthly_budget_band:
        signals.append(f"Stated monthly marketing budget: {profile.monthly_budget_band}.")

    leads_block = _format_leads_block(ordered_candidates, now=now)
    counts_block = _format_counts_block(counts)

    return {
        "counts": counts,
        "candidates": ordered_candidates,
        "leads_block": leads_block,
        "counts_block": counts_block,
        "top_source_summary": top_source_summary,
        "signals": signals,
        "prescores": [s for s, _ in scored],
    }


async def _load_counts(
    session: AsyncSession, *, brand_id: uuid.UUID, now: datetime
) -> LeadCountsSnapshot:
    """One round-trip counts query using Postgres FILTER clauses."""
    from sqlalchemy import func

    week_ago = now - timedelta(hours=_WEEKLY_HOURS)
    day_ago = now - timedelta(hours=_RECENT_HOURS)

    stmt = select(
        func.count().label("total"),
        func.count().filter(Lead.status == "new").label("new_count"),
        func.count().filter(Lead.status == "hot").label("hot_count"),
        func.count().filter(Lead.created_at >= week_ago).label("last_7d"),
        func.count().filter(Lead.created_at >= day_ago).label("last_24h"),
    ).where(Lead.brand_id == brand_id)
    row = (await session.execute(stmt)).one()
    return LeadCountsSnapshot(
        total=int(row.total),
        new_count=int(row.new_count),
        hot_count=int(row.hot_count),
        last_7d=int(row.last_7d),
        last_24h=int(row.last_24h),
    )


async def _load_candidates(
    session: AsyncSession,
    *,
    brand_id: uuid.UUID,
    limit: int,
    now: datetime,
) -> list[Lead]:
    """Pull the most actionable leads: archived rows excluded, ordered by
    recency desc. Capped to `limit`. Bigger inboxes are filtered later
    by the prescorer; for now recency is the dominant signal."""
    cutoff = now - timedelta(days=45)
    stmt = (
        select(Lead)
        .where(
            Lead.brand_id == brand_id,
            Lead.status != "archived",
            Lead.created_at >= cutoff,
        )
        .order_by(desc(Lead.created_at))
        .limit(limit)
    )
    rows = (await session.execute(stmt)).scalars().all()
    return list(rows)


# ---------------------------------------------------------------------
#  Heuristic prescorer
# ---------------------------------------------------------------------


def _prescore_lead(lead: Lead, *, now: datetime) -> int:
    """Deterministic priority score (0-100) used to:

    1. Pick which leads even go to the LLM (top 10).
    2. Drive the deterministic fallback when the LLM fails.

    Higher = more urgent. The bands roughly match the LLM's confidence
    calibration so the fallback feels consistent.
    """
    score = 0

    # Status — hot dominates.
    if lead.status == "hot":
        score += 40
    elif lead.status == "new":
        score += 20
    elif lead.status == "warm":
        score += 15
    elif lead.status == "cold":
        score += 5
    # archived already filtered upstream

    # Recency — last 24h is the sweet spot for replies.
    age = now - lead.created_at if lead.created_at.tzinfo else now.replace(tzinfo=None) - lead.created_at
    age_hours = age.total_seconds() / 3600
    if age_hours <= 24:
        score += 25
    elif age_hours <= 24 * 3:
        score += 15
    elif age_hours <= 24 * 7:
        score += 5

    # Contactability — phone is the single best predictor of a quick reply.
    if lead.phone:
        score += 15
    if lead.message and len(lead.message.strip()) >= 20:
        score += 10  # they wrote you a real note — engage

    # Attribution quality — paid + specific campaign tends to be more
    # qualified than direct anonymous traffic.
    if lead.utm_campaign:
        score += 5
    if lead.company:
        score += 5

    return max(0, min(100, score))


def _bucket_from_score(score: int) -> str:
    """Map a prescore to a priority bucket. Used by the fallback path."""
    if score >= 70:
        return "focus"
    if score >= 50:
        return "hot"
    if score >= 30:
        return "warm"
    return "cold"


# ---------------------------------------------------------------------
#  Formatters — turn rows into the prompt's text blocks
# ---------------------------------------------------------------------


def _format_leads_block(leads: list[Lead], *, now: datetime) -> str:
    if not leads:
        return "(no candidate leads — the inbox is empty or fully archived)"
    lines: list[str] = []
    for i, lead in enumerate(leads, start=1):
        age_hours = (
            now - lead.created_at
            if lead.created_at.tzinfo
            else now.replace(tzinfo=None) - lead.created_at
        ).total_seconds() / 3600
        if age_hours < 1:
            age_label = "<1h ago"
        elif age_hours < 24:
            age_label = f"{int(age_hours)}h ago"
        else:
            age_label = f"{int(age_hours / 24)}d ago"

        contact_bits: list[str] = []
        if lead.phone:
            contact_bits.append("has phone")
        if lead.company:
            contact_bits.append(f"company={lead.company}")
        if lead.message and lead.message.strip():
            snippet = lead.message.strip().replace("\n", " ")
            if len(snippet) > 80:
                snippet = snippet[:77] + "…"
            contact_bits.append(f'message="{snippet}"')

        attribution_bits: list[str] = []
        if lead.utm_campaign:
            attribution_bits.append(f"campaign={lead.utm_campaign}")
        if lead.utm_source:
            attribution_bits.append(f"source={lead.utm_source}")
        if lead.utm_medium:
            attribution_bits.append(f"medium={lead.utm_medium}")
        if lead.source_asset_type:
            attribution_bits.append(f"asset={lead.source_asset_type}")

        line = (
            f"{i}. email={lead.email} "
            f"name={lead.name or '?'} "
            f"status={lead.status} "
            f"age={age_label}"
        )
        if contact_bits:
            line += " · " + " · ".join(contact_bits)
        if attribution_bits:
            line += " · " + " · ".join(attribution_bits)
        lines.append(line)
    return "\n".join(lines)


def _format_counts_block(counts: LeadCountsSnapshot) -> str:
    return (
        f"- Total leads: {counts.total}\n"
        f"- New (unactioned): {counts.new_count}\n"
        f"- Hot: {counts.hot_count}\n"
        f"- Last 7 days: {counts.last_7d}\n"
        f"- Last 24 hours: {counts.last_24h}"
    )


# ---------------------------------------------------------------------
#  LLM call — single invocation, fallback on error.
# ---------------------------------------------------------------------


async def _generate_narrative(
    *,
    profile: BusinessProfileResponse,
    composed: dict,
) -> _LeadIntelligenceNarrative:
    router = get_llm_router()
    user_prompt = build_lead_intelligence_user_prompt(
        profile=profile,
        leads_block=composed["leads_block"],
        counts_block=composed["counts_block"],
        top_source_summary=composed["top_source_summary"],
        signals=composed["signals"],
    )
    try:
        result = await router.generate(
            response_schema=_LeadIntelligenceNarrative,
            system=LEAD_INTELLIGENCE_SYSTEM_PROMPT,
            messages=[LLMMessage(role="user", content=user_prompt)],
            temperature=0.5,
            # Mirrors weekly plan headroom — Gemini 2.5 Flash burns
            # thinking tokens against this budget before emitting content.
            max_tokens=5000,
        )
        return result.data
    except Exception as e:
        # Advisory must degrade gracefully — never 5xx the inbox.
        log.warning("leads.intelligence.narrative_failed", error=str(e))
        return _fallback_narrative(composed)


# ---------------------------------------------------------------------
#  Assemble the public response — resolves indices → real lead rows
# ---------------------------------------------------------------------


def _assemble_report(
    *,
    narrative: _LeadIntelligenceNarrative,
    composed: dict,
) -> LeadIntelligenceReport:
    candidates: list[Lead] = composed["candidates"]

    priorities: list[LeadPriority] = []
    seen_focus = False

    for np in narrative.priorities[:MAX_PRIORITIES]:
        idx = np.lead_index - 1
        if idx < 0 or idx >= len(candidates):
            # LLM hallucinated an index — drop the entry rather than
            # making up a lead. The frontend can still render the rest.
            log.warning(
                "leads.intelligence.bad_index",
                lead_index=np.lead_index,
                candidate_count=len(candidates),
            )
            continue

        # The Constitution forbids more than one 'focus'. If the LLM
        # mis-ordered, demote any later 'focus' entries to 'hot'.
        priority = np.priority
        if priority == "focus":
            if seen_focus:
                priority = "hot"
            else:
                seen_focus = True

        lead = candidates[idx]
        priorities.append(
            LeadPriority(
                lead_id=lead.id,
                email=lead.email,
                name=lead.name,
                company=lead.company,
                rank=len(priorities) + 1,
                priority=priority,
                why_now=np.why_now,
                recommended_action=np.recommended_action,
                expected_result=np.expected_result,
                confidence=np.confidence,
                reason=np.reason,
                impact_category=np.impact_category,
                estimated_value_band=np.estimated_value_band,
                cta_label=np.cta_label,
            )
        )

    # If we ended up with priorities but none marked focus (because every
    # entry the LLM produced was 'hot'), promote rank 1 → focus so the
    # Constitution's "exactly one focus when priorities exist" rule holds.
    if priorities and not any(p.priority == "focus" for p in priorities):
        priorities[0] = priorities[0].model_copy(update={"priority": "focus"})

    return LeadIntelligenceReport(
        headline=narrative.headline,
        hero_recommendation=narrative.hero_recommendation,
        priorities=priorities,
        skip_for_now=narrative.skip_for_now,
        counts=composed["counts"],
        signals_used=composed["signals"],
        generated_at=datetime.now(UTC).isoformat(),
    )


# ---------------------------------------------------------------------
#  Deterministic fallback (LLM unavailable or invalid response)
# ---------------------------------------------------------------------


def _fallback_narrative(composed: dict) -> _LeadIntelligenceNarrative:
    """Built from the deterministic prescorer. Every field on every
    priority is filled so the Constitution contract holds even when the
    LLM is down. Confidence is intentionally moderate (50-75) because
    this is rule-of-thumb, not informed analysis."""
    candidates: list[Lead] = composed["candidates"]
    prescores: list[int] = composed["prescores"]
    counts: LeadCountsSnapshot = composed["counts"]

    priorities: list[_NarrativeLeadPriority] = []
    focus_assigned = False

    for i, (lead, score) in enumerate(zip(candidates, prescores, strict=False)):
        if score < 30 and len(priorities) >= 1:
            # Don't pad the list with cold leads in the fallback.
            break
        if len(priorities) >= MAX_PRIORITIES:
            break

        bucket = _bucket_from_score(score)
        if bucket == "focus":
            if focus_assigned:
                bucket = "hot"
            else:
                focus_assigned = True

        priorities.append(
            _NarrativeLeadPriority(
                lead_index=i + 1,
                priority=bucket,  # type: ignore[arg-type]
                why_now=_fallback_why_now(lead),
                recommended_action=_fallback_action(lead),
                expected_result=_fallback_expected(lead),
                confidence=min(75, max(45, score - 5)),
                reason=_fallback_reason(lead),
                impact_category="revenue",
                estimated_value_band=_fallback_value_band(lead),
                cta_label=_fallback_cta(lead),
            )
        )

    # Same fix as in _assemble_report — if no focus, promote rank 1.
    if priorities and not any(p.priority == "focus" for p in priorities):
        priorities[0] = priorities[0].model_copy(update={"priority": "focus"})

    return _LeadIntelligenceNarrative(
        headline=(
            f"You have {counts.total} leads in the inbox — "
            f"start with the warmest ones from this week."
            if counts.total > 0
            else "Your inbox is empty — the next step is getting your first lead in."
        ),
        hero_recommendation=_fallback_hero(counts),
        priorities=priorities,
        skip_for_now=[],
    )


def _fallback_hero(counts: LeadCountsSnapshot) -> LeadHeroRecommendation:
    if counts.total == 0:
        return LeadHeroRecommendation(
            what_is_happening="Your lead inbox is empty — nobody has filled out a form yet.",
            impact_category="lead",
            recommendation="Publish a lead page if you haven't, then share its link in one of your usual posts today.",
            expected_result="Even 30-50 visitors typically produce your first 1-3 leads.",
            confidence=65,
            reason="Based on the empty inbox — no captured leads possible without a page + traffic.",
        )
    if counts.last_24h > 0:
        return LeadHeroRecommendation(
            what_is_happening=(
                f"{counts.last_24h} {'lead' if counts.last_24h == 1 else 'leads'} "
                f"arrived in the last 24 hours — reply speed is the single biggest "
                "predictor of whether they convert."
            ),
            impact_category="revenue",
            recommendation="Reply to the most recent leads today, starting with anyone who left a phone number.",
            expected_result="Typically 1-2 quick conversations booked within 48 hours, with one likely to convert.",
            confidence=70,
            reason=f"Based on {counts.last_24h} fresh leads in the last 24h — replies in the first 24h convert 5-10x better.",
        )
    if counts.hot_count > 0:
        return LeadHeroRecommendation(
            what_is_happening=(
                f"You have {counts.hot_count} leads marked hot but no fresh "
                "submissions in the last 24 hours — work the hot ones before they cool."
            ),
            impact_category="revenue",
            recommendation="Send a one-line follow-up to each hot lead today asking a single qualifying question.",
            expected_result="1-2 hot leads typically reply within 48 hours when nudged.",
            confidence=65,
            reason=f"Based on {counts.hot_count} hot leads and no fresh signal in the last 24h.",
        )
    return LeadHeroRecommendation(
        what_is_happening=(
            f"You have {counts.total} leads in the inbox but nothing fresh "
            "this week — the channel that brought them in may have gone quiet."
        ),
        impact_category="lead",
        recommendation="Publish one new post or ad pointing at your lead page this week to re-prime the channel.",
        expected_result="A small refresh in submissions over the following 7-10 days.",
        confidence=55,
        reason="Based on existing leads but zero in the last 24h — the funnel needs new traffic.",
    )


def _fallback_why_now(lead: Lead) -> str:
    bits: list[str] = []
    if lead.status == "hot":
        bits.append("marked hot")
    if lead.status == "new":
        bits.append("not yet contacted")
    if lead.phone:
        bits.append("left a phone number")
    if lead.utm_campaign:
        bits.append(f"came in via the {lead.utm_campaign} campaign")
    elif lead.utm_source:
        bits.append(f"came in from {lead.utm_source}")
    if not bits:
        bits.append("recent submission worth a quick reply")
    return "This lead is " + ", ".join(bits) + "."


def _fallback_action(lead: Lead) -> str:
    if lead.phone:
        return "Call within the next 24 hours — a short conversation usually beats email at this stage."
    if lead.message and len(lead.message.strip()) >= 20:
        return "Reply directly to their message with one qualifying question and a clear next step."
    return "Send a short, personalised email that references how they found you, and propose a 15-minute call."


def _fallback_expected(lead: Lead) -> str:
    if lead.status == "hot" or lead.phone:
        return "A reply within 48 hours, with a 1-in-3 chance of converting to paying."
    return "A reply within a week if the offer fits; otherwise a clean cold-mark."


def _fallback_reason(lead: Lead) -> str:
    bits: list[str] = [f"status={lead.status}"]
    if lead.phone:
        bits.append("has phone")
    if lead.utm_campaign:
        bits.append(f"campaign={lead.utm_campaign}")
    elif lead.utm_source:
        bits.append(f"source={lead.utm_source}")
    return "Heuristic prescore — " + ", ".join(bits) + "."


def _fallback_value_band(lead: Lead) -> EstimatedValueBand:
    if lead.company and lead.phone:
        return "high"
    if lead.company or lead.phone:
        return "medium"
    if lead.status in ("hot", "warm"):
        return "medium"
    return "unknown"


def _fallback_cta(lead: Lead) -> str:
    if lead.phone:
        return "Call now"
    if lead.message and len(lead.message.strip()) >= 20:
        return "Reply today"
    return "Send email"


# ---------------------------------------------------------------------
#  Zero-state — no inbox at all
# ---------------------------------------------------------------------


def _zero_state_report(composed: dict) -> LeadIntelligenceReport:
    """When the inbox is empty we skip the LLM entirely — there's nothing
    to rank, and the founder is best served by a direct "get your first
    lead in" call to action."""
    counts: LeadCountsSnapshot = composed["counts"]
    return LeadIntelligenceReport(
        headline="Your lead inbox is empty — let's get your first one in.",
        hero_recommendation=_fallback_hero(counts),
        priorities=[],
        skip_for_now=[
            "Don't buy a contact list — bought leads almost never convert for small businesses.",
        ],
        counts=counts,
        signals_used=composed["signals"],
        generated_at=datetime.now(UTC).isoformat(),
    )
