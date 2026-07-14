"""GenerationContext builder.

Pulls signals from analytics + landing pages + onboarding analysis into a
single immutable snapshot. Each lookup swallows its own errors so a slow
analytics query can't 5xx a context build.

Also exposes `render_context_block()` — the canonical way to summarise the
context inside an LLM prompt. Every generator's prompts.py prepends this
block when context is available, so the LLM sees the same inheritance
shape across the platform.
"""

from __future__ import annotations

import uuid
from datetime import UTC, datetime

import structlog
from sqlalchemy.ext.asyncio import AsyncSession

from aicmo.modules.analytics import service as analytics_service
from aicmo.modules.context.schemas import (
    ContextPreferences,
    GenerationContext,
    WinningAsset,
    WinningPage,
)
from aicmo.modules.onboarding.schemas import (
    BusinessAnalysis,
    BusinessProfileResponse,
)

log = structlog.get_logger()


async def build_generation_context(
    session: AsyncSession,
    *,
    profile: BusinessProfileResponse,
    brand_id: "uuid.UUID | None" = None,
) -> GenerationContext:
    """Snapshot everything the platform knows about this brand.

    Caller passes the already-fetched profile so we don't re-query it; the
    builder only does the extra signal lookups.

    `brand_id` scopes signal lookups (winning patterns, learning events,
    top assets). When omitted (legacy callers), falls back to `profile.user_id`
    for the lookups that still take user_id (transitional during W1-12).
    """
    signals: list[str] = []

    # ---- Intelligence Engine v2 fields (best-effort parse) ---------------
    analysis: BusinessAnalysis | None = None
    if profile.analysis:
        try:
            analysis = (
                profile.analysis
                if isinstance(profile.analysis, BusinessAnalysis)
                else BusinessAnalysis.model_validate(profile.analysis)
            )
        except Exception:
            analysis = None

    current_state: str | None = None
    desired_future_state: str | None = None
    growth_bottlenecks: list[str] = []
    recommended_channels: list[str] = []
    current_phase_summary: str | None = None

    if analysis:
        current_state = analysis.current_state
        desired_future_state = analysis.desired_future_state
        growth_bottlenecks = list(analysis.growth_bottlenecks or [])
        if analysis.recommended_acquisition_channels:
            recommended_channels = [
                c.channel for c in analysis.recommended_acquisition_channels
            ]
        if analysis.realistic_growth_path:
            first = analysis.realistic_growth_path[0]
            current_phase_summary = f"{first.phase} — {first.goal}"
        signals.append("Loaded Intelligence Engine v2 fields from profile.")

    # ---- Winning assets (top-converting generated pieces) ---------------
    winning_assets: list[WinningAsset] = []
    try:
        top = await analytics_service.top_assets(
            session, brand_id=(brand_id or profile.brand_id), limit=3
        )
        winning_assets = [
            WinningAsset(
                source_asset_type=t.source_asset_type,
                source_asset_id=t.source_asset_id,
                subtype=t.subtype,
                platform=t.platform,
                goal=t.goal,
                leads=t.leads,
            )
            for t in top.items
        ]
        if winning_assets:
            signals.append(
                f"{len(winning_assets)} winning asset(s) feeding pattern hints."
            )
    except Exception as e:
        log.warning("context.top_assets_failed", error=str(e))

    # ---- Best lead page (auto-attach default) ---------------------------
    winning_page: WinningPage | None = None
    try:
        pages = await analytics_service.landing_page_performance(
            session, brand_id=(brand_id or profile.brand_id)
        )
        published = [
            p
            for p in pages.items
            if p.status == "published" and p.submission_count > 0
        ]
        if published:
            best = max(published, key=lambda p: p.submission_count)
            winning_page = WinningPage(
                id=best.id,
                title=best.title,
                slug=best.slug,
                submission_count=best.submission_count,
                conversion_rate=best.conversion_rate,
            )
            signals.append(
                f"Auto-attach lead page: '{best.title}' ({best.submission_count} signups)."
            )
        elif pages.items:
            # No conversions yet but at least one published page exists —
            # fall back to the most-viewed published page.
            published_any = [p for p in pages.items if p.status == "published"]
            if published_any:
                best = max(published_any, key=lambda p: p.view_count)
                winning_page = WinningPage(
                    id=best.id,
                    title=best.title,
                    slug=best.slug,
                    submission_count=best.submission_count,
                    conversion_rate=best.conversion_rate,
                )
                signals.append(
                    f"Default lead page: '{best.title}' (most viewed, no signups yet)."
                )
    except Exception as e:
        log.warning("context.pages_failed", error=str(e))

    # ---- Social-intelligence inheritance --------------------------------
    # The whole point of the Social module: every generator inherits the
    # patterns the analyzer extracted from REAL platform performance.
    social_winning_patterns: list[str] = []
    social_audience_signals: list[str] = []
    try:
        from aicmo.modules.social import service as social_service

        wp = await social_service.top_winning_patterns_for_context(
            session, brand_id=(brand_id or profile.brand_id), limit=5
        )
        social_winning_patterns = [w.summary for w in wp if w.summary]
        if social_winning_patterns:
            signals.append(
                f"{len(social_winning_patterns)} social winning pattern(s) feeding generation."
            )

        ap = await social_service.list_audience_patterns(
            session, brand_id=(brand_id or profile.brand_id)
        )
        social_audience_signals = [
            a.description for a in ap if a.confidence_score >= 0.6
        ][:3]
    except Exception as e:
        log.warning("context.social_patterns_failed", error=str(e))

    # ---- Campaign Learning Lab inheritance ------------------------------
    # What we've learned from clustering our OWN past generations + their
    # downstream results. Distinct from social_winning_patterns: those
    # describe what works organically; these describe what works among
    # the things we generated. Threshold logic lives in `learning.service`
    # so the bar for "trustworthy enough to feed back into the LLM" is
    # centralised there (currently confidence ≥ 0.55, sample_size ≥ 3).
    learning_findings: list[str] = []
    try:
        from aicmo.modules.learning import service as learning_service

        events = await learning_service.top_learning_events_for_context(
            session, brand_id=(brand_id or profile.brand_id), limit=5
        )
        learning_findings = [e.finding for e in events if e.finding]
        if learning_findings:
            signals.append(
                f"{len(learning_findings)} learning finding(s) from past generations."
            )
    except Exception as e:
        log.warning("context.learning_findings_failed", error=str(e))

    # ---- Suggested defaults for studio forms ----------------------------
    suggested_platform: str | None = None
    if winning_assets and winning_assets[0].platform:
        suggested_platform = winning_assets[0].platform
    elif profile.preferred_platforms:
        suggested_platform = profile.preferred_platforms[0]

    preferences = ContextPreferences(
        suggested_platform=suggested_platform,
        suggested_tone=profile.brand_tone,
        suggested_goal=profile.primary_goal_text
        or (profile.goals[0] if profile.goals else None),
        suggested_landing_page_id=winning_page.id if winning_page else None,
    )

    return GenerationContext(
        user_id=profile.user_id,
        business_name=profile.business_name,
        industry=profile.industry,
        target_audience=profile.target_audience,
        brand_tone=profile.brand_tone,
        preferred_platforms=list(profile.preferred_platforms or []),
        business_location=profile.business_location,
        current_monthly_leads_band=profile.current_monthly_leads_band,
        monthly_budget_band=profile.monthly_budget_band,
        primary_goal_text=profile.primary_goal_text,
        brand_colors=list(profile.brand_colors or []),
        fonts=list(profile.fonts or []),
        keywords=list(profile.keywords or []),
        brand_rules=list(profile.brand_rules or []),
        writing_style=profile.writing_style,
        current_state=current_state,
        desired_future_state=desired_future_state,
        growth_bottlenecks=growth_bottlenecks,
        recommended_channels=recommended_channels,
        current_phase_summary=current_phase_summary,
        winning_assets=winning_assets,
        winning_page=winning_page,
        social_winning_patterns=social_winning_patterns,
        social_audience_signals=social_audience_signals,
        learning_findings=learning_findings,
        preferences=preferences,
        signals_used=signals,
        generated_at=datetime.now(UTC).isoformat(),
    )


