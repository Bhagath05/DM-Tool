"""Phase 7.4 — the experiment contract + deterministic evidence integrity.

This module is PURE: no DB, no LLM, no network. It gives BRO two things it did
not have before:

1. A structured, server-validated **experiment proposal** contract — the shape
   BRO fills in when it proposes a test (objective, hypothesis, primary metric,
   comparison, variants, audience/channel, measurement window, minimum evidence,
   known confounders, and explicit success + inconclusive conditions). The
   validator is the server's authority; a proposal that omits a success or an
   inconclusive condition, or that has fewer than two distinct variants, is
   rejected. The LLM can shape the wording, never bypass these rules.

2. A deterministic **evidence-integrity evaluator** over EXISTING measured
   experiment results. It answers "is there enough comparable evidence to reach
   a conclusion, and if so which way?" with one of five honest verdicts. It never
   invents a statistical-significance number or a confidence percentage: data
   strength is reported as the existing impression-based signal, labelled as a
   volume proxy, and anything short of a clean, comparable, adequately-powered
   contrast returns INSUFFICIENT_EVIDENCE, INCOMPARABLE or INCONCLUSIVE.

Nothing here writes a belief or asserts causation. A SUPPORTED/CONTRADICTED
verdict is a *measured association* between a variant and a metric — the caller
(and the existing belief-formation pipeline) treats it as correlation, never
cause.
"""

from __future__ import annotations

import enum
import hashlib
import json

from pydantic import BaseModel, ConfigDict, Field, field_validator


class PrimaryMetric(enum.StrEnum):
    """Metrics BRO may test on — each maps to a real measured ExperimentResult
    field, so a proposal can only target data the platform actually captures."""

    LEADS = "leads"
    ENGAGEMENT_RATE = "engagement_rate"
    CTR = "ctr"
    REACH = "reach"
    VIEWS = "views"


# How a metric reads: for a rate the absolute point difference matters; for a
# count the relative change matters. Used only to pick the effect calculation.
_RATE_METRICS = {PrimaryMetric.ENGAGEMENT_RATE, PrimaryMetric.CTR}

# --- deterministic evidence thresholds (tuned to be honest, not generous) ----
# Below this many impressions on a side we do not draw conclusions — mirrors the
# learning service's own "≥100 impressions = completed, earlier is noise" rule.
MIN_IMPRESSIONS = 100
# Relative effect on the primary metric smaller than this is within noise → we
# refuse to call a winner.
NOISE_BAND = 0.10
# If one side saw this many times more exposure than the other, the contrast is
# not fair — we downgrade to inconclusive rather than pretend it is clean.
MAX_EXPOSURE_RATIO = 3.0
# More than one differing creative variable between variants = confounded; we
# cannot attribute an effect to the one thing under test.
MAX_DIFFERING_VARIABLES = 1


class ExperimentVariant(BaseModel):
    """One arm of the comparison. ``variable_choices`` are the creative/targeting
    dimensions this arm fixes (hook, format, tone, cta, platform, …)."""

    model_config = ConfigDict(extra="forbid")

    label: str = Field(min_length=1, max_length=80)
    description: str = Field(default="", max_length=600)
    variable_choices: dict[str, str] = Field(default_factory=dict)

    @field_validator("variable_choices")
    @classmethod
    def _bound_choices(cls, v: dict[str, str]) -> dict[str, str]:
        if len(v) > 12:
            raise ValueError("a variant may fix at most 12 variables")
        return {str(k)[:48]: str(val)[:120] for k, val in v.items()}


