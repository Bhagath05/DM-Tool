"""Strategy Engine — Growth Objective → CampaignStrategy (the asset plan).

The user asks for an outcome; this decides the creative strategy (Law 1).
It calls the LLM for a rich, on-context plan and falls back to a deterministic
plan (keyed on the objective's *outcome category*, never an industry) when the
LLM is unavailable — so the feature always produces an editable campaign.
"""

from __future__ import annotations

import structlog
from sqlalchemy.ext.asyncio import AsyncSession

from aicmo.llm import get_llm_router
from aicmo.llm.providers.base import LLMMessage
from aicmo.modules.growth.models import GrowthObjective, ObjectiveKind
from aicmo.modules.growth.strategy_schemas import (
    AssetSpec,
    CampaignStrategy,
    Slide,
)
from aicmo.modules.onboarding import service as onboarding_service

log = structlog.get_logger()

SYSTEM_PROMPT = (
    "You are a senior growth strategist. Given a business OUTCOME (e.g. get "
    "leads, drive sales, get bookings, hire), you design a complete campaign: "
    "audience, messaging, channels, and a concrete ASSET PLAN of creatives to "
    "produce. Rules:\n"
    "- The outcome is the goal; every asset must move that KPI.\n"
    "- Produce a varied asset plan: at least a poster, a carousel, an ad, and "
    "a reel. Each asset needs a headline, a CTA, and (for carousel/reel) 3 "
    "slides/scenes.\n"
    "- Write specific, benefit-led copy. The CTA is the most important line.\n"
    "- Industry is CONTEXT for the copy, never a template — there are no "
    "industry templates.\n"
    "- Keep copy tight and platform-native."
)

# Outcome-keyed CTA + hook templates (industry-FREE). Used by the LLM as a
# hint and by the deterministic fallback directly.
_CATEGORY_CTA: dict[str, str] = {
    "lead": "Get your free assessment",
    "booking": "Book your slot",
    "sale": "Shop the offer",
    "awareness": "See how it works",
    "install": "Download the app",
    "hire": "Apply now",
    "signup": "Start free",
    "traffic": "Read the guide",
    "retention": "Claim your reward",
}
_CATEGORY_HOOK: dict[str, str] = {
    "lead": "Ready for better-qualified leads?",
    "booking": "Book in 30 seconds.",
    "sale": "A deal worth grabbing.",
    "awareness": "Here's what you're missing.",
    "install": "Your next favourite app.",
    "hire": "We're hiring — join us.",
    "signup": "Get started in minutes.",
    "traffic": "The guide everyone's reading.",
    "retention": "A thank-you, just for you.",
}


async def plan_campaign(
    session: AsyncSession, *, tenant, objective: GrowthObjective
) -> CampaignStrategy:
    """Produce the campaign strategy + asset plan for an objective. Tries the
    LLM; falls back to a deterministic plan on any failure (never raises)."""
    kind = await session.get(ObjectiveKind, objective.objective_kind)
    category = kind.category if kind else "lead"
    channels = list(kind.default_channels) if kind and kind.default_channels else []

    business_ctx = await _business_context(session, brand_id=objective.brand_id)

    try:
        return await _llm_plan(objective, category, channels, business_ctx)
    except Exception as e:  # noqa: BLE001 — never block the campaign on an LLM error
        log.warning("growth.strategy.llm_fallback", error=str(e), category=category)
        return _fallback_plan(objective, category, channels)


async def _business_context(session: AsyncSession, *, brand_id) -> str:
    try:
        profile = await onboarding_service.get_profile_or_none(session, brand_id=brand_id)
    except Exception:  # noqa: BLE001
        profile = None
    if profile is None:
        return ""
    bits = []
    for attr in ("business_name", "industry", "description", "target_audience"):
        val = getattr(profile, attr, None)
        if val:
            bits.append(f"{attr}: {val}")
    return "\n".join(bits)