# ---------------------------------------------------------------------
#  Prompt block — the canonical inheritance summary for LLM prompts
# ---------------------------------------------------------------------


def render_context_block(ctx: GenerationContext) -> str:
    """Format the snapshot for injection at the top of any generator prompt.

    Kept compact (~250-400 tokens). Sections that are empty render as a
    single 'unknown' line so the LLM doesn't see ragged whitespace.
    """
    location = ctx.business_location or "(not specified)"
    leads_band = ctx.current_monthly_leads_band or "(not specified)"
    budget_band = ctx.monthly_budget_band or "(not specified)"
    goal = ctx.primary_goal_text or "(no primary goal set)"
    platforms = ", ".join(ctx.preferred_platforms) or "(none)"
    channels = ", ".join(ctx.recommended_channels) or "(none yet)"
    bottlenecks = (
        " · ".join(ctx.growth_bottlenecks[:3])
        if ctx.growth_bottlenecks
        else "(none identified)"
    )

    winning_block = "(no winning pieces yet)"
    if ctx.winning_assets:
        winning_block = "\n".join(
            f"- {w.source_asset_type}/{w.subtype}"
            + (f" on {w.platform}" if w.platform else "")
            + f" — '{w.goal}' — {w.leads} lead(s)"
            for w in ctx.winning_assets
        )

    page_block = (
        f"'{ctx.winning_page.title}' (slug: {ctx.winning_page.slug})"
        if ctx.winning_page
        else "(no page attached)"
    )

    # Social Intelligence Layer — these are the lines the analyzer
    # extracted from REAL platform performance. The generator should treat
    # them as nearly-authoritative because they're grounded in this user's
    # actual audience behavior.
    social_patterns_block = (
        "\n".join(f"- {s}" for s in ctx.social_winning_patterns)
        if ctx.social_winning_patterns
        else "(none yet — run the social analyzer to feed this back)"
    )
    audience_signals_block = (
        "\n".join(f"- {s}" for s in ctx.social_audience_signals)
        if ctx.social_audience_signals
        else "(none yet)"
    )

    # Campaign Learning Lab — these findings are derived from clustering
    # this user's OWN past generations + their downstream results. They
    # carry slightly less authority than social_winning_patterns (which
    # come from organic posts), but more than vague best practices. They
    # are filtered server-side to confidence ≥ 0.55 and sample_size ≥ 3.
    learning_findings_block = (
        "\n".join(f"- {s}" for s in ctx.learning_findings)
        if ctx.learning_findings
        else "(none yet — generate more pieces and run the Learning Lab)"
    )

    # Brand Brain — the visual + verbal signature every generation inherits.
    colors = ", ".join(ctx.brand_colors) or "(not set)"
    fonts = ", ".join(ctx.fonts) or "(not set)"
    keywords = ", ".join(ctx.keywords[:12]) or "(none)"
    writing_style = ctx.writing_style or "(follow brand tone)"
    brand_rules_block = (
        "\n".join(f"- {r}" for r in ctx.brand_rules)
        if ctx.brand_rules
        else "(none set)"
    )

    return f"""# Business context (inherited — do not re-ask)
Name: {ctx.business_name}
Industry: {ctx.industry}
Location: {location}
Audience: {ctx.target_audience}
Brand tone: {ctx.brand_tone}
Preferred platforms: {platforms}

# Brand identity (the Brand Brain — keep every asset on-brand)
Brand colours: {colors}
Fonts: {fonts}
Writing style: {writing_style}
Keywords to weave in: {keywords}
Brand rules (MUST follow):
{brand_rules_block}

# Stage + resources
Current monthly leads/customers: {leads_band}
Monthly marketing budget: {budget_band}
Primary growth goal: {goal}
Current strategy phase: {ctx.current_phase_summary or "(not yet analysed)"}

# Strategist recommendations (from prior analysis)
Recommended channels: {channels}
Known bottlenecks: {bottlenecks}

# What ACTUALLY works on this user's social accounts
# (Derived from real performance numbers — treat as ground truth.)
{social_patterns_block}

# Audience signals (real engagement patterns)
{audience_signals_block}

# What our PAST GENERATIONS have taught us
# (Evidence-backed findings from our own experiments — high-confidence,
# sample-sized.  Lean on these when picking creative dimensions.)
{learning_findings_block}

# What's already working for this business
{winning_block}
Best-converting lead page: {page_block}

# Inheritance rule for this generation
You already know everything above. Do NOT re-ask. Reference these facts \
when they're relevant; ignore them when they aren't. Stay consistent with \
the established brand tone, colours, fonts, writing style, and platforms, \
and NEVER violate a brand rule listed above."""