class ExperimentProposal(BaseModel):
    """BRO's structured proposal for a test. Server-validated; the fields map to
    the questions a real marketing experiment must answer before it runs."""

    model_config = ConfigDict(extra="forbid")

    business_objective: str = Field(min_length=1, max_length=400)
    hypothesis: str = Field(min_length=1, max_length=600)
    primary_metric: PrimaryMetric
    comparison: str = Field(min_length=1, max_length=400)
    variants: list[ExperimentVariant] = Field(min_length=2, max_length=6)
    audience: str = Field(default="", max_length=300)
    channel: str = Field(default="", max_length=80)
    measurement_window_days: int = Field(ge=1, le=90)
    minimum_impressions: int = Field(default=MIN_IMPRESSIONS, ge=1, le=10_000_000)
    confounders: list[str] = Field(default_factory=list, max_length=12)
    success_condition: str = Field(min_length=1, max_length=400)
    inconclusive_condition: str = Field(min_length=1, max_length=400)

    @field_validator("variants")
    @classmethod
    def _distinct_variants(cls, v: list[ExperimentVariant]) -> list[ExperimentVariant]:
        labels = [variant.label.strip().lower() for variant in v]
        if len(set(labels)) != len(labels):
            raise ValueError("variant labels must be distinct")
        return v

    @field_validator("confounders")
    @classmethod
    def _bound_confounders(cls, v: list[str]) -> list[str]:
        return [str(c)[:160] for c in v]


class ExperimentContractError(ValueError):
    """A proposal violated the server-side experiment contract."""


def validate_proposal(data: dict | ExperimentProposal) -> ExperimentProposal:
    """Validate (or re-validate) a proposal. Raises ExperimentContractError with a
    compact message — never leaks raw validation internals to the caller."""
    if isinstance(data, ExperimentProposal):
        return data
    try:
        return ExperimentProposal.model_validate(data)
    except Exception as exc:  # pydantic ValidationError or TypeError
        count = getattr(exc, "error_count", lambda: 1)()
        raise ExperimentContractError(f"invalid experiment proposal: {count} problem(s)") from exc


def proposal_fingerprint(proposal: ExperimentProposal) -> str:
    """Stable fingerprint over the decision-bearing fields, so re-proposing the
    same experiment is idempotent (same fingerprint → same draft id upstream).
    Variant order does not matter; wording of audience/confounders does not."""
    core = {
        "objective": proposal.business_objective.strip().lower(),
        "hypothesis": proposal.hypothesis.strip().lower(),
        "metric": proposal.primary_metric.value,
        "channel": proposal.channel.strip().lower(),
        "variants": sorted(
            v.label.strip().lower() for v in proposal.variants
        ),
    }
    blob = json.dumps(core, sort_keys=True, separators=(",", ":"))
    return hashlib.sha256(blob.encode()).hexdigest()[:32]


# ---------------------------------------------------------------------
#  Evidence integrity — deterministic verdicts over measured results
# ---------------------------------------------------------------------
class EvidenceVerdict(enum.StrEnum):
    INSUFFICIENT_EVIDENCE = "insufficient_evidence"  # not enough measured volume
    INCOMPARABLE = "incomparable"  # objective/channel/format don't match
    INCONCLUSIVE = "inconclusive"  # comparable + powered, but no clear effect
    SUPPORTED = "supported"  # variant measurably beat the baseline
    CONTRADICTED = "contradicted"  # variant measurably lost to the baseline


class EvidenceCheck(BaseModel):
    name: str
    passed: bool
    detail: str = ""


class EvidenceAssessment(BaseModel):
    """The honest result of weighing measured evidence. ``effect`` is the signed
    relative change on the primary metric (primary vs baseline), present only
    when a real comparison was possible. ``data_strength`` is the EXISTING
    impression-volume confidence proxy (0 to 1), never a fabricated significance."""

    verdict: EvidenceVerdict
    primary_metric: PrimaryMetric
    primary_value: float | None = None
    baseline_value: float | None = None
    effect: float | None = None
    data_strength: float = 0.0
    checks: list[EvidenceCheck] = Field(default_factory=list)
    reasons: list[str] = Field(default_factory=list)
    note: str = (
        "This weighs measured association only — it is not proof of cause. "
        "Confidence/belief changes are derived by the platform, never asserted here."
    )


