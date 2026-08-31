"""Deterministic, evidence-grounded insight rules.

Rule-based first (per the Phase-3 spec): obvious situations produce insights
without any LLM, so the Performance Marketer is honest and reproducible even
when the model is unavailable. Every rule:

- fires ONLY when the data is sufficient for the claim (``sufficiency`` gate),
- fires ONLY on comparisons that are real (never on ``"insufficient"``),
- attaches the exact computed evidence it reasoned from, and
- carries the full recommendation contract (recommendation / reason /
  confidence / expected_result / impact_category).

The LLM layer later *rephrases* these; it never adds evidence or numbers.
"""

from __future__ import annotations

from dataclasses import dataclass

from aicmo.modules.marketing_analytics import normalize
from aicmo.modules.marketing_analytics.schemas import (
    ConfidenceBand,
    Insight,
    MetricEvidence,
)
from aicmo.modules.marketing_analytics.sufficiency import (
    Sufficiency,
    SufficiencyLevel,
    can_claim_comparison,
)
from aicmo.modules.marketing_analytics.timeseries import (
    SIGNIFICANT_PCT,
    Comparison,
)


@dataclass(frozen=True)
class MetricState:
    """A single provider metric with its period-over-period comparison."""

    provider_slug: str
    platform: str
    canonical: str
    label: str
    kind: str
    unit: str
    comparable: bool
    current: float
    comparison: Comparison


def confidence_band(score: int) -> ConfidenceBand:
    if score >= 80:
        return "high"
    if score >= 60:
        return "medium"
    if score >= 40:
        return "low"
    return "speculative"


def _cap(sufficiency: Sufficiency) -> int:
    """Confidence ceiling from how much data backs the claim."""
    if sufficiency.level == SufficiencyLevel.STRONG:
        return 85
    if sufficiency.level == SufficiencyLevel.WEEKLY:
        return 70
    return 55


def _window_label(window_days: int) -> str:
    return f"{window_days}d"


def _evidence(state: MetricState, window: str) -> MetricEvidence:
    c = state.comparison
    return MetricEvidence(
        metric=state.canonical,
        label=state.label,
        provider=state.provider_slug,
        platform=state.platform,
        current=c.current,
        previous=c.previous,
        absolute_change=c.absolute_change,
        change_percent=c.change_percent,
        window=window,
    )


def _is_significant_up(c: Comparison) -> bool:
    return c.trend == "up" and c.change_percent is not None and c.change_percent >= SIGNIFICANT_PCT


def _is_significant_down(c: Comparison) -> bool:
    return (
        c.trend == "down" and c.change_percent is not None and c.change_percent <= -SIGNIFICANT_PCT
    )


def _is_stable(c: Comparison) -> bool:
    """No meaningful move — flat, or a change below the significance bar."""
    if c.trend == "flat":
        return True
    return c.change_percent is not None and abs(c.change_percent) < SIGNIFICANT_PCT


def _pct_text(c: Comparison) -> str:
    if c.change_percent is None:
        return "changed"
    direction = "up" if c.change_percent > 0 else "down" if c.change_percent < 0 else "flat"
    return f"{direction} {abs(c.change_percent):.0f}%"


def _mk(
    *,
    rule: str,
    state: MetricState,
    severity: str,
    observation: str,
    interpretation: str,
    recommendation: str,
    reason: str,
    expected_result: str,
    impact_category: str,
    base_confidence: int,
    sufficiency: Sufficiency,
    window: str,
    extra_evidence: list[MetricEvidence] | None = None,
    id_suffix: str = "",
) -> Insight:
    confidence = min(base_confidence, _cap(sufficiency))
    evidence = [_evidence(state, window)]
    if extra_evidence:
        evidence.extend(extra_evidence)
    return Insight(
        id=f"{rule}:{state.provider_slug}:{state.canonical}{id_suffix}",
        severity=severity,  # type: ignore[arg-type]
        observation=observation,
        evidence=evidence,
        interpretation=interpretation,
        recommendation=recommendation,
        reason=reason[:140],
        confidence=confidence,
        confidence_band=confidence_band(confidence),
        expected_result=expected_result,
        impact_category=impact_category,  # type: ignore[arg-type]
        window=window,
    )


def _find(states: list[MetricState], provider: str, canonical: str) -> MetricState | None:
    for s in states:
        if s.provider_slug == provider and s.canonical == canonical:
            return s
    return None


