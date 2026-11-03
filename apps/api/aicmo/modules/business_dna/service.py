"""Canonical Business DNA read service (Phase 7.20 Stage 1).

``get_business_dna`` assembles the EXISTING intelligence into one provenance-aware
snapshot. It REUSES, never duplicates:

* Marketing Brain composition (`marketing_brain.build_context`) — profile,
  Business Brain evidence/ICP/research, analytics, advisor recs, outcomes,
  strategy, learning, and the known/unknown gap lists.
* The shared belief-grounding foundation (`belief.grounding`) — evidence-graded
  beliefs with server-derived confidence + read-time freshness + contradictions.
* The onboarding profile row — for Brand Identity, USPs, and the AI business
  analysis narrative (fields the Marketing Brain snapshot intentionally drops).
* Social audience patterns (`social.service`) — MEASURED audience signals.

Guarantees:
* **Deterministic** — no LLM call participates; every input is a DB read with a
  deterministic order. Only ``generated_at`` varies run-to-run.
* **Read-only** — composes reads; never adds/updates/deletes a row.
* **Honest** — confidence/freshness are server-derived or measured (never
  model-asserted); missing data is UNKNOWN / INSUFFICIENT_EVIDENCE, not invented.
* **Tenant/brand-isolated** — brand scope comes only from the caller's
  ``TenantContext``; every underlying service re-scopes by it.
* **Economics-deferred** — the economics facet is explicitly UNKNOWN in this
  stage (Phase 7.20 Stage 2 owns it). This service does NOT implement it.
"""

from __future__ import annotations

import uuid
from datetime import UTC, datetime

import structlog
from fastapi import HTTPException, status
from sqlalchemy.ext.asyncio import AsyncSession

from aicmo.modules.business_dna import economics, economics_store
from aicmo.modules.business_dna.schemas import (
    BusinessDna,
    ContextProvenance,
    DnaFacet,
    DnaItem,
    FacetStatus,
)
from aicmo.modules.marketing_brain import service as mb_service
from aicmo.modules.onboarding import service as onboarding_service
from aicmo.tenancy.context import TenantContext

log = structlog.get_logger()

# Canonical facet order (deterministic output).
_FACET_ORDER = (
    "identity",
    "brand_identity",
    "offer_positioning",
    "audience",
    "market",
    "evidence",
    "beliefs",
    "performance",
    "learning",
    "economics",
)

_TIER_ORDER = {
    ContextProvenance.USER_STATED: 0,
    ContextProvenance.SYSTEM_INFERRED: 1,
    ContextProvenance.VERIFIED: 2,
    ContextProvenance.MEASURED: 3,
    ContextProvenance.UNKNOWN: 4,
}

PROVENANCE_LEGEND: dict[str, str] = {
    ContextProvenance.USER_STATED.value: (
        "The owner told us (profile, brand voice, goals). Authoritative about "
        "intent; not independently verified."
    ),
    ContextProvenance.SYSTEM_INFERRED.value: (
        "Derived, not confirmed (observations, hypotheses, ICP, strategy, "
        "research, learned beliefs). Treat as a claim, never state as certain."
    ),
    ContextProvenance.VERIFIED.value: (
        "Evidence-backed, confirmed-style claim (Business Brain facts)."
    ),
    ContextProvenance.MEASURED.value: (
        "Real first-party / provider-verified data (analytics KPIs, evaluated "
        "outcomes). Never fabricated; if absent, say so."
    ),
    ContextProvenance.UNKNOWN.value: (
        "An explicit gap. Acknowledge and ask; never fill with a guess."
    ),
}


_ECON_STATUS_MAP = {
    "populated": FacetStatus.POPULATED,
    "insufficient_evidence": FacetStatus.INSUFFICIENT_EVIDENCE,
    "unknown": FacetStatus.UNKNOWN,
}


def _require_brand(tenant: TenantContext) -> uuid.UUID:
    """Brand scope is authorization-derived — never a caller-supplied id alone."""
    if tenant.brand_id is None:
        raise HTTPException(
            status.HTTP_400_BAD_REQUEST,
            "Pick a workspace first, then we can read its Business DNA.",
        )
    return tenant.brand_id


def _economics_facet(econ: economics.EconomicsResolution) -> DnaFacet:
    """Map an economics resolution → the canonical economics DnaFacet. Shared by
    the full DNA build and the facet-scoped accessor so there is ONE economics
    projection."""
    return DnaFacet(
        key="economics",
        title="Business Economics",
        status=_ECON_STATUS_MAP[econ.status],
        provenance_tiers=_tiers(econ.items),
        items=econ.items,
        note=econ.note,
    )


