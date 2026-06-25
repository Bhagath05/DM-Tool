"""Performance service — Phase 9.1 orchestration.

Brand-scoped. Wires the pure-function modules (csv_parser, diagnostics,
recommender) to the DB.

Three public entry points:

  - ingest_csv(session, tenant, payload, filename) -> CsvIngestSummary
       Parse + persist raw events, fuzzy-match creatives, recompute
       the rollup cube, run the diagnostic rules, persist new cards.

  - overview(session, tenant) -> PerformanceOverview
       Read-only payload for the founder dashboard.

  - dismiss_diagnostic(session, tenant, diagnostic_id) -> None
       Founder clicked "not useful". We don't delete (audit trail);
       we flip status so it stops surfacing.

Constitution discipline:
  - We never insert a diagnostic with confidence < 40 (Speculative).
  - We never surface a fabricated rollup (sample_state gates input).
  - If no diagnostic rules fire, overview() returns has_data=True but
    diagnostics=[]; the dashboard surfaces a ComingSoonCard.
"""

from __future__ import annotations

import uuid
from collections import defaultdict
from datetime import datetime
from difflib import SequenceMatcher

from sqlalchemy import delete, desc, func, select
from sqlalchemy.ext.asyncio import AsyncSession

from aicmo.modules.ads.models import GeneratedAd
from aicmo.modules.content.models import GeneratedContent
from aicmo.modules.performance import diagnostics as diag_rules
from aicmo.modules.performance import recommender
from aicmo.modules.performance.csv_parser import ParseResult, parse_csv
from aicmo.modules.performance.models import (
    CreativeResult,
    PerformanceDiagnostic,
    PerformanceEvent,
)
from aicmo.modules.performance.schemas import (
    CreativeRollup,
    CsvIngestRow,
    CsvIngestSummary,
    PerformanceDiagnosticCard,
    PerformanceOverview,
)
from aicmo.modules.visuals.models import GeneratedVisual
from aicmo.tenancy.context import TenantContext


# ---------------------------------------------------------------------
#  Sample-state thresholds — keep in lock-step with diagnostics.py
# ---------------------------------------------------------------------

MIN_IMPRESSIONS = diag_rules.MIN_IMPRESSIONS
MIN_SPEND_MICROS = diag_rules.MIN_SPEND_MICROS
MIN_CONVERSIONS = diag_rules.MIN_CONVERSIONS

FUZZY_MATCH_FLOOR = 0.78  # SequenceMatcher ratio


# ---------------------------------------------------------------------
#  Helpers
# ---------------------------------------------------------------------


def compute_sample_state(
    *, impressions: int, spend_micros: int, conversions: int
) -> str:
    """Return 'sufficient' iff all three thresholds pass."""
    if impressions < MIN_IMPRESSIONS:
        return "insufficient"
    if spend_micros < MIN_SPEND_MICROS:
        return "insufficient"
    if conversions < MIN_CONVERSIONS:
        return "insufficient"
    return "sufficient"


def _norm(s: str) -> str:
    return s.strip().lower()


def _best_match(
    creative_ref: str,
    candidates: list[tuple[str, str, uuid.UUID, dict]],
) -> tuple[str, uuid.UUID, dict] | None:
    """Fuzzy-match the CSV's creative_ref against this brand's
    generated creatives. Returns (asset_type, asset_id, tag_dict)
    or None.

    `candidates` is [(asset_type, name, asset_id, tags), ...].
    """
    if not candidates:
        return None
    target = _norm(creative_ref)
    best: tuple[float, str, uuid.UUID, dict] | None = None
    for asset_type, name, asset_id, tags in candidates:
        if not name:
            continue
        # Exact match short-circuits — no ratio needed.
        if _norm(name) == target:
            return asset_type, asset_id, tags
        ratio = SequenceMatcher(None, target, _norm(name)).ratio()
        if best is None or ratio > best[0]:
            best = (ratio, asset_type, asset_id, tags)
    if best is None or best[0] < FUZZY_MATCH_FLOOR:
        return None
    return best[1], best[2], best[3]


