"""AI-vs-human creative evaluation — data gathering + recommendation shaping.

Thin integration layer over the pure `marketing_analytics.creative_evaluation`
core: it loads the brand's real performance records (tenant-scoped), resolves
each one's AI/human provenance, runs the deterministic evaluator, and shapes an
evidence-first recommendation. When the verdict is actionable it can persist an
`AdvisorRecommendation` through the existing (audited) recommendation path so it
flows into the existing outcome/effectiveness learning loop.

It NEVER publishes or spends. The verdict is advisory; `human_approval_required`
is always True and confidence never unlocks execution — execution stays behind
the existing approval gates.
"""

from __future__ import annotations

import uuid
from datetime import UTC, datetime

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from aicmo.modules.advisor.models import AdvisorRecommendation
from aicmo.modules.advisor.schemas import (
    CreativeEvaluationResponse,
    CreativeMetricDelta,
)
from aicmo.modules.advisor.service import _upsert_recommendation
from aicmo.modules.marketing_analytics.creative_evaluation import (
    CreativeEvaluation,
    CreativeSample,
    Provenance,
    Verdict,
    evaluate_ai_vs_human,
)
from aicmo.modules.publishing.models import ContentAsset, ScheduledPost
from aicmo.modules.social.models import PerformanceSignal, SocialAsset
from aicmo.tenancy.context import TenantContext

# ContentAsset.source_table values produced by our own AI generators. A post
# whose content traces back to one of these is AI-provenance. We do NOT infer
# "human" from the absence of these — human is only asserted from an explicit
# label, so we never mislabel an unknown post as human.
_AI_SOURCE_TABLES = frozenset({"generated_content", "generated_ads", "generated_visuals"})

# The alternatives the advisor surfaces when AI creative is underperforming —
# never "just generate more AI".
_HUMAN_ALTERNATIVES = [
    "Commission human creators / influencers for UGC",
    "Hire a photographer or videographer for a batch of assets",
    "Brief professional models for the hero creative",
    "Test a different creative format (e.g. testimonial, demo, founder-to-camera)",
    "Run a human-created control against the next AI batch",
]

_METRIC_FIELDS = ("views", "engagement_rate", "ctr", "watch_time_seconds", "reach")


def resolve_provenance(*, explicit: str | None, source_table: str | None) -> Provenance:
    """Pure provenance resolution. Explicit label wins; otherwise derive AI from
    a known AI source table. Anything we cannot positively attribute is UNKNOWN
    (excluded from comparisons) — provenance is never guessed as human."""
    label = (explicit or "").strip().lower()
    if label in ("ai", "human"):
        return Provenance(label)
    if source_table in _AI_SOURCE_TABLES:
        return Provenance.AI
    return Provenance.UNKNOWN


async def _load_provenance_map(session: AsyncSession, *, brand_id: uuid.UUID) -> dict[str, str]:
    """platform_post_id -> ContentAsset.source_table, for posts we published
    ourselves (the only ones whose origin we can trace)."""
    rows = (
        await session.execute(
            select(ScheduledPost.platform_post_id, ContentAsset.source_table)
            .join(ContentAsset, ScheduledPost.content_asset_id == ContentAsset.id)
            .where(
                ScheduledPost.brand_id == brand_id,
                ScheduledPost.platform_post_id.is_not(None),
            )
        )
    ).all()
    return {ppid: src for (ppid, src) in rows if ppid}