def _tiers(items: list[DnaItem]) -> list[ContextProvenance]:
    distinct = {i.provenance for i in items}
    return sorted(distinct, key=lambda t: _TIER_ORDER[t]) or [ContextProvenance.UNKNOWN]


def _facet(
    key: str,
    title: str,
    items: list[DnaItem],
    *,
    source_present: bool,
    contradictions: list[DnaItem] | None = None,
    note: str | None = None,
    force_unknown: bool = False,
) -> DnaFacet:
    contradictions = contradictions or []
    if force_unknown:
        fstatus = FacetStatus.UNKNOWN
    elif items:
        fstatus = FacetStatus.POPULATED
    elif source_present:
        fstatus = FacetStatus.INSUFFICIENT_EVIDENCE
    else:
        fstatus = FacetStatus.UNKNOWN
    return DnaFacet(
        key=key,
        title=title,
        status=fstatus,
        provenance_tiers=_tiers(items),
        items=items,
        contradictions=contradictions,
        note=note,
    )


def _text_item(label: str, value: object, provenance: ContextProvenance, *, source: str) -> DnaItem | None:
    """One USER_STATED/SYSTEM_INFERRED text item — skipped when the value is empty
    (honest absence, never a fabricated placeholder)."""
    if value is None:
        return None
    text = str(value).strip()
    if not text:
        return None
    return DnaItem(label=label, detail=text, provenance=provenance, source=source)


def _list_item(label: str, values: list | None, provenance: ContextProvenance, *, source: str) -> DnaItem | None:
    vals = [str(v).strip() for v in (values or []) if str(v).strip()]
    if not vals:
        return None
    return DnaItem(label=label, detail=", ".join(vals[:20]), provenance=provenance, source=source)