class _Side(BaseModel):
    """A normalized view of one experiment arm, built by the adapter from the
    existing CampaignExperiment + ExperimentResult rows. Pure data."""

    model_config = ConfigDict(extra="forbid")

    goal: str | None = None
    asset_type: str | None = None
    platform: str | None = None
    variable_choices: dict = Field(default_factory=dict)
    impressions: int = 0
    metric_value: float | None = None
    data_strength: float = 0.0


def _impression_strength(impressions: int) -> float:
    """Monotone volume → 0 to 1 strength, identical bands to the learning service's
    ``_impression_confidence`` (kept local so this module stays import-pure)."""
    if impressions <= 0:
        return 0.1
    if impressions < 50:
        return 0.3
    if impressions < 250:
        return 0.5
    if impressions < 1000:
        return 0.7
    return 0.85


def assess_evidence(
    *,
    primary_metric: PrimaryMetric,
    primary: _Side,
    baseline: _Side | None,
) -> EvidenceAssessment:
    """Deterministically weigh measured evidence for a variant (vs an optional
    baseline). Pure. Returns one of five verdicts and the checks behind it."""
    checks: list[EvidenceCheck] = []
    reasons: list[str] = []
    p_strength = _impression_strength(primary.impressions)

    # --- volume floor (both sides) ---------------------------------------
    primary_ok = primary.impressions >= MIN_IMPRESSIONS and primary.metric_value is not None
    checks.append(EvidenceCheck(
        name="primary_volume",
        passed=primary_ok,
        detail=f"{primary.impressions} impressions (need ≥{MIN_IMPRESSIONS})",
    ))
    if not primary_ok:
        reasons.append("The variant has too little measured volume to draw a conclusion.")
        return EvidenceAssessment(
            verdict=EvidenceVerdict.INSUFFICIENT_EVIDENCE,
            primary_metric=primary_metric,
            primary_value=primary.metric_value,
            data_strength=p_strength,
            checks=checks,
            reasons=reasons,
        )

    # --- single-arm readiness (no baseline) ------------------------------
    if baseline is None:
        reasons.append("No comparison variant was provided — readiness is adequate but a winner cannot be declared.")
        checks.append(EvidenceCheck(name="has_baseline", passed=False, detail="no baseline experiment supplied"))
        return EvidenceAssessment(
            verdict=EvidenceVerdict.INCONCLUSIVE,
            primary_metric=primary_metric,
            primary_value=primary.metric_value,
            data_strength=p_strength,
            checks=checks,
            reasons=reasons,
        )

    b_strength = _impression_strength(baseline.impressions)
    baseline_ok = baseline.impressions >= MIN_IMPRESSIONS and baseline.metric_value is not None
    checks.append(EvidenceCheck(
        name="baseline_volume",
        passed=baseline_ok,
        detail=f"{baseline.impressions} impressions (need ≥{MIN_IMPRESSIONS})",
    ))
    if not baseline_ok:
        reasons.append("The baseline has too little measured volume to compare against.")
        return EvidenceAssessment(
            verdict=EvidenceVerdict.INSUFFICIENT_EVIDENCE,
            primary_metric=primary_metric,
            primary_value=primary.metric_value,
            baseline_value=baseline.metric_value,
            data_strength=min(p_strength, b_strength),
            checks=checks,
            reasons=reasons,
        )

    data_strength = min(p_strength, b_strength)

    # --- comparability ---------------------------------------------------
    same_objective = not (primary.goal and baseline.goal) or primary.goal == baseline.goal
    same_format = not (primary.asset_type and baseline.asset_type) or primary.asset_type == baseline.asset_type
    same_channel = not (primary.platform and baseline.platform) or primary.platform == baseline.platform
    checks.append(EvidenceCheck(name="comparable_objective", passed=same_objective,
                                detail=f"{primary.goal!r} vs {baseline.goal!r}"))
    checks.append(EvidenceCheck(name="comparable_format", passed=same_format,
                                detail=f"{primary.asset_type!r} vs {baseline.asset_type!r}"))
    checks.append(EvidenceCheck(name="comparable_channel", passed=same_channel,
                                detail=f"{primary.platform!r} vs {baseline.platform!r}"))
    if not (same_objective and same_format):
        reasons.append("The two arms pursue different objectives or formats — they are not comparable.")
        return EvidenceAssessment(
            verdict=EvidenceVerdict.INCOMPARABLE,
            primary_metric=primary_metric,
            primary_value=primary.metric_value,
            baseline_value=baseline.metric_value,
            data_strength=data_strength,
            checks=checks,
            reasons=reasons,
        )

    # --- fair-exposure + confounder gates (downgrade, never fabricate) ---
    lo, hi = sorted((max(primary.impressions, 1), max(baseline.impressions, 1)))
    exposure_ratio = hi / lo
    fair_exposure = exposure_ratio <= MAX_EXPOSURE_RATIO
    checks.append(EvidenceCheck(name="fair_exposure", passed=fair_exposure,
                                detail=f"exposure ratio {exposure_ratio:.1f}x (max {MAX_EXPOSURE_RATIO:g}x)"))

    differing = _differing_variables(primary.variable_choices, baseline.variable_choices)
    single_variable = differing <= MAX_DIFFERING_VARIABLES
    checks.append(EvidenceCheck(name="single_variable", passed=single_variable,
                                detail=f"{differing} creative variable(s) differ (max {MAX_DIFFERING_VARIABLES})"))

    pv = float(primary.metric_value)  # type: ignore[arg-type]
    bv = float(baseline.metric_value)  # type: ignore[arg-type]
    effect = _relative_effect(primary_metric, pv, bv)

    if not fair_exposure:
        reasons.append("Exposure was too unequal between the arms to trust the contrast.")
    if not single_variable:
        reasons.append("More than one creative variable differs — any effect is confounded.")
    if not same_channel:
        reasons.append("Note: the arms ran on different channels — interpret the comparison with care.")

    if not (fair_exposure and single_variable):
        return EvidenceAssessment(
            verdict=EvidenceVerdict.INCONCLUSIVE,
            primary_metric=primary_metric,
            primary_value=pv, baseline_value=bv, effect=effect,
            data_strength=data_strength, checks=checks, reasons=reasons,
        )

    # --- effect size vs noise band ---------------------------------------
    if effect is None or abs(effect) < NOISE_BAND:
        reasons.append(f"The measured difference is within the {NOISE_BAND:.0%} noise band — no clear winner.")
        verdict = EvidenceVerdict.INCONCLUSIVE
    elif effect > 0:
        reasons.append(f"The variant measurably outperformed the baseline on {primary_metric.value} (+{effect:.0%}).")
        verdict = EvidenceVerdict.SUPPORTED
    else:
        reasons.append(f"The variant measurably underperformed the baseline on {primary_metric.value} ({effect:.0%}).")
        verdict = EvidenceVerdict.CONTRADICTED

    return EvidenceAssessment(
        verdict=verdict,
        primary_metric=primary_metric,
        primary_value=pv, baseline_value=bv, effect=effect,
        data_strength=data_strength, checks=checks, reasons=reasons,
    )


def _relative_effect(metric: PrimaryMetric, primary: float, baseline: float) -> float | None:
    """Signed effect of primary vs baseline. Rates use absolute point difference
    normalized by the baseline's own scale; counts use relative change."""
    if metric in _RATE_METRICS:
        # Rates are already 0 to 1 fractions; relative change on the baseline rate.
        if baseline == 0:
            return None if primary == 0 else 1.0
        return (primary - baseline) / baseline
    if baseline == 0:
        return None if primary == 0 else 1.0
    return (primary - baseline) / baseline


def _differing_variables(a: dict, b: dict) -> int:
    """Count creative variables whose value differs (or is present on one side
    only) — the confounder signal."""
    keys = set(a) | set(b)
    return sum(1 for k in keys if str(a.get(k)) != str(b.get(k)))