async def _load_samples(session: AsyncSession, *, brand_id: uuid.UUID) -> list[CreativeSample]:
    assets = (
        (await session.execute(select(SocialAsset).where(SocialAsset.brand_id == brand_id)))
        .scalars()
        .all()
    )
    if not assets:
        return []

    # Latest performance signal per asset (metrics snapshot).
    asset_ids = [a.id for a in assets]
    signals = (
        (
            await session.execute(
                select(PerformanceSignal)
                .where(PerformanceSignal.asset_id.in_(asset_ids))
                .order_by(PerformanceSignal.captured_at.asc())
            )
        )
        .scalars()
        .all()
    )
    latest: dict[uuid.UUID, PerformanceSignal] = {}
    for sig in signals:  # ascending → last write wins = latest
        latest[sig.asset_id] = sig

    prov_map = await _load_provenance_map(session, brand_id=brand_id)

    samples: list[CreativeSample] = []
    for a in assets:
        sig = latest.get(a.id)
        if sig is None:
            continue  # no measured performance yet — nothing to compare
        metrics: dict[str, float] = {}
        for f in _METRIC_FIELDS:
            v = getattr(sig, f, None)
            if v is not None and v != 0:
                metrics[f] = float(v)
        if not metrics:
            continue
        provenance = resolve_provenance(
            explicit=a.creative_provenance,
            source_table=prov_map.get(a.platform_post_id),
        )
        # Provider-collected assets carry an integration connection; fixture /
        # manually-seeded rows do not. This is the "provider-verified" signal.
        source = "provider" if a.integration_connection_id is not None else "local"
        samples.append(
            CreativeSample(
                provenance=provenance,
                metrics=metrics,
                platform=a.platform,
                fmt=a.asset_type,
                posted_at=a.posted_at,
                ref=str(a.id),
                source=source,
            )
        )
    return samples


def _evidence_source(samples: list[CreativeSample]) -> str:
    """Label the evidence behind a verdict: provider-verified if any comparable
    (AI/human) sample came from a connected account, else local/fixture, else
    none. Never lets fixture data masquerade as live provider data."""
    known = [s for s in samples if s.provenance in (Provenance.AI, Provenance.HUMAN)]
    if not known:
        return "none"
    if any(s.source == "provider" for s in known):
        return "provider_verified"
    return "local_only"


# ---------------------------------------------------------------------
#  Recommendation shaping (verdict -> constitution-complete recommendation)
# ---------------------------------------------------------------------


def _join(labels: list[str]) -> str:
    if not labels:
        return ""
    if len(labels) == 1:
        return labels[0]
    return f"{', '.join(labels[:-1])} and {labels[-1]}"


def _significant_labels(ev: CreativeEvaluation, *, ai_better: bool) -> list[str]:
    """The metric labels that were BOTH significant and won by the given side —
    so a diagnosis names exactly the dimensions the evidence supports and never
    implies (e.g.) a revenue effect that wasn't measured."""
    return [d.label for d in ev.metric_deltas if d.significant and d.ai_better is ai_better]


def _diagnosis(ev: CreativeEvaluation) -> str:
    n = f"{ev.ai_sample_size} AI-generated vs {ev.human_sample_size} human-created comparable posts"
    match ev.verdict:
        case Verdict.AI_UNDERPERFORMING:
            scope = _join(_significant_labels(ev, ai_better=False))
            on = f" on {scope}" if scope else ""
            return (
                f"AI-generated creative is underperforming the human-created baseline{on} ({n}). "
                "This is an observed performance gap on the measured metrics, not a proven revenue effect."
            )
        case Verdict.HUMAN_OUTPERFORMING:
            scope = _join(_significant_labels(ev, ai_better=False))
            on = f" on {scope}" if scope else ""
            return f"Human-created creative is decisively outperforming AI-generated creative{on} ({n})."
        case Verdict.AI_OUTPERFORMING:
            scope = _join(_significant_labels(ev, ai_better=True))
            on = f" on {scope}" if scope else ""
            return f"AI-generated creative is outperforming the human-created baseline{on} ({n})."
        case Verdict.NO_SIGNIFICANT_DIFFERENCE:
            return f"No significant performance difference between AI-generated and human-created creative ({n})."
        case _:
            return "There isn't enough comparable, provenance-labelled performance data to judge AI vs human creative yet."


def _action_and_alternatives(ev: CreativeEvaluation) -> tuple[str, list[str]]:
    if ev.verdict in (Verdict.AI_UNDERPERFORMING, Verdict.HUMAN_OUTPERFORMING):
        return (
            "Test human creators / professional UGC before increasing AI-video production. "
            "Do not scale AI creative while it trails the human baseline.",
            list(_HUMAN_ALTERNATIVES),
        )
    if ev.verdict is Verdict.AI_OUTPERFORMING:
        return (
            "Keep producing AI creative variations, and run one human-created control "
            "against the next batch to confirm the advantage holds.",
            [
                "Keep a human-created control in every test",
                "Vary the AI creative concept to avoid fatigue",
            ],
        )
    if ev.verdict is Verdict.NO_SIGNIFICANT_DIFFERENCE:
        return (
            "No clear winner — choose on cost and speed, and keep a human-created control running.",
            [
                "Decide by production cost / turnaround",
                "Keep a human-created control",
                "Re-evaluate after more data",
            ],
        )
    return (
        "Collect more comparable, provenance-labelled performance data before shifting creative strategy. "
        "Do not increase AI production purely because it is cheap to generate.",
        [
            "Label existing posts as AI or human",
            "Publish a small human-created test batch",
            "Connect platforms so metrics sync",
        ],
    )