async def get_business_dna(session: AsyncSession, *, tenant: TenantContext) -> BusinessDna:
    """Compose the canonical Business DNA snapshot for the active tenant brand.

    Raises HTTP 400 when no brand is selected (same contract as Business Brain /
    Marketing Brain). Every optional source is wrapped so one slow/failed read
    degrades that facet to UNKNOWN rather than aborting the snapshot.
    """
    brand_id = _require_brand(tenant)
    generated_at = datetime.now(UTC)

    # --- Reused composition: Marketing Brain (profile + evidence + ICP + research
    #     + analytics + recs + outcomes + strategy + learning + known/unknown). ---
    mb = await mb_service.build_context(session, tenant=tenant)

    # --- Full profile row for the fields the MB snapshot drops (Brand Identity,
    #     USPs, AI analysis narrative). Best-effort; absence → UNKNOWN facets. ---
    profile_row = None
    try:
        profile_row = await onboarding_service.get_profile_or_none(session, brand_id)
    except Exception as e:  # never abort the snapshot for a profile read miss
        log.warning("business_dna.profile_read_failed", error=str(e)[:200])

    # --- Reused shared belief-grounding foundation (confidence + freshness +
    #     contradictions). Defensive: a grounding miss degrades to insufficient. ---
    grounding = None
    try:
        from aicmo.modules.belief.grounding import resolve_evidence_grounding

        _, grounding = await resolve_evidence_grounding(session, tenant=tenant)
    except Exception as e:
        log.warning("business_dna.belief_grounding_failed", error=str(e)[:200])

    # --- Measured audience signals (social). Best-effort. ---
    audience_patterns: list = []
    try:
        from aicmo.modules.social import service as social_service

        audience_patterns = await social_service.list_audience_patterns(
            session, brand_id=brand_id
        )
    except Exception as e:
        log.warning("business_dna.audience_patterns_failed", error=str(e)[:200])

    facets: list[DnaFacet] = []
    profile_present = mb.profile.present

    # ---- 1. Identity --------------------------------------------------------
    identity_items: list[DnaItem] = []
    p = mb.profile
    for label, value in (
        ("Business name", p.business_name),
        ("Website", p.website),
        ("Industry", p.industry),
        ("Business type", p.business_type),
        ("Target audience", p.target_audience),
        ("Location", p.location),
    ):
        item = _text_item(label, value, ContextProvenance.USER_STATED, source="profile")
        if item:
            identity_items.append(item)
    analysis = getattr(profile_row, "analysis", None) if profile_row is not None else None
    if isinstance(analysis, dict):
        summary = _text_item(
            "Business summary (AI analysis)",
            analysis.get("business_summary"),
            ContextProvenance.SYSTEM_INFERRED,
            source="onboarding_analysis",
        )
        if summary:
            identity_items.append(summary)
    facets.append(
        _facet(
            "identity",
            "Identity",
            identity_items,
            source_present=profile_present,
            note=None if profile_present else "No business profile for this brand yet.",
        )
    )

    # ---- 2. Brand Identity (visual + verbal signature) ----------------------
    brand_items: list[DnaItem] = []
    if profile_row is not None:
        bt = _text_item("Brand tone", getattr(profile_row, "brand_tone", None), ContextProvenance.USER_STATED, source="profile")
        if bt:
            brand_items.append(bt)
        for label, attr in (
            ("Brand colours", "brand_colors"),
            ("Fonts", "fonts"),
            ("Keywords", "keywords"),
            ("Brand rules", "brand_rules"),
        ):
            li = _list_item(label, getattr(profile_row, attr, None), ContextProvenance.USER_STATED, source="profile")
            if li:
                brand_items.append(li)
        ws = _text_item("Writing style", getattr(profile_row, "writing_style", None), ContextProvenance.USER_STATED, source="profile")
        if ws:
            brand_items.append(ws)
    facets.append(
        _facet("brand_identity", "Brand Identity", brand_items, source_present=profile_present)
    )

    # ---- 3. Offer & Positioning --------------------------------------------
    offer_items: list[DnaItem] = []
    for label, values in (("Products", p.products), ("Services", p.services)):
        li = _list_item(label, values, ContextProvenance.USER_STATED, source="profile")
        if li:
            offer_items.append(li)
    if profile_row is not None:
        usp = _list_item("Unique selling points", getattr(profile_row, "unique_selling_points", None), ContextProvenance.USER_STATED, source="profile")
        if usp:
            offer_items.append(usp)
    pricing = _text_item("Pricing (owner-stated)", p.pricing, ContextProvenance.USER_STATED, source="profile")
    if pricing:
        offer_items.append(pricing)
    if mb.strategy.present:
        for label, value in (
            ("Positioning", mb.strategy.positioning),
            ("Target summary", mb.strategy.target_summary),
            ("Highest-leverage move", mb.strategy.recommendation),
        ):
            si = _text_item(label, value, ContextProvenance.SYSTEM_INFERRED, source="strategist")
            if si:
                offer_items.append(si)
    facets.append(
        _facet(
            "offer_positioning",
            "Offer & Positioning",
            offer_items,
            source_present=profile_present,
            note=(
                "Owner-stated pricing/budget appear here as USER_STATED context; a "
                "quantitative economics model (CAC/LTV/margin) is deferred to the "
                "economics facet (Phase 7.20 Stage 2)."
            ),
        )
    )

    # ---- 4. Audience / Customer Intelligence --------------------------------
    audience_items: list[DnaItem] = []
    for icp in mb.icps:
        audience_items.append(
            DnaItem(
                label=f"ICP: {icp.name}",
                detail=icp.description[:400],
                provenance=ContextProvenance.SYSTEM_INFERRED,
                confidence=icp.confidence,
                status=icp.status,
                source="business_brain_icp",
            )
        )
    for ap in audience_patterns:
        score = getattr(ap, "confidence_score", None)
        conf = round(float(score) * 100) if isinstance(score, (int, float)) else None
        if conf is not None:
            conf = max(0, min(conf, 100))
        audience_items.append(
            DnaItem(
                label=f"Audience pattern ({getattr(ap, 'pattern_type', 'signal')})",
                detail=getattr(ap, "description", None),
                provenance=ContextProvenance.MEASURED,
                confidence=conf,
                source=f"social:{getattr(ap, 'platform', 'unknown')}",
            )
        )
    if isinstance(analysis, dict):
        for insight in list(analysis.get("audience_insights") or [])[:3]:
            it = _text_item("Audience insight (AI analysis)", insight, ContextProvenance.SYSTEM_INFERRED, source="onboarding_analysis")
            if it:
                audience_items.append(it)
    facets.append(
        _facet(
            "audience",
            "Audience & Customer Intelligence",
            audience_items,
            source_present=profile_present or bool(audience_patterns),
            note=mb.icp_message if mb.icp_status == "INSUFFICIENT_EVIDENCE" else None,
        )
    )

    # ---- 5. Market & Competitors --------------------------------------------
    market_items: list[DnaItem] = []
    for c in mb.research.competitor_candidates:
        market_items.append(
            DnaItem(
                label=f"Competitor: {c.name}",
                detail=c.reason[:300],
                provenance=ContextProvenance.SYSTEM_INFERRED,
                confidence=c.confidence,
                status=c.status,
                source=c.source_url or "competitor_research",
            )
        )
    for s in mb.research.market_signals:
        market_items.append(
            DnaItem(
                label=f"Market signal: {s.signal_kind}",
                detail=s.claim[:300],
                provenance=ContextProvenance.SYSTEM_INFERRED,
                confidence=s.confidence,
                source=s.source_url or s.source_type,
            )
        )
    market_note = None
    if not market_items:
        parts = [m for m in (mb.research.competitor_message, mb.research.market_message) if m]
        market_note = " ".join(parts) if parts else None
    facets.append(
        _facet("market", "Market & Competitors", market_items, source_present=True, note=market_note)
    )

    # ---- 6. Evidence (Business Brain typed claims) --------------------------
    evidence_items: list[DnaItem] = []
    for e in mb.facts:
        evidence_items.append(
            DnaItem(
                label=f"Fact ({e.category})",
                detail=e.claim[:400],
                provenance=ContextProvenance.VERIFIED,
                confidence=e.confidence,
                status=e.status,
                source=e.source_url or e.source_type,
            )
        )
    for bucket, items in (("Observation", mb.observations), ("Hypothesis", mb.hypotheses), ("Evidence recommendation", mb.evidence_recommendations)):
        for e in items:
            evidence_items.append(
                DnaItem(
                    label=f"{bucket} ({e.category})",
                    detail=e.claim[:400],
                    provenance=ContextProvenance.SYSTEM_INFERRED,
                    confidence=e.confidence,
                    status=e.status,
                    source=e.source_url or e.source_type,
                )
            )
    evidence_note_parts = []
    if mb.superseded_excluded_count:
        evidence_note_parts.append(
            f"{mb.superseded_excluded_count} superseded/contradicted evidence row(s) excluded from the active set."
        )
    evidence_note_parts.append(
        "Business Brain evidence is not freshness-decayed at read time in this stage "
        "(freshness applies to beliefs today; see Stage 0 provenance standard, I5)."
    )
    facets.append(
        _facet(
            "evidence",
            "Evidence",
            evidence_items,
            source_present=profile_present,
            note=" ".join(evidence_note_parts),
        )
    )

    # ---- 7. Learned Beliefs (confidence + freshness + contradictions) -------
    belief_items: list[DnaItem] = []
    belief_contradictions: list[DnaItem] = []
    belief_note: str | None = None
    if grounding is not None:
        for b in grounding.beliefs:
            belief_items.append(
                DnaItem(
                    label=f"Belief ({b.category})",
                    detail=b.statement[:400],
                    provenance=ContextProvenance.SYSTEM_INFERRED,
                    confidence=b.confidence,
                    freshness=b.freshness_reason,
                    status=b.status,
                    source=f"belief_memory ({b.evidence_count} evidence)",
                )
            )
        for b in grounding.contradictions:
            belief_contradictions.append(
                DnaItem(
                    label=f"Contradicted belief ({b.category})",
                    detail=b.statement[:400],
                    provenance=ContextProvenance.SYSTEM_INFERRED,
                    confidence=b.confidence,
                    freshness=b.freshness_reason,
                    status="contradicted",
                    source="belief_memory",
                )
            )
        if grounding.status != "grounded":
            belief_note = grounding.note
    else:
        belief_note = "Belief memory was unavailable for this snapshot."
    beliefs_facet = _facet(
        "beliefs",
        "Learned Beliefs",
        belief_items,
        source_present=True,
        contradictions=belief_contradictions,
        note=belief_note,
    )
    facets.append(beliefs_facet)

    # ---- 8. Performance (measured) ------------------------------------------
    perf_items: list[DnaItem] = []
    a = mb.analytics
    if a is not None:
        for label, value in (
            ("Total leads", a.total_leads),
            ("Leads (7d)", a.leads_7d),
            ("Leads (30d)", a.leads_30d),
            ("Hot leads", a.hot_leads),
        ):
            perf_items.append(
                DnaItem(label=label, detail=str(value), provenance=ContextProvenance.MEASURED, source="analytics")
            )
        perf_items.append(
            DnaItem(
                label="Landing-page conversion",
                detail=f"{a.conversion_rate:.1%}",
                provenance=ContextProvenance.MEASURED,
                source="analytics",
            )
        )
    for o in mb.outcomes:
        if o.kind != "evaluated_success":
            continue
        score = round(o.effectiveness_score) if o.effectiveness_score is not None else None
        if score is not None:
            score = max(0, min(score, 100))
        perf_items.append(
            DnaItem(
                label=f"Outcome: {o.title[:80]}",
                detail=o.delta_summary,
                provenance=ContextProvenance.MEASURED,
                confidence=score,
                source=o.source_surface or "advisor_outcome",
            )
        )
    facets.append(
        _facet("performance", "Performance & Measured Outcomes", perf_items, source_present=a is not None)
    )

    # ---- 9. Learning & Recommendation Intelligence --------------------------
    learning_items: list[DnaItem] = []
    for li in mb.learning_insights:
        learning_items.append(
            DnaItem(
                label=f"Lesson ({li.direction}/{li.category})",
                detail=li.observation[:400],
                provenance=ContextProvenance.SYSTEM_INFERRED,
                confidence=li.confidence,
                status=li.status,
                source="learning",
            )
        )
    for r in mb.recommendations[:15]:
        learning_items.append(
            DnaItem(
                label=f"Recommendation: {r.title[:80]}",
                detail=r.expected_result,
                provenance=ContextProvenance.SYSTEM_INFERRED,
                confidence=r.confidence,
                status=r.status,
                source=f"advisor ({r.source_surface})",
            )
        )
    facets.append(
        _facet("learning", "Learning & Recommendation Intelligence", learning_items, source_present=profile_present)
    )

    # ---- 10. Business Economics (Phase 7.20 Stage 2 + 2b) ------------------
    # Deterministic: owner-stated budget/pricing/targets + measured conversion
    # economics + persisted structured inputs, with margin/LTV/break-even computed
    # when their inputs exist and INSUFFICIENT_EVIDENCE otherwise. Reuses the
    # profile row + analytics already fetched above (no extra reads).
    stored_economics = economics_store.economics_from_row(profile_row)
    econ = economics.resolve_economics(
        profile_row=profile_row, analytics=mb.analytics, economics=stored_economics
    )
    facets.append(_economics_facet(econ))

    # Deterministic facet ordering.
    facets.sort(key=lambda f: _FACET_ORDER.index(f.key))

    limitations = list(mb.limitations)
    limitations.append(
        "Business Economics computes margin/LTV/break-even deterministically from "
        "persisted inputs when present; CAC and budget utilization remain "
        "INSUFFICIENT_EVIDENCE until a provider-verified spend source is connected."
    )
    limitations.append(
        "The legacy competitors module is not consulted here; market facts come "
        "from the evidence-grounded Business Brain research path."
    )

    return BusinessDna(
        brand_id=brand_id,
        organization_id=tenant.organization_id,
        generated_at=generated_at,
        facets=facets,
        known=list(mb.known),
        unknown=list(mb.unknown),
        provenance_legend=dict(PROVENANCE_LEGEND),
        limitations=limitations,
    )


async def get_economics_facet(session: AsyncSession, *, tenant: TenantContext) -> DnaFacet:
    """Read-only Business Economics facet ALONE — the "request only the facet you
    need" seam (Phase 7.20 Stage 3) for consumers that want economics context
    without building the full Business DNA.

    Reuses the canonical economics resolver + store; it does NOT build the full
    Marketing Brain context, so it is cheap (one scoped profile read) and avoids
    duplicate heavy composition. Brand-scoped via the caller's TenantContext;
    read-only; deterministic; never writes. ``analytics`` is intentionally omitted
    (consumers surface analytics separately) so this adds no analytics read.
    """
    brand_id = _require_brand(tenant)
    profile_row = None
    try:
        profile_row = await onboarding_service.get_profile_or_none(session, brand_id)
    except Exception as e:  # never abort a consumer for a profile read miss
        log.warning("business_dna.economics_facet_profile_failed", error=str(e)[:200])
    stored = economics_store.economics_from_row(profile_row)
    econ = economics.resolve_economics(profile_row=profile_row, analytics=None, economics=stored)
    return _economics_facet(econ)