def generate_insights(
    states: list[MetricState],
    *,
    sufficiency: Sufficiency,
    window_days: int,
) -> list[Insight]:
    """Run every deterministic rule and return the insights that fired.

    Returns an empty list when the data cannot support any honest claim — an
    empty state is correct, never a fabricated 'everything looks great'.
    """
    if not can_claim_comparison(sufficiency.level, window_days=window_days):
        return []

    window = _window_label(window_days)
    insights: list[Insight] = []
    providers = sorted({s.provider_slug for s in states})

    # ---- per-platform distribution-vs-interaction rules ----
    for provider in providers:
        platform = next(s.platform for s in states if s.provider_slug == provider)
        reach = _find(states, provider, normalize.REACH) or _find(
            states, provider, normalize.IMPRESSIONS
        )
        eng = _find(states, provider, normalize.ENGAGEMENT_RATE)
        audience = _find(states, provider, normalize.AUDIENCE)

        # R1 — reach up, engagement flat → distribution outran resonance.
        if reach and eng and _is_significant_up(reach.comparison) and _is_stable(eng.comparison):
            insights.append(
                _mk(
                    rule="reach_up_engagement_flat",
                    state=reach,
                    severity="attention",
                    observation=(
                        f"{platform} {reach.label.lower()} is {_pct_text(reach.comparison)} over the "
                        f"last {window_days} days while engagement rate stayed roughly flat."
                    ),
                    interpretation=(
                        "Your content is reaching more people, but the extra reach is not "
                        "converting into proportionally more interaction — a hook/CTA gap, not a distribution problem."
                    ),
                    recommendation=(
                        f"Test stronger first-line hooks and a clearer call-to-action in your next 3 {platform} posts."
                    ),
                    reason=f"{platform} reach {_pct_text(reach.comparison)}, engagement flat ({window}).",
                    expected_result="A higher share of the people you already reach interacting with the next posts.",
                    impact_category="lead",
                    base_confidence=70,
                    sufficiency=sufficiency,
                    window=window,
                    extra_evidence=[_evidence(eng, window)],
                )
            )
        # R2 — engagement up, reach stable → resonance improving.
        elif reach and eng and _is_significant_up(eng.comparison) and _is_stable(reach.comparison):
            insights.append(
                _mk(
                    rule="engagement_up_reach_stable",
                    state=eng,
                    severity="good",
                    observation=(
                        f"{platform} engagement rate is {_pct_text(eng.comparison)} over the last "
                        f"{window_days} days on stable reach."
                    ),
                    interpretation=(
                        "The same-sized audience is interacting more — your recent content is resonating better."
                    ),
                    recommendation=(
                        f"Keep publishing the recent {platform} format and topics; note what changed and repeat it."
                    ),
                    reason=f"{platform} engagement {_pct_text(eng.comparison)}, reach stable ({window}).",
                    expected_result="Continued or growing engagement if you keep the winning format.",
                    impact_category="lead",
                    base_confidence=68,
                    sufficiency=sufficiency,
                    window=window,
                    extra_evidence=[_evidence(reach, window)],
                )
            )

        # R3 — audience growing.
        if audience and _is_significant_up(audience.comparison):
            insights.append(
                _mk(
                    rule="audience_growth",
                    state=audience,
                    severity="good",
                    observation=(
                        f"Your {platform} {audience.label.lower()} grew {_pct_text(audience.comparison)} "
                        f"over the last {window_days} days."
                    ),
                    interpretation="Your audience base is expanding — more people you can reach for free over time.",
                    recommendation=f"Keep the posting cadence that is winning new {platform} followers and thank recent ones.",
                    reason=f"{platform} audience {_pct_text(audience.comparison)} ({window}).",
                    expected_result="Continued audience growth if cadence holds.",
                    impact_category="customer",
                    base_confidence=72,
                    sufficiency=sufficiency,
                    window=window,
                )
            )

        # R6 — a meaningful decline in a core distribution metric.
        core = reach or audience
        if core and _is_significant_down(core.comparison):
            insights.append(
                _mk(
                    rule="core_decline",
                    state=core,
                    severity="attention",
                    observation=(
                        f"{platform} {core.label.lower()} is {_pct_text(core.comparison)} over the "
                        f"last {window_days} days."
                    ),
                    interpretation=(
                        "A drop here usually traces back to lower posting frequency, a format that stopped working, "
                        "or seasonality — worth checking before it compounds."
                    ),
                    recommendation=(
                        f"Review your {platform} posting cadence for the period and republish your best recent format."
                    ),
                    reason=f"{platform} {core.label.lower()} {_pct_text(core.comparison)} ({window}).",
                    expected_result="Recovery over the following 1-2 weeks if cadence and format are restored.",
                    impact_category="lead",
                    base_confidence=68,
                    sufficiency=sufficiency,
                    window=window,
                )
            )

    # ---- cross-platform allocation rule ----
    insights.extend(_cross_platform_leader(states, sufficiency=sufficiency, window=window))

    # ---- all-platforms decline rule ----
    decline = _all_platforms_declining(states, providers)
    if decline is not None:
        lead_state, extra = decline
        insights.append(
            _mk(
                rule="all_platforms_decline",
                state=lead_state,
                severity="attention",
                observation="Reach or audience is down across every connected platform over the last period.",
                interpretation=(
                    "A synchronized decline across platforms points to something upstream — posting cadence, "
                    "audience fatigue, seasonality, or an account/access issue — rather than one bad post."
                ),
                recommendation=(
                    "Check that publishing continued as planned, then run one focused test: revive your best "
                    "past format on your strongest platform this week."
                ),
                reason="Every connected platform's core metric declined this period.",
                expected_result="Isolating the cause; a cadence fix often recovers reach within 1-2 weeks.",
                impact_category="lead",
                base_confidence=64,
                sufficiency=sufficiency,
                window=window,
                extra_evidence=extra,
                id_suffix=":all",
            )
        )

    return insights