async def _llm_plan(
    objective: GrowthObjective, category: str, channels: list[str], business_ctx: str
) -> CampaignStrategy:
    cta_hint = _CATEGORY_CTA.get(category, "Get started")
    user = (
        f"OUTCOME: {objective.objective_kind} ({category})\n"
        f"GOAL (the user's words): {objective.statement}\n"
        f"AUDIENCE HYPOTHESIS: {objective.audience_hypothesis or '(infer one)'}\n"
        f"SUGGESTED CHANNELS: {', '.join(channels) or '(choose)'}\n"
        f"CTA STYLE HINT: {cta_hint}\n"
        f"BUSINESS CONTEXT:\n{business_ctx or '(none provided — infer reasonably)'}\n\n"
        "Design the campaign and asset plan now."
    )
    router = get_llm_router()
    result = await router.generate(
        response_schema=CampaignStrategy,
        system=SYSTEM_PROMPT,
        messages=[LLMMessage(role="user", content=user)],
        temperature=0.7,
        max_tokens=2048,
    )
    strategy = result.data
    if not strategy.asset_plan:  # model returned an empty plan → use the fallback's
        strategy.asset_plan = _fallback_plan(objective, category, channels).asset_plan
    return strategy


# ---------------------------------------------------------------------
#  Deterministic fallback — always produces an editable multi-format plan.
# ---------------------------------------------------------------------
def _extract_topic(statement: str) -> str:
    """Best-effort subject of the goal, e.g. 'I need 50 qualified cybersecurity
    leads' → 'qualified cybersecurity'. Purely heuristic; the LLM path does
    this properly."""
    s = statement.strip().rstrip(".").lower()
    for lead in ("i need ", "i want ", "we need ", "we want ", "get me ", "help me ", "generate ", "drive "):
        if s.startswith(lead):
            s = s[len(lead):]
            break
    words = s.split()
    drop_head = {w for w in words if w.isdigit()}
    drop_tail = {"leads", "lead", "customers", "customer", "sales", "sale",
                 "bookings", "booking", "signups", "sign-ups", "installs",
                 "applicants", "applications", "more", "new", "qualified"}
    kept = [w for w in words if w not in drop_head and w not in drop_tail]
    topic = " ".join(kept).strip()
    return topic or "your offer"


def _fallback_plan(
    objective: GrowthObjective, category: str, channels: list[str]
) -> CampaignStrategy:
    topic = _extract_topic(objective.statement)
    cta = _CATEGORY_CTA.get(category, "Get started")
    hook = _CATEGORY_HOOK.get(category, "Here's something for you.")
    audience = objective.audience_hypothesis or f"Decision-makers interested in {topic}"
    value = f"We help you with {topic} — fast, and with proof."
    proof = "Trusted by teams who needed exactly this."

    poster = AssetSpec(
        creative_type="poster", aspect="4:5", headline=hook,
        subhead=value, cta=cta, rationale="Top-of-funnel attention + clear CTA.",
    )
    ad = AssetSpec(
        creative_type="ad", aspect="4:5", headline=f"{topic.title()} — done right.",
        subhead=value, cta=cta, variant_label="A",
        rationale="Offer-forward ad to drive the action.",
    )
    carousel = AssetSpec(
        creative_type="carousel", aspect="1:1", headline=hook, subhead=value, cta=cta,
        slides=[
            Slide(headline="The problem", body=f"Why {topic} is harder than it should be."),
            Slide(headline="The fix", body=value),
            Slide(headline="Proof", body=proof),
        ],
        rationale="Narrative carousel: problem → solution → proof.",
    )
    reel = AssetSpec(
        creative_type="reel", aspect="9:16", headline=hook, subhead=value, cta=cta,
        slides=[
            Slide(headline=hook, body="Scene 1 — the hook."),
            Slide(headline="Here's how", body=value),
            Slide(headline=cta, body="Scene 3 — the call to action."),
        ],
        rationale="Short-form video for reach + retention.",
    )
    return CampaignStrategy(
        objective_summary=objective.statement,
        audience=audience,
        hook=hook,
        value_prop=value,
        proof_point=proof,
        cta_angle=cta,
        channels=channels,
        asset_plan=[poster, ad, carousel, reel],
    )
