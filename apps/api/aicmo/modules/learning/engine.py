"""Learning Engine — clusters experiments + results into LearningEvents.

Mirror of `social/analyzer.py`. Reads the user's recent CampaignExperiment
rows + their latest ExperimentResult, flattens them into an indexed
table, asks Gemini to find 0-6 evidence-backed findings, then persists
those to `learning_events`.

One Gemini call per run. The output feeds GenerationContext, which feeds
every studio — so the bar for emitting is intentionally high (see
`prompts.ENGINE_SYSTEM_PROMPT`).
"""

from __future__ import annotations

import uuid
from datetime import datetime

import structlog
from sqlalchemy import desc, select
from sqlalchemy.ext.asyncio import AsyncSession

from aicmo.llm import get_llm_router
from aicmo.llm.providers.base import LLMMessage
from aicmo.modules.learning.models import (
    CampaignExperiment,
    ExperimentResult,
    LearningEvent,
)
from aicmo.modules.learning.prompts import (
    ENGINE_SYSTEM_PROMPT,
    build_engine_user_prompt,
)
from aicmo.modules.learning.schemas import LearningRunResult, _LearningOutput
from aicmo.modules.onboarding import service as onboarding_service
from aicmo.tenancy.context import TenantContext

log = structlog.get_logger()

# Engine was originally pinned to Gemini Flash for cost. Now uses the
# platform-default provider so a single API key powers everything.
_MAX_TOKENS = 3200

# Engine refuses to run with fewer than this many experiments — there's
# nothing meaningful to learn from 2 generations.
_MIN_EXPERIMENTS = 3


async def run_engine(
    session: AsyncSession,
    *,
    tenant: TenantContext,
    variable: str | None = None,
    max_experiments: int = 60,
) -> LearningRunResult:
    """Public entry point. Returns counts; the rows themselves land in
    `learning_events` for the frontend to read."""
    brand_id = tenant.brand_id

    # 1) Pull recent experiments + their latest result.
    exp_stmt = (
        select(CampaignExperiment)
        .where(CampaignExperiment.brand_id == brand_id)
        .order_by(desc(CampaignExperiment.created_at))
        .limit(max(5, min(max_experiments, 200)))
    )
    experiments = list((await session.execute(exp_stmt)).scalars().all())

    if len(experiments) < _MIN_EXPERIMENTS:
        return LearningRunResult(
            events_created=0,
            events_superseded=0,
            experiments_considered=len(experiments),
        )

    latest_result_by_exp: dict[uuid.UUID, ExperimentResult] = {}
    if experiments:
        res_stmt = (
            select(ExperimentResult)
            .where(
                ExperimentResult.experiment_id.in_(
                    [e.id for e in experiments]
                )
            )
            .order_by(desc(ExperimentResult.captured_at))
        )
        for r in (await session.execute(res_stmt)).scalars():
            if r.experiment_id not in latest_result_by_exp:
                latest_result_by_exp[r.experiment_id] = r

    # 2) Look up profile for business context in the prompt.
    profile_row = await onboarding_service.get_profile_or_none(
        session, brand_id
    )
    business_name = (
        getattr(profile_row, "business_name", None) or "this business"
    )
    industry = (
        getattr(profile_row, "industry", None) or "unspecified industry"
    )

    # 3) Flatten to a stable index table the LLM can reference.
    experiments_block = _render_experiments_block(
        experiments, latest_result_by_exp
    )

    # 4) Single Gemini call.
    router = get_llm_router()
    user_prompt = build_engine_user_prompt(
        business_name=business_name,
        industry=industry,
        variable_focus=variable,
        experiments_block=experiments_block,
    )

    try:
        result = await router.generate(
            response_schema=_LearningOutput,
            system=ENGINE_SYSTEM_PROMPT,
            messages=[LLMMessage(role="user", content=user_prompt)],
            temperature=0.4,
            max_tokens=_MAX_TOKENS,
        )
    except Exception as e:
        log.warning("learning.engine_failed", error=str(e))
        return LearningRunResult(
            events_created=0,
            events_superseded=0,
            experiments_considered=len(experiments),
        )

    output = result.data

    # 5) Persist. When a new finding's variable matches an existing
    # active event's variable, supersede the old one instead of stacking.
    # This is the difference vs the social analyzer (which fully replaces).
    # Older learnings can still be useful as history but shouldn't compete
    # in the GenerationContext.
    events_superseded = 0
    events_created = 0

    for derived in output.events:
        # Skip below the platform-wide trust bar regardless of LLM score.
        if derived.confidence_score < 0.40 or derived.sample_size < 1:
            continue

        # Variable focus narrowing — caller asked for one variable only.
        if variable and derived.variable != variable:
            continue

        experiment_ids: list[str] = []
        for idx in derived.experiment_indices:
            if 0 <= idx < len(experiments):
                experiment_ids.append(str(experiments[idx].id))

        # Supersede prior active event for this variable.
        prior_stmt = select(LearningEvent).where(
            LearningEvent.brand_id == brand_id,
            LearningEvent.variable == derived.variable,
            LearningEvent.status == "active",
        )
        for prior in (await session.execute(prior_stmt)).scalars():
            prior.status = "superseded"
            events_superseded += 1

        session.add(
            LearningEvent(
                id=uuid.uuid4(),
                user_id=tenant.user_id,
                organization_id=tenant.organization_id,
                brand_id=tenant.brand_id,
                variable=derived.variable,
                finding=derived.finding,
                direction=derived.direction,
                effect_size=derived.effect_size,
                experiment_ids=experiment_ids,
                evidence=list(derived.evidence or []),
                sample_size=int(derived.sample_size),
                confidence_score=float(derived.confidence_score),
                source="auto",
                status="active",
            )
        )
        events_created += 1

    await session.commit()
    log.info(
        "learning.engine_completed",
        brand_id=str(brand_id),
        variable=variable,
        experiments=len(experiments),
        created=events_created,
        superseded=events_superseded,
    )
    return LearningRunResult(
        events_created=events_created,
        events_superseded=events_superseded,
        experiments_considered=len(experiments),
    )