def _tags_from_visual(row: GeneratedVisual) -> dict:
    return {
        "concept_family": row.concept_family,
        "emotion": row.emotion,
        "audience": row.audience,
        "funnel_stage": row.funnel_stage,
        "business_goal": row.business_goal,
        "offer_type": row.offer_type,
    }


def _tags_from_content(row: GeneratedContent) -> dict:
    return {
        "concept_family": row.concept_family,
        "emotion": row.emotion,
        "audience": row.audience,
        "funnel_stage": row.funnel_stage,
        "business_goal": row.business_goal,
        "offer_type": row.offer_type,
    }


def _tags_from_ad(row: GeneratedAd) -> dict:
    return {
        "concept_family": row.concept_family,
        "emotion": row.emotion,
        "audience": row.audience,
        "funnel_stage": row.funnel_stage,
        "business_goal": row.business_goal,
        "offer_type": row.offer_type,
    }


async def _load_match_candidates(
    session: AsyncSession, brand_id: uuid.UUID
) -> list[tuple[str, str, uuid.UUID, dict]]:
    """Collect (asset_type, displayable_name, asset_id, tags) for every
    creative the brand has generated. We derive the displayable name
    from the strategy/output blob — there is no first-class 'name'
    column on the existing tables."""
    out: list[tuple[str, str, uuid.UUID, dict]] = []

    # Visuals.
    visuals_q = await session.execute(
        select(GeneratedVisual).where(GeneratedVisual.brand_id == brand_id)
    )
    for v in visuals_q.scalars():
        name = _name_of_visual(v)
        if name:
            out.append(("visual", name, v.id, _tags_from_visual(v)))

    # Content.
    content_q = await session.execute(
        select(GeneratedContent).where(GeneratedContent.brand_id == brand_id)
    )
    for c in content_q.scalars():
        name = _name_of_content(c)
        if name:
            out.append(("content", name, c.id, _tags_from_content(c)))

    # Ads.
    ads_q = await session.execute(
        select(GeneratedAd).where(GeneratedAd.brand_id == brand_id)
    )
    for a in ads_q.scalars():
        name = _name_of_ad(a)
        if name:
            out.append(("ad", name, a.id, _tags_from_ad(a)))

    return out


def _name_of_visual(v: GeneratedVisual) -> str | None:
    """Pick the best display name from a visual's strategy/output."""
    out = v.output or {}
    for k in ("title", "headline", "hook", "concept", "name"):
        val = out.get(k)
        if isinstance(val, str) and val.strip():
            return val.strip()
    strat = v.strategy or {}
    val = strat.get("audience_angle") or strat.get("hook") or strat.get("title")
    if isinstance(val, str) and val.strip():
        return val.strip()
    return None


def _name_of_content(c: GeneratedContent) -> str | None:
    out = c.output or {}
    for k in ("title", "headline", "hook", "caption", "name"):
        val = out.get(k)
        if isinstance(val, str) and val.strip():
            return val.strip()
    return None


def _name_of_ad(a: GeneratedAd) -> str | None:
    out = a.output or {}
    for k in ("title", "headline", "primary_text", "name"):
        val = out.get(k)
        if isinstance(val, str) and val.strip():
            return val.strip()
    return None


# ---------------------------------------------------------------------
#  Public: ingest_csv
# ---------------------------------------------------------------------


