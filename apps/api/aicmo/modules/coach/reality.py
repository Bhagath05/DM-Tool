"""Reality Engine orchestrator.

`evaluate_goal()` is the single public entry point. It composes:
1. Deterministic heuristic scoring (heuristics.score_goal) — instant.
2. LLM narrative generation (one Gemini call via the shared router) —
   anchored to the heuristic so the two never disagree.
3. Final assembly into the public RealityCheck shape.

Failure policy: if the LLM call fails, we still return a usable
RealityCheck with the heuristic score, label, signals, and a minimal
fallback narrative. The founder NEVER gets a 5xx for an advisory call.
"""

from __future__ import annotations

import structlog

from aicmo.llm import get_llm_router
from aicmo.llm.providers.base import LLMMessage
from aicmo.modules.coach.heuristics import label_for_score, score_goal
from aicmo.modules.coach.prompts import SYSTEM_PROMPT, build_user_prompt
from aicmo.modules.coach.schemas import (
    PhasedStep,
    RealityCheck,
    RealityMilestone,
    RiskFlag,
    _RealityNarrative,
)
from aicmo.modules.onboarding.schemas import BusinessProfileResponse

log = structlog.get_logger()

# Uses platform-default LLM provider (see config.llm_default_provider).


async def evaluate_goal(
    *,
    profile: BusinessProfileResponse,
    goal_text: str,
    timeline_hint: str | None = None,
) -> RealityCheck:
    """Score the goal + generate the advisory narrative around it."""
    score, signals = score_goal(
        profile=profile, goal_text=goal_text, timeline_hint=timeline_hint
    )
    label = label_for_score(score)

    narrative = await _generate_narrative(
        profile=profile,
        goal_text=goal_text,
        timeline_hint=timeline_hint,
        feasibility_score=score,
        feasibility_label=label,
        signals=signals,
    )

    return RealityCheck(
        feasibility_score=score,
        feasibility_label=label,
        headline=narrative.headline,
        realistic_milestones=narrative.realistic_milestones,
        phased_growth_path=narrative.phased_growth_path,
        risk_flags=narrative.risk_flags,
        strategic_notes=narrative.strategic_notes,
        score_signals=signals,
    )


async def _generate_narrative(
    *,
    profile: BusinessProfileResponse,
    goal_text: str,
    timeline_hint: str | None,
    feasibility_score: int,
    feasibility_label: str,
    signals: list[str],
) -> _RealityNarrative:
    """LLM call. Returns a fallback narrative on failure — never raises."""
    router = get_llm_router()
    user_prompt = build_user_prompt(
        profile=profile,
        goal_text=goal_text,
        timeline_hint=timeline_hint,
        feasibility_score=feasibility_score,
        feasibility_label=feasibility_label,  # type: ignore[arg-type]
        signals=signals,
    )
    try:
        result = await router.generate(
            response_schema=_RealityNarrative,
            system=SYSTEM_PROMPT,
            messages=[LLMMessage(role="user", content=user_prompt)],
            temperature=0.5,
            # 3 milestones + 3-4 phases + 2-5 flags + 2-4 notes + headline.
            # ~1500 tokens is plenty; 2200 leaves room for verbose phrasing.
            max_tokens=2200,
        )
        return result.data
    except Exception as e:  # noqa: BLE001 — advisory must degrade gracefully
        log.warning(
            "coach.reality_narrative_failed",
            error=str(e),
            score=feasibility_score,
            label=feasibility_label,
        )
        return _fallback_narrative(feasibility_label, signals)


def _fallback_narrative(label: str, signals: list[str]) -> _RealityNarrative:
    """Minimal, honest narrative if the LLM is unreachable.

    Not a great UX, but it preserves the contract — the frontend always
    gets a complete RealityCheck and the score is still trustworthy because
    it came from the heuristic, not the LLM.
    """
    headline = (
        "We couldn't run the full strategic analysis right now — the score "
        "below is still trustworthy. Refresh in a moment for the narrative."
    )
    return _RealityNarrative(
        headline=headline,
        realistic_milestones=[
            RealityMilestone(
                timeframe="Now",
                target="Refresh the page in a moment to see the full path.",
                why_realistic="The score is computed locally and won't change.",
            )
        ],
        phased_growth_path=[
            PhasedStep(
                phase="First",
                focus="Wait a moment, then ask for the reality check again.",
                rationale="The advisory narrative comes from an external model that briefly didn't respond.",
            )
        ],
        risk_flags=[
            RiskFlag(
                kind="execution",
                note=f"Score landed at: {label}. Signals: {'; '.join(signals) if signals else 'none'}.",
                severity="info",
            )
        ],
        strategic_notes=[
            "If this happens repeatedly, check that the Gemini API key is set and quota is healthy.",
        ],
    )