# ---------------------------------------------------------------------
#  Helpers
# ---------------------------------------------------------------------


def _render_experiments_block(
    experiments: list[CampaignExperiment],
    latest_result_by_exp: dict[uuid.UUID, ExperimentResult],
) -> str:
    """Index → row table the LLM references by integer.

    We DO want the engine to see the variable_choices dict and the
    inherited_patterns list — those are precisely the dimensions it's
    looking at. Compact one-line-per-experiment format keeps tokens low
    even at max_experiments=60.
    """
    lines: list[str] = [
        "Index | Type | Platform | Created | Hypothesis | Variable choices | Inherited patterns | Impressions | Engagement% | Leads | CTR%",
        "----- | ---- | -------- | ------- | ---------- | ---------------- | ------------------ | ----------- | ----------- | ----- | ----",
    ]
    for i, e in enumerate(experiments):
        r = latest_result_by_exp.get(e.id)
        created = (
            e.created_at.isoformat()[:10]
            if isinstance(e.created_at, datetime)
            else "—"
        )
        hypothesis_short = (e.hypothesis or "—")[:80].replace("\n", " ").replace(
            "|", "/"
        )
        choices_short = _flatten_dict_for_prompt(e.variable_choices or {})
        patterns_short = (
            " · ".join(list(e.inherited_patterns or [])[:3])[:120]
            .replace("\n", " ")
            .replace("|", "/")
        ) or "—"
        if r is None:
            metrics = "— | — | — | —"
        else:
            eng_pct = f"{(r.engagement_rate * 100):.1f}%"
            ctr_pct = f"{(r.ctr * 100):.2f}%"
            metrics = f"{r.impressions} | {eng_pct} | {r.leads} | {ctr_pct}"
        lines.append(
            f"{i} | {e.source_asset_type} | {e.platform or '—'} | {created} | "
            f"{hypothesis_short} | {choices_short} | {patterns_short} | {metrics}"
        )
    return "\n".join(lines)


def _flatten_dict_for_prompt(d: dict) -> str:
    """`{hook_style: 'founder', length: 'short'}` → `'hook_style=founder, length=short'`.
    Keeps the experiments table parsable by the LLM without dumping JSON
    braces (Gemini reads tabular markdown better than nested JSON in
    long prompts)."""
    if not d:
        return "—"
    parts: list[str] = []
    for k, v in list(d.items())[:6]:
        sv = str(v)[:30].replace("|", "/").replace("\n", " ")
        parts.append(f"{k}={sv}")
    return ", ".join(parts)