async def ingest_csv(
    session: AsyncSession,
    *,
    tenant: TenantContext,
    payload: str,
    filename: str | None = None,
    brand_default_currency: str | None = None,
) -> CsvIngestSummary:
    """Parse a CSV blob, persist accepted rows, refresh rollups, run
    diagnostics, persist new diagnostic cards. Returns a per-upload
    summary the founder sees in the UI."""
    parsed: ParseResult = parse_csv(
        payload, brand_default_currency=brand_default_currency
    )

    upload_id = uuid.uuid4()
    candidates = await _load_match_candidates(session, tenant.brand_id)

    matched = 0
    unmatched = 0
    accepted_seen_refs: set[str] = set()

    for row in parsed.accepted:
        match = _best_match(row.creative_ref, candidates)
        if match is None:
            asset_type = asset_id = None
            unmatched += 1 if row.creative_ref not in accepted_seen_refs else 0
        else:
            asset_type, asset_id, _tags = match
            matched += 1 if row.creative_ref not in accepted_seen_refs else 0
        accepted_seen_refs.add(row.creative_ref)

        session.add(
            PerformanceEvent(
                organization_id=tenant.organization_id,
                brand_id=tenant.brand_id,
                upload_id=upload_id,
                event_date=row.event_date,
                platform=row.platform,
                creative_ref=row.creative_ref,
                matched_asset_type=asset_type,
                matched_asset_id=asset_id,
                impressions=row.impressions,
                clicks=row.clicks,
                conversions=row.conversions,
                spend_micros=row.spend_micros,
                conversion_value_micros=row.conversion_value_micros,
                currency=row.currency,
                source_filename=filename,
            )
        )

    await session.flush()

    # Recompute rollups + diagnostics from scratch. Phase 9.1 keeps
    # this simple: blow away the brand's cube and rewrite it from the
    # full event history. Cheap at MVP scale; we can switch to
    # incremental updates when volume justifies it.
    await _recompute_rollups(session, brand_id=tenant.brand_id)
    await _refresh_diagnostics(session, tenant=tenant)

    await session.commit()

    return CsvIngestSummary(
        upload_id=upload_id,
        rows_accepted=len(parsed.accepted),
        rows_rejected=len(parsed.errors),
        creatives_matched=matched,
        creatives_unmatched=unmatched,
        date_range=parsed.date_range,
        currency=parsed.currency,
        errors=parsed.errors,
    )


# ---------------------------------------------------------------------
#  Rollups
# ---------------------------------------------------------------------


async def _recompute_rollups(
    session: AsyncSession, *, brand_id: uuid.UUID
) -> None:
    """Blow away and rewrite `creative_results` for the brand.

    Tag snapshot is taken at write time from the matched asset (if
    any) so the cube doesn't have to re-resolve them later.
    """
    # Wipe existing rollups for this brand. Idempotent re-import safe.
    await session.execute(
        delete(CreativeResult).where(CreativeResult.brand_id == brand_id)
    )

    events_q = await session.execute(
        select(PerformanceEvent).where(PerformanceEvent.brand_id == brand_id)
    )
    events = list(events_q.scalars())
    if not events:
        return

    # Group by (creative_ref, platform) — the natural cube key.
    groups: dict[tuple[str, str], list[PerformanceEvent]] = defaultdict(list)
    for ev in events:
        groups[(ev.creative_ref, ev.platform)].append(ev)

    # Pre-load tag candidates once for the brand.
    tag_map = await _build_tag_map(session, brand_id)

    for (ref, platform), evs in groups.items():
        impressions = sum(e.impressions for e in evs)
        clicks = sum(e.clicks for e in evs)
        conversions = sum(e.conversions for e in evs)
        spend_micros = sum(e.spend_micros for e in evs)
        conv_value_micros = sum(e.conversion_value_micros for e in evs)
        first_seen = min(e.event_date for e in evs)
        last_seen = max(e.event_date for e in evs)

        # Currency: take the most common across events for this ref —
        # warns implicitly if mixed by picking one.
        currencies = [e.currency for e in evs]
        currency = max(set(currencies), key=currencies.count)

        sample_state = compute_sample_state(
            impressions=impressions,
            spend_micros=spend_micros,
            conversions=conversions,
        )

        # Tag resolution: prefer event match, fall back to ref-based.
        matched = next(
            ((e.matched_asset_type, e.matched_asset_id) for e in evs if e.matched_asset_id),
            (None, None),
        )
        tags = tag_map.get((matched[0], matched[1])) if matched[1] else None

        # First brand's org_id — same for every event under this brand
        # because TenantMixin guarantees consistency.
        org_id = evs[0].organization_id

        session.add(
            CreativeResult(
                organization_id=org_id,
                brand_id=brand_id,
                creative_ref=ref,
                platform=platform,
                matched_asset_type=matched[0],
                matched_asset_id=matched[1],
                concept_family=(tags or {}).get("concept_family"),
                emotion=(tags or {}).get("emotion"),
                audience=(tags or {}).get("audience"),
                funnel_stage=(tags or {}).get("funnel_stage"),
                business_goal=(tags or {}).get("business_goal"),
                offer_type=(tags or {}).get("offer_type"),
                impressions=impressions,
                clicks=clicks,
                conversions=conversions,
                spend_micros=spend_micros,
                conversion_value_micros=conv_value_micros,
                currency=currency,
                first_seen=first_seen,
                last_seen=last_seen,
                sample_state=sample_state,
            )
        )


