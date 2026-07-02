"""Module 6 — the cross-domain Learning Engine.

Reuses signals that already exist (never re-derives them): the Decision
Engine's factual snapshot (leads, publishing, performance, strategy, competitors,
and the social winning/audience patterns it already surfaces), plus the creative
LearningEvents this module already produces and the owner's own
approvals/rejections from advisor memory. It distils those into explainable
`LearningInsight` rows that feed the four reasoning modules.

One LLM call per run (mirrors `learning/engine.py`). When there's too little
real history it emits nothing and returns "Not enough historical evidence."
"""

from __future__ import annotations

import uuid
from datetime import UTC, datetime, timedelta

import structlog
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from aicmo.llm import get_llm_router
from aicmo.llm.providers.base import LLMMessage
from aicmo.modules.advisor import memory as advisor_memory
from aicmo.modules.decision_engine.signals import gather_signals
from aicmo.modules.learning import service as learning_service
from aicmo.modules.learning.insights_prompts import (
    SYSTEM_PROMPT,
    build_synthesis_prompt,
)
from aicmo.modules.learning.insights_schemas import (
    SynthesisOutput,
    SynthesisRunResult,
)
from aicmo.modules.learning.models import LearningInsight
from aicmo.tenancy.context import TenantContext

log = structlog.get_logger()

_MAX_TOKENS = 3200
# Below this the lesson is a guess, not a learning — never persist it (mirrors
# the constitution's "don't ship a CTA under 40% confidence").
_MIN_CONFIDENCE = 40
_NOT_ENOUGH = "Not enough historical evidence."


async def _expire_stale(session: AsyncSession, *, brand_id: uuid.UUID) -> int:
    """Flip active insights whose expires_at has passed to 'expired'. They stop
    feeding the reasoning modules but stay as history."""
    now = datetime.now(UTC)
    stmt = select(LearningInsight).where(
        LearningInsight.brand_id == brand_id,
        LearningInsight.status == "active",
        LearningInsight.expires_at.is_not(None),
        LearningInsight.expires_at < now,
    )
    n = 0
    for row in (await session.execute(stmt)).scalars():
        row.status = "expired"
        n += 1
    return n


async def _build_evidence_blocks(
    session: AsyncSession, *, tenant: TenantContext
) -> tuple[str, str, list[str], bool, int]:
    """Returns (business, industry, blocks, has_history, signals_considered).

    Reuses existing read paths only — no new queries invented."""
    brand_id = tenant.brand_id
    sig = await gather_signals(session, tenant=tenant)

    business = sig.business_name or "this business"
    industry = sig.industry or "unspecified industry"
    conv = round(sig.conversion_rate * 100, 1)

    blocks: list[str] = []
    considered = 0

    blocks.append(
        "## Leads & conversion\n"
        f"Total leads {sig.total_leads}; last 7d {sig.leads_7d}; last 30d "
        f"{sig.leads_30d}; hot {sig.hot_leads}. Landing pages published "
        f"{sig.landing_pages_published}; views {sig.total_views}; "
        f"conversion {conv}%."
    )
    considered += sig.total_leads + sig.landing_pages_published

    blocks.append(
        "## Publishing history\n"
        f"Published {sig.published_posts}; scheduled {sig.scheduled_posts}; "
        f"failed {sig.failed_posts}."
    )
    considered += sig.published_posts + sig.failed_posts

    if sig.performance_has_data:
        blocks.append(
            "## Paid / creative performance\n"
            f"{sig.performance_rows} performance rows across "
            f"{sig.creatives_tracked} creatives; "
            f"{sig.performance_diagnostics} diagnostics flagged."
        )
        considered += sig.performance_rows
    else:
        blocks.append("## Paid / creative performance\nNo performance data yet.")

    # Already-learned social patterns (reused, not re-derived).
    if sig.winning_patterns or sig.audience_patterns:
        parts = ["## Patterns already observed on this brand's posts"]
        parts += [f"- WIN: {w}" for w in sig.winning_patterns]
        parts += [f"- AUDIENCE: {a}" for a in sig.audience_patterns]
        blocks.append("\n".join(parts))
        considered += len(sig.winning_patterns) + len(sig.audience_patterns)

    # Strategy + revisions.
    strat_line = "in place" if sig.has_strategy else "none yet"
    try:
        from aicmo.modules.strategist import service as strategist_service

        revs = await strategist_service.list_strategies(session, brand_id=brand_id)
        rev_count = len(revs.items)
    except Exception as e:
        log.warning("learning.synth.strategy_failed", error=str(e)[:120])
        rev_count = 0
    blocks.append(
        "## Marketing strategy\n"
        f"Strategy {strat_line}"
        + (f"; top move: {sig.strategy_top_move}" if sig.strategy_top_move else "")
        + f". Revisions on record: {rev_count}."
    )

    # Creative learnings this module already derived (reuse).
    creative_events = 0
    try:
        events = await learning_service.top_learning_events_for_context(
            session, brand_id=brand_id, limit=8, min_confidence=0.4, min_sample_size=1
        )
        creative_events = len(events)
        if events:
            lines = ["## Creative learnings (from our own experiments)"]
            for ev in events:
                lines.append(
                    f"- [{ev.direction}] {ev.finding} "
                    f"(confidence {float(ev.confidence_score):.2f}, n={ev.sample_size})"
                )
            blocks.append("\n".join(lines))
            considered += creative_events
    except Exception as e:
        log.warning("learning.synth.creative_failed", error=str(e)[:120])

    # Owner approvals / rejections (reuse advisor memory verbatim block).
    memory_rows = 0
    try:
        rows = await advisor_memory.load_brand_memory(session, brand_id=brand_id)
        memory_rows = len(rows)
        if rows:
            blocks.append(
                "## Owner approvals / rejections\n"
                + advisor_memory.build_memory_context_block(rows)
            )
            considered += memory_rows
    except Exception as e:
        log.warning("learning.synth.memory_failed", error=str(e)[:120])

    # Phase 4.5 — the continuous loop's own execution history (approved/dismissed
    # work, recurring events, achieved goals). Real signals only.
    ops_lines: list[str] = []
    try:
        from aicmo.modules.operations import learning_feed

        ops_lines = await learning_feed.learning_signals(session, brand_id=brand_id)
        if ops_lines:
            blocks.append(
                "## Autonomous operations history\n"
                + "\n".join(f"- {ln}" for ln in ops_lines)
            )
            considered += len(ops_lines)
    except Exception as e:
        log.warning("learning.synth.ops_failed", error=str(e)[:120])

    has_history = bool(
        sig.total_leads
        or sig.published_posts
        or sig.performance_has_data
        or sig.winning_patterns
        or sig.audience_patterns
        or creative_events
        or memory_rows
        or ops_lines
    )
    return business, industry, blocks, has_history, considered


