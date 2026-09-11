"""Evidence-driven AI-vs-human creative evaluation (pure, deterministic).

The advisor must be able to conclude that AI-generated creative is HELPING or
HURTING on real evidence — and must never recommend "just generate more AI"
simply because the platform can. This module is the pure decision core: given
provenance-labelled performance samples it validates comparability, computes
metric deltas, and returns one of five honest verdicts with a deterministic
confidence and an explicit list of evidence limitations.

No LLM, no network, no DB — the verdict is reproducible and testable without
any provider credentials. It never invents a metric: a dimension is compared
only when it is actually present on both sides; anything missing is reported as
a limitation, never as a zero.

Reuses ``marketing_analytics.sufficiency`` for the trend-claim gate.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime
from enum import StrEnum

from aicmo.modules.marketing_analytics.sufficiency import (
    assess as assess_sufficiency,
)
from aicmo.modules.marketing_analytics.sufficiency import (
    can_claim_trend,
)
from aicmo.modules.marketing_analytics.timeseries import Observation


class Provenance(StrEnum):
    AI = "ai"
    HUMAN = "human"
    UNKNOWN = "unknown"


class Verdict(StrEnum):
    AI_OUTPERFORMING = "AI_OUTPERFORMING"
    AI_UNDERPERFORMING = "AI_UNDERPERFORMING"
    HUMAN_OUTPERFORMING = "HUMAN_OUTPERFORMING"
    NO_SIGNIFICANT_DIFFERENCE = "NO_SIGNIFICANT_DIFFERENCE"
    INSUFFICIENT_EVIDENCE = "INSUFFICIENT_EVIDENCE"


class TrendDirection(StrEnum):
    FALLING = "falling"
    RISING = "rising"
    FLAT = "flat"
    INSUFFICIENT = "insufficient"


# metric_key -> +1 (higher is better) | -1 (lower is better). Only these keys
# are ever compared; anything else on a sample is ignored, never invented.
METRIC_DIRECTION: dict[str, int] = {
    "views": 1,
    "engagement_rate": 1,
    "ctr": 1,
    "watch_time_seconds": 1,
    "reach": 1,
    "conversions": 1,
    "revenue": 1,
    "roas": 1,
    "retention": 1,
    "cac": -1,
    "cost_per_result": -1,
}

# Human-readable labels for evidence/UI (plain-language, per the constitution).
METRIC_LABEL: dict[str, str] = {
    "views": "views",
    "engagement_rate": "engagement",
    "ctr": "click-through rate",
    "watch_time_seconds": "watch time (retention)",
    "reach": "reach",
    "conversions": "conversions",
    "revenue": "attributed revenue",
    "roas": "return on ad spend",
    "retention": "retention",
    "cac": "cost to acquire a customer",
    "cost_per_result": "cost per result",
}

# --- thresholds (defaults; overridable per call) ---
MIN_SAMPLES_PER_SIDE = 3  # fewer than this on either side => insufficient
SIGNIFICANCE_THRESHOLD = 0.10  # relative delta below this is noise
DECISIVE_EFFECT = 0.25  # per-metric effect size for a "decisive" human win
MIN_DECISIVE_METRICS = 3  # metrics that must all favour human, decisively
MAX_SPEND_RATIO = 3.0  # cohorts whose mean spend differs > this are not comparable
MAX_AUDIENCE_RATIO = 5.0  # ditto for audience/reach scale
CONFIDENCE_CAP = 90  # a data-driven verdict is never 100% certain
_EPS = 1e-9


@dataclass(frozen=True)
class CreativeSample:
    """One provenance-labelled performance record (e.g. a published post).

    ``metrics`` holds ONLY metrics that are actually present — a missing key
    means "not measured", never zero.
    """

    provenance: Provenance
    metrics: dict[str, float]
    platform: str
    fmt: str
    posted_at: datetime | None = None
    spend: float | None = None
    audience_size: float | None = None
    ref: str | None = None


@dataclass(frozen=True)
class MetricDelta:
    metric: str
    label: str
    ai_value: float
    human_value: float
    relative_delta: float  # (ai - human) / |human|, raw sign
    ai_better: bool
    significant: bool


@dataclass(frozen=True)
class CreativeEvaluation:
    verdict: Verdict
    confidence: int
    ai_sample_size: int
    human_sample_size: int
    unknown_sample_size: int
    metric_deltas: list[MetricDelta] = field(default_factory=list)
    evidence: list[str] = field(default_factory=list)
    limitations: list[str] = field(default_factory=list)

    @property
    def ai_is_underperforming(self) -> bool:
        return self.verdict in (Verdict.AI_UNDERPERFORMING, Verdict.HUMAN_OUTPERFORMING)


def _mean(values: list[float]) -> float:
    return sum(values) / len(values) if values else 0.0


def _present(samples: list[CreativeSample], metric: str) -> list[float]:
    return [s.metrics[metric] for s in samples if metric in s.metrics]


def _comparable_scale(ai: list[CreativeSample], human: list[CreativeSample]) -> str | None:
    """Return a limitation string if the two cohorts are NOT comparable in a
    way that would invalidate a like-for-like read (mixed platforms, or a large
    spend/audience gap that confounds the comparison). None => comparable."""
    ai_platforms = {s.platform for s in ai}
    human_platforms = {s.platform for s in human}
    if ai_platforms.isdisjoint(human_platforms):
        return (
            "AI and human samples are on different platforms "
            f"({sorted(ai_platforms)} vs {sorted(human_platforms)}) — not a like-for-like comparison."
        )
    ai_formats = {s.fmt for s in ai}
    human_formats = {s.fmt for s in human}
    if ai_formats.isdisjoint(human_formats):
        return (
            "AI and human samples use different creative formats "
            f"({sorted(ai_formats)} vs {sorted(human_formats)}) — not a like-for-like comparison."
        )

    def _ratio(getter) -> float | None:
        a = [v for s in ai if (v := getter(s)) is not None]
        h = [v for s in human if (v := getter(s)) is not None]
        if not a or not h:
            return None
        ma, mh = _mean(a), _mean(h)
        lo, hi = sorted((ma, mh))
        return (hi / lo) if lo > _EPS else None

    spend_ratio = _ratio(lambda s: s.spend)
    if spend_ratio is not None and spend_ratio > MAX_SPEND_RATIO:
        return (
            f"Spend differs {spend_ratio:.1f}x between the AI and human samples — "
            "a paid-vs-organic gap this large invalidates the comparison."
        )
    audience_ratio = _ratio(lambda s: s.audience_size)
    if audience_ratio is not None and audience_ratio > MAX_AUDIENCE_RATIO:
        return (
            f"Audience scale differs {audience_ratio:.1f}x between the samples — "
            "too different to compare fairly."
        )
    return None


def _missing_metric_limitations(
    ai: list[CreativeSample], human: list[CreativeSample], compared: set[str]
) -> list[str]:
    """Name the business-critical metrics we could NOT compare, so the verdict
    never looks more complete than the evidence."""
    out: list[str] = []
    for metric in ("conversions", "revenue", "roas", "cac"):
        if metric not in compared:
            out.append(
                f"No per-creative {METRIC_LABEL[metric]} data available — "
                "that dimension was not part of this comparison."
            )
    _ = (ai, human)
    return out


def _confidence(*, per_side_min: int, significant: list[MetricDelta], agree_fraction: float) -> int:
    """Deterministic confidence — a function of evidence only. Never 100, and
    confidence NEVER unlocks execution (approval is enforced separately)."""
    base = 50
    base += min(20, (per_side_min - MIN_SAMPLES_PER_SIDE) * 4)  # more data
    base += int(min(20, agree_fraction * 20))  # metric agreement
    avg_effect = _mean([abs(d.relative_delta) for d in significant]) if significant else 0.0
    base += int(min(10, avg_effect * 20))  # effect size
    return max(0, min(CONFIDENCE_CAP, base))


def evaluate_ai_vs_human(
    samples: list[CreativeSample],
    *,
    min_samples_per_side: int = MIN_SAMPLES_PER_SIDE,
    significance_threshold: float = SIGNIFICANCE_THRESHOLD,
) -> CreativeEvaluation:
    """Compare AI-generated vs human-created creative on real, provenance-
    labelled samples. Fails to INSUFFICIENT_EVIDENCE rather than guessing."""
    ai = [s for s in samples if s.provenance == Provenance.AI]
    human = [s for s in samples if s.provenance == Provenance.HUMAN]
    unknown = [s for s in samples if s.provenance == Provenance.UNKNOWN]

    base_limitations: list[str] = []
    if unknown:
        base_limitations.append(
            f"{len(unknown)} sample(s) had unknown provenance and were excluded "
            "(only content we can attribute to AI or a human is compared)."
        )

    # Gate 1 — enough on each side.
    if len(ai) < min_samples_per_side or len(human) < min_samples_per_side:
        return CreativeEvaluation(
            verdict=Verdict.INSUFFICIENT_EVIDENCE,
            confidence=0,
            ai_sample_size=len(ai),
            human_sample_size=len(human),
            unknown_sample_size=len(unknown),
            evidence=[
                f"{len(ai)} AI vs {len(human)} human comparable samples "
                f"(need at least {min_samples_per_side} of each)."
            ],
            limitations=[
                *base_limitations,
                "Not enough comparable content on both sides to draw a conclusion.",
            ],
        )

    # Gate 2 — comparability (invalid comparisons fail closed).
    incomparable = _comparable_scale(ai, human)
    if incomparable is not None:
        return CreativeEvaluation(
            verdict=Verdict.INSUFFICIENT_EVIDENCE,
            confidence=0,
            ai_sample_size=len(ai),
            human_sample_size=len(human),
            unknown_sample_size=len(unknown),
            evidence=[f"{len(ai)} AI vs {len(human)} human samples."],
            limitations=[*base_limitations, incomparable],
        )

    # Compare only metrics actually present on BOTH sides (never invent one).
    deltas: list[MetricDelta] = []
    for metric, direction in METRIC_DIRECTION.items():
        ai_vals = _present(ai, metric)
        human_vals = _present(human, metric)
        if not ai_vals or not human_vals:
            continue
        ma, mh = _mean(ai_vals), _mean(human_vals)
        rel = (ma - mh) / max(abs(mh), _EPS)
        adjusted = direction * rel
        significant = abs(rel) >= significance_threshold
        deltas.append(
            MetricDelta(
                metric=metric,
                label=METRIC_LABEL[metric],
                ai_value=round(ma, 4),
                human_value=round(mh, 4),
                relative_delta=round(rel, 4),
                ai_better=adjusted > 0,
                significant=significant,
            )
        )

    compared = {d.metric for d in deltas}
    limitations = [*base_limitations, *_missing_metric_limitations(ai, human, compared)]

    if not deltas:
        return CreativeEvaluation(
            verdict=Verdict.INSUFFICIENT_EVIDENCE,
            confidence=0,
            ai_sample_size=len(ai),
            human_sample_size=len(human),
            unknown_sample_size=len(unknown),
            evidence=["No metric was measured on both AI and human samples."],
            limitations=[*limitations, "No shared metric to compare."],
        )

    significant = [d for d in deltas if d.significant]
    per_side_min = min(len(ai), len(human))
    evidence = [
        f"{len(ai)} AI-generated vs {len(human)} human-created comparable samples.",
        *(
            f"{d.label}: AI {'+' if d.relative_delta >= 0 else ''}{d.relative_delta * 100:.0f}% "
            f"vs human baseline{' (significant)' if d.significant else ''}."
            for d in deltas
        ),
    ]

    if not significant:
        return CreativeEvaluation(
            verdict=Verdict.NO_SIGNIFICANT_DIFFERENCE,
            confidence=_confidence(per_side_min=per_side_min, significant=[], agree_fraction=0.0),
            ai_sample_size=len(ai),
            human_sample_size=len(human),
            unknown_sample_size=len(unknown),
            metric_deltas=deltas,
            evidence=evidence,
            limitations=limitations,
        )

    ai_wins = [d for d in significant if d.ai_better]
    human_wins = [d for d in significant if not d.ai_better]
    winner_count = max(len(ai_wins), len(human_wins))
    agree_fraction = winner_count / len(significant)

    if len(ai_wins) > len(human_wins):
        verdict = Verdict.AI_OUTPERFORMING
    elif len(human_wins) > len(ai_wins):
        decisive = (
            len(human_wins) == len(significant)
            and len(human_wins) >= MIN_DECISIVE_METRICS
            and all(abs(d.relative_delta) >= DECISIVE_EFFECT for d in human_wins)
        )
        verdict = Verdict.HUMAN_OUTPERFORMING if decisive else Verdict.AI_UNDERPERFORMING
    else:
        verdict = Verdict.NO_SIGNIFICANT_DIFFERENCE

    return CreativeEvaluation(
        verdict=verdict,
        confidence=_confidence(
            per_side_min=per_side_min, significant=significant, agree_fraction=agree_fraction
        ),
        ai_sample_size=len(ai),
        human_sample_size=len(human),
        unknown_sample_size=len(unknown),
        metric_deltas=deltas,
        evidence=evidence,
        limitations=limitations,
    )


def diagnose_trend(observations: list[Observation], *, metric_label: str) -> TrendDirection:
    """Direction of a single metric over time — gated by data sufficiency so we
    never claim a trend (e.g. "revenue falling") from a day or two of data.

    Compares the mean of the first half of the window to the second half; a
    >=10% move either way is a trend, otherwise flat. Reuses the sufficiency
    ladder: below a week of coverage we return INSUFFICIENT.
    """
    suff = assess_sufficiency(observations)
    if not can_claim_trend(suff.level):
        return TrendDirection.INSUFFICIENT
    ordered = sorted(observations, key=lambda o: o.observed_at)
    mid = len(ordered) // 2
    first = _mean([o.value for o in ordered[:mid]])
    second = _mean([o.value for o in ordered[mid:]])
    if abs(first) < _EPS:
        return TrendDirection.INSUFFICIENT
    change = (second - first) / abs(first)
    _ = metric_label
    if change <= -0.10:
        return TrendDirection.FALLING
    if change >= 0.10:
        return TrendDirection.RISING
    return TrendDirection.FLAT