async def _build_tag_map(
    session: AsyncSession, brand_id: uuid.UUID
) -> dict[tuple[str, uuid.UUID], dict]:
    """Pre-load (asset_type, asset_id) -> tag dict for the brand."""
    tag_map: dict[tuple[str, uuid.UUID], dict] = {}

    vq = await session.execute(
        select(GeneratedVisual).where(GeneratedVisual.brand_id == brand_id)
    )
    for v in vq.scalars():
        tag_map[("visual", v.id)] = _tags_from_visual(v)

    cq = await session.execute(
        select(GeneratedContent).where(GeneratedContent.brand_id == brand_id)
    )
    for c in cq.scalars():
        tag_map[("content", c.id)] = _tags_from_content(c)

    aq = await session.execute(
        select(GeneratedAd).where(GeneratedAd.brand_id == brand_id)
    )
    for a in aq.scalars():
        tag_map[("ad", a.id)] = _tags_from_ad(a)

    return tag_map


# ---------------------------------------------------------------------
#  Diagnostics
# ---------------------------------------------------------------------


async def _refresh_diagnostics(
    session: AsyncSession, *, tenant: TenantContext
) -> None:
    """Replace all open diagnostics for the brand with a fresh set.

    Phase 9.1 keeps this simple: any 'open' card for the brand is
    superseded on every ingest. acted_on / dismissed cards are
    preserved as audit history.
    """
    rollups = await _load_rollups(session, brand_id=tenant.brand_id)
    drafts = diag_rules.diagnose(rollups)

    # Expire prior open cards so the founder doesn't see two of the
    # same kind after re-uploading a refreshed CSV.
    await session.execute(
        PerformanceDiagnostic.__table__.update()
        .where(PerformanceDiagnostic.brand_id == tenant.brand_id)
        .where(PerformanceDiagnostic.status == "open")
        .values(status="expired", resolved_at=datetime.utcnow())
    )

    for draft in drafts:
        # Compose words from the draft — same path tests pin.
        what, why, rec, expected, reason = recommender.compose(draft)
        session.add(
            PerformanceDiagnostic(
                organization_id=tenant.organization_id,
                brand_id=tenant.brand_id,
                kind=draft.kind,
                impact_category=draft.impact_category,
                what_happened=what,
                why=why,
                recommendation=rec,
                expected_result=expected,
                reason=reason,
                confidence=draft.confidence,
                evidence=draft.evidence,
                status="open",
            )
        )


async def _load_rollups(
    session: AsyncSession, *, brand_id: uuid.UUID
) -> list[CreativeRollup]:
    q = await session.execute(
        select(CreativeResult).where(CreativeResult.brand_id == brand_id)
    )
    out: list[CreativeRollup] = []
    for r in q.scalars():
        out.append(
            CreativeRollup(
                creative_ref=r.creative_ref,
                platform=r.platform,  # type: ignore[arg-type]
                matched_asset_type=r.matched_asset_type,
                matched_asset_id=r.matched_asset_id,
                concept_family=r.concept_family,
                emotion=r.emotion,
                audience=r.audience,
                funnel_stage=r.funnel_stage,  # type: ignore[arg-type]
                business_goal=r.business_goal,
                offer_type=r.offer_type,  # type: ignore[arg-type]
                impressions=r.impressions,
                clicks=r.clicks,
                conversions=r.conversions,
                spend_micros=r.spend_micros,
                conversion_value_micros=r.conversion_value_micros,
                currency=r.currency,
                first_seen=r.first_seen,
                last_seen=r.last_seen,
                sample_state=r.sample_state,  # type: ignore[arg-type]
            )
        )
    return out