def _expected_impact(ev: CreativeEvaluation) -> str:
    if ev.verdict in (Verdict.AI_UNDERPERFORMING, Verdict.HUMAN_OUTPERFORMING):
        worst = [d for d in ev.metric_deltas if d.significant and not d.ai_better]
        if worst:
            span = ", ".join(
                f"{d.label} {abs(d.relative_delta) * 100:.0f}% higher" for d in worst[:3]
            )
            return f"A human-created test could recover the gap where AI trails ({span}), based on the observed baseline."
        return "A human-created test could recover the observed performance gap."
    if ev.verdict is Verdict.AI_OUTPERFORMING:
        return "Continuing AI creative should hold the observed advantage; the human control quantifies it."
    if ev.verdict is Verdict.NO_SIGNIFICANT_DIFFERENCE:
        return "Either source performs comparably; expected impact of switching is roughly neutral on current evidence."
    return "Expected impact cannot be estimated until there is enough comparable evidence."


def _assumptions(ev: CreativeEvaluation) -> list[str]:
    return [
        "Provenance labels (AI vs human) are correct for the compared posts.",
        "The compared cohorts are otherwise similar (platform, format, audience, timing).",
        "The latest performance snapshot per post is representative.",
    ]


def _risks(ev: CreativeEvaluation) -> list[str]:
    risks = [
        "This is an observed relationship, not proven causation.",
        "Small sample sizes can move the verdict as more data arrives.",
    ]
    if any("revenue" in lim.lower() or "cost" in lim.lower() for lim in ev.limitations):
        risks.append(
            "Verdict is based on engagement/reach signals; revenue/CAC impact is not yet measured per creative."
        )
    return risks


def shape_response(
    ev: CreativeEvaluation, *, evidence_source: str = "none"
) -> CreativeEvaluationResponse:
    action, alternatives = _action_and_alternatives(ev)
    return CreativeEvaluationResponse(
        verdict=ev.verdict.value,
        confidence=ev.confidence,
        evidence_source=evidence_source,  # type: ignore[arg-type]
        ai_sample_size=ev.ai_sample_size,
        human_sample_size=ev.human_sample_size,
        unknown_sample_size=ev.unknown_sample_size,
        diagnosis=_diagnosis(ev),
        recommended_action=action,
        expected_impact=_expected_impact(ev),
        alternatives=alternatives,
        assumptions=_assumptions(ev),
        risks=_risks(ev),
        evidence=ev.evidence,
        evidence_limitations=ev.limitations,
        metric_deltas=[
            CreativeMetricDelta(
                metric=d.metric,
                label=d.label,
                ai_value=d.ai_value,
                human_value=d.human_value,
                relative_delta=d.relative_delta,
                ai_better=d.ai_better,
                significant=d.significant,
            )
            for d in ev.metric_deltas
        ],
        human_approval_required=True,
        generated_at=datetime.now(UTC).isoformat(),
    )


async def evaluate_creative(
    session: AsyncSession, *, tenant: TenantContext
) -> CreativeEvaluationResponse:
    """Read-only: gather real data, resolve provenance, evaluate, and shape the
    evidence-first recommendation. Never writes, never executes."""
    if tenant.brand_id is None:
        # Brand-scoped analysis needs a brand; fail honest, never guess.
        return shape_response(
            CreativeEvaluation(
                verdict=Verdict.INSUFFICIENT_EVIDENCE,
                confidence=0,
                ai_sample_size=0,
                human_sample_size=0,
                unknown_sample_size=0,
                evidence=[],
                limitations=["No brand selected — pick a brand to evaluate its creative."],
            )
        )
    samples = await _load_samples(session, brand_id=tenant.brand_id)
    evaluation = evaluate_ai_vs_human(samples)
    return shape_response(evaluation, evidence_source=_evidence_source(samples))