def _cross_platform_leader(
    states: list[MetricState], *, sufficiency: Sufficiency, window: str
) -> list[Insight]:
    """When ≥2 platforms report the same comparable metric and one clearly
    leads, recommend shifting testing/effort toward the stronger platform."""
    out: list[Insight] = []
    # Only compare within semantically comparable families.
    families = sorted(
        {
            s.canonical
            for s in states
            if s.comparable and s.canonical in (normalize.AUDIENCE, normalize.ENGAGEMENT_RATE)
        }
    )
    for family in families:
        members = [s for s in states if s.canonical == family and s.comparable]
        if len({m.provider_slug for m in members}) < 2:
            continue
        # Leader by current value; only fire when the margin is decisive (>=50%).
        ranked = sorted(members, key=lambda m: m.current, reverse=True)
        leader, runner_up = ranked[0], ranked[1]
        if runner_up.current <= 0 or leader.current < runner_up.current * 1.5:
            continue
        out.append(
            _mk(
                rule="cross_platform_leader",
                state=leader,
                severity="neutral",
                observation=(
                    f"{leader.platform} leads on {leader.label.lower()} "
                    f"({leader.current:.0f}) vs {runner_up.platform} ({runner_up.current:.0f})."
                ),
                interpretation=(
                    f"{leader.platform} is where your audience is most concentrated for this metric right now."
                ),
                recommendation=(
                    f"Put your next test — a new format or a small boosted post — on {leader.platform} first, "
                    "where it can reach the most people."
                ),
                reason=f"{leader.platform} {leader.label.lower()} well above {runner_up.platform} ({window}).",
                expected_result=f"More return on the same effort by concentrating tests on {leader.platform}.",
                impact_category="lead",
                base_confidence=62,
                sufficiency=sufficiency,
                window=window,
                extra_evidence=[_evidence(runner_up, window)],
                id_suffix=f":{family}",
            )
        )
    return out


def _all_platforms_declining(
    states: list[MetricState], providers: list[str]
) -> tuple[MetricState, list[MetricEvidence]] | None:
    """Return (representative_state, extra_evidence) when every provider's core
    reach/audience comparison is a real decline; else None."""
    if len(providers) < 2:
        return None
    cores: list[MetricState] = []
    for provider in providers:
        core = (
            _find(states, provider, normalize.REACH)
            or _find(states, provider, normalize.IMPRESSIONS)
            or _find(states, provider, normalize.AUDIENCE)
        )
        if core is None or core.comparison.trend == "insufficient":
            return None  # can't claim "all" without every platform measurable
        cores.append(core)
    if not cores or not all(c.comparison.trend == "down" for c in cores):
        return None
    window = cores[0].comparison.window_days
    extra = [_evidence(c, f"{window}d") for c in cores[1:]]
    return cores[0], extra