# ---------------------------------------------------------------------
#  Public: overview
# ---------------------------------------------------------------------


async def overview(
    session: AsyncSession, *, tenant: TenantContext
) -> PerformanceOverview:
    rows_count = (
        await session.execute(
            select(func.count(PerformanceEvent.id)).where(
                PerformanceEvent.brand_id == tenant.brand_id
            )
        )
    ).scalar_one()
    creatives_count = (
        await session.execute(
            select(func.count(CreativeResult.id)).where(
                CreativeResult.brand_id == tenant.brand_id
            )
        )
    ).scalar_one()
    last_upload = (
        await session.execute(
            select(func.max(PerformanceEvent.created_at)).where(
                PerformanceEvent.brand_id == tenant.brand_id
            )
        )
    ).scalar_one()

    diag_q = await session.execute(
        select(PerformanceDiagnostic)
        .where(PerformanceDiagnostic.brand_id == tenant.brand_id)
        .where(PerformanceDiagnostic.status == "open")
        .order_by(desc(PerformanceDiagnostic.confidence), desc(PerformanceDiagnostic.created_at))
    )
    cards = [
        PerformanceDiagnosticCard.model_validate(d) for d in diag_q.scalars()
    ]

    return PerformanceOverview(
        has_data=rows_count > 0,
        rows_ingested=rows_count,
        creatives_tracked=creatives_count,
        last_upload_at=last_upload,
        diagnostics=cards,
    )


# ---------------------------------------------------------------------
#  Public: dismiss
# ---------------------------------------------------------------------


async def dismiss_diagnostic(
    session: AsyncSession,
    *,
    tenant: TenantContext,
    diagnostic_id: uuid.UUID,
) -> bool:
    """Mark a single diagnostic as dismissed. Returns True if a row
    was updated. Safe against cross-tenant access (brand_id filter)."""
    result = await session.execute(
        PerformanceDiagnostic.__table__.update()
        .where(PerformanceDiagnostic.id == diagnostic_id)
        .where(PerformanceDiagnostic.brand_id == tenant.brand_id)
        .where(PerformanceDiagnostic.status == "open")
        .values(status="dismissed", resolved_at=datetime.utcnow())
    )
    await session.commit()
    return bool(result.rowcount)


# ---------------------------------------------------------------------
#  Public: reset
# ---------------------------------------------------------------------


async def reset_brand_data(
    session: AsyncSession,
    *,
    tenant: TenantContext,
) -> None:
    """Delete ALL ingested performance data for the active brand.

    Wipes `performance_events`, `creative_results`, and
    `performance_diagnostics` rows scoped by `brand_id`. Idempotent —
    safe to call on a brand with no data. Deletion order honors the
    dependency direction (diagnostics ← rollups ← events) but since
    there are no FKs between these tables, the order is mainly for
    readability.

    Generated-creative tags on `generated_visuals` / `generated_ads`
    / `generated_content` are NOT touched — only the uploaded-CSV-
    derived data is removed. The tags are useful even without perf
    data attached.
    """
    bid = tenant.brand_id
    await session.execute(
        delete(PerformanceDiagnostic).where(PerformanceDiagnostic.brand_id == bid)
    )
    await session.execute(
        delete(CreativeResult).where(CreativeResult.brand_id == bid)
    )
    await session.execute(
        delete(PerformanceEvent).where(PerformanceEvent.brand_id == bid)
    )
    await session.commit()