# Everything EXCEPT insufficient evidence is actionable: a clear winner, or —
# for NO_SIGNIFICANT_DIFFERENCE — a "run a controlled test" recommendation.
# INSUFFICIENT_EVIDENCE is never persisted, so we never fabricate a conclusion.
_ACTIONABLE = {
    Verdict.AI_UNDERPERFORMING,
    Verdict.HUMAN_OUTPERFORMING,
    Verdict.AI_OUTPERFORMING,
    Verdict.NO_SIGNIFICANT_DIFFERENCE,
}


async def record_creative_recommendation(
    session: AsyncSession, *, tenant: TenantContext, response: CreativeEvaluationResponse
) -> AdvisorRecommendation | None:
    """Persist an actionable verdict as an AdvisorRecommendation via the existing
    (audited, tenant-scoped) path so it enters the outcome/effectiveness loop.

    Returns None for INSUFFICIENT_EVIDENCE — we never create a task from a
    conclusion the data can't support. Every other verdict is a real, honest
    recommendation (a clear winner, or a controlled test when there's no
    significant difference). The recommendation is created with status
    'not_started'; execution still flows through the existing approval gates,
    so a high confidence never bypasses human approval.

    Durability (H1): `get_db()` does not auto-commit, and the deterministic
    LLM-fallback path in `compose_intelligence()` returns without
    `_persist_intelligence()`'s commit. Persistence therefore uses a dedicated
    short-lived `SessionLocal` write session so we never
    `commit()` the caller's request session (which may already carry unrelated
    tenancy dirtiness such as `last_active_brand_id`). After commit, the row is
    re-loaded on the caller's session (no commit) so callers can still mutate
    scalar fields (e.g. human rejection) on that session.
    """
    from aicmo.db.session import SessionLocal

    if response.verdict not in {v.value for v in _ACTIONABLE}:
        return None
    fingerprint = f"creative_eval:{tenant.brand_id}:{response.verdict}"
    rec_id = uuid.uuid5(uuid.NAMESPACE_URL, fingerprint)
    source_label = {
        "provider_verified": "Provider-verified (metrics from a connected account)",
        "local_only": "Local/fixture evidence (no connected account yet)",
        "none": "No comparable evidence",
    }
    data_used = [
        {
            "key": "evidence_source",
            "label": "Evidence source",
            "value": source_label.get(response.evidence_source, response.evidence_source),
        },
        *({"key": "evidence", "label": "Evidence", "value": e} for e in response.evidence[:5]),
    ]
    async with SessionLocal() as write_session:
        await _upsert_recommendation(
            write_session,
            tenant=tenant,
            rec_id=rec_id,
            fingerprint=fingerprint,
            title="AI-vs-human creative performance",
            description=response.recommended_action,
            source_surface="creative_evaluation",
            confidence=response.confidence,
            impact_category="revenue",
            why=response.diagnosis,
            expected_result=response.expected_impact,
            data_used=data_used,
            generator_hint=None,
            observation=response.diagnosis,
            root_cause=" ".join(response.evidence[:2]) or None,
        )
        await write_session.commit()

    # Re-attach on the request session for callers that mutate scalars later.
    # Does not commit `session`.
    return await session.get(AdvisorRecommendation, rec_id)


async def generate_creative_recommendation(
    session: AsyncSession, *, tenant: TenantContext
) -> CreativeEvaluationResponse:
    """Advisor-workflow entry point: evaluate AI-vs-human creative and, when the
    verdict is actionable, persist it as an AdvisorRecommendation (fingerprint-
    idempotent) so it joins the existing recommendation list + outcome loop.

    Returns the evaluation response either way. Persistence is skipped for
    INSUFFICIENT_EVIDENCE (never fabricate) and when advisor persistence is
    disabled. Advisory only — never publishes or spends.
    """
    from aicmo.config import get_settings

    response = await evaluate_creative(session, tenant=tenant)
    if get_settings().advisor_engine_enabled:
        await record_creative_recommendation(session, tenant=tenant, response=response)
    return response