async def synthesize(
    session: AsyncSession, *, tenant: TenantContext
) -> SynthesisRunResult:
    """Public entry point for POST /learning/synthesize."""
    brand_id = tenant.brand_id
    now = datetime.now(UTC)

    expired = await _expire_stale(session, brand_id=brand_id)

    business, industry, blocks, has_history, considered = (
        await _build_evidence_blocks(session, tenant=tenant)
    )

    if not has_history:
        await session.commit()
        return SynthesisRunResult(
            insights_created=0,
            insights_superseded=0,
            insights_expired=expired,
            signals_considered=considered,
            data_sufficiency=(
                "This workspace has almost no marketing history yet — no leads, "
                "published posts, performance data, or prior learnings to draw on."
            ),
            note=_NOT_ENOUGH,
        )

    router = get_llm_router()
    user_prompt = build_synthesis_prompt(
        business=business, industry=industry, blocks=blocks
    )
    try:
        result = await router.generate(
            response_schema=SynthesisOutput,
            system=SYSTEM_PROMPT,
            messages=[LLMMessage(role="user", content=user_prompt)],
            temperature=0.3,
            max_tokens=_MAX_TOKENS,
        )
    except Exception as e:
        log.warning("learning.synth.llm_failed", error=str(e)[:160])
        await session.commit()
        return SynthesisRunResult(
            insights_created=0,
            insights_superseded=0,
            insights_expired=expired,
            signals_considered=considered,
            data_sufficiency="The learning run could not complete — try again shortly.",
            note=None,
        )

    output: SynthesisOutput = result.data
    created = 0
    superseded = 0

    for draft in output.insights:
        # Trust floor — no guesses, no evidence-free lessons.
        if draft.confidence < _MIN_CONFIDENCE or not draft.evidence:
            continue

        # Supersede the prior active lesson in the same category so lessons
        # don't stack contradictions (same idea as LearningEvent by variable).
        prior_stmt = select(LearningInsight).where(
            LearningInsight.brand_id == brand_id,
            LearningInsight.category == draft.category,
            LearningInsight.status == "active",
        )
        for prior in (await session.execute(prior_stmt)).scalars():
            prior.status = "superseded"
            superseded += 1

        expires_at = (
            now + timedelta(days=draft.lifespan_days)
            if draft.lifespan_days
            else None
        )
        session.add(
            LearningInsight(
                id=uuid.uuid4(),
                user_id=tenant.user_id,
                organization_id=tenant.organization_id,
                brand_id=brand_id,
                category=draft.category,
                observation=draft.observation,
                evidence=list(draft.evidence),
                recommendation=draft.recommendation,
                expected_result=draft.expected_result,
                confidence=int(draft.confidence),
                direction=draft.direction,
                affected_modules=list(draft.affected_modules),
                learned_at=now,
                expires_at=expires_at,
                source="auto",
                status="active",
            )
        )
        created += 1

    await session.commit()
    log.info(
        "learning.synth.completed",
        brand_id=str(brand_id),
        created=created,
        superseded=superseded,
        expired=expired,
        considered=considered,
    )
    return SynthesisRunResult(
        insights_created=created,
        insights_superseded=superseded,
        insights_expired=expired,
        signals_considered=considered,
        data_sufficiency=output.data_sufficiency,
        note=None if created else _NOT_ENOUGH,
    )
