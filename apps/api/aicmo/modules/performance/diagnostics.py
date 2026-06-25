"""Diagnostic rules for Phase 9.1.

Pure functions over `CreativeRollup` lists. No DB, no LLM. The
service layer feeds rollups in, persists drafts out.

Phase 9.1 ships TWO rules:

  1. WINNER         — the creative with the best CPL among rollups
                      whose sample is sufficient. Confidence scales
                      with sample size. Cap 90 (we have observed
                      outcomes, but a single CSV upload isn't a
                      multi-week experiment).

  2. BUDGET_REALLOC — recommend shifting spend toward the winner.
                      Only fires when there is at least one winner
                      AND at least one non-winner with comparable
                      sample, so the founder has somewhere to shift
                      FROM.

Per Constitution:
  - Confidence < 40 → never ship as CTA (Speculative band).
  - Min-sample gate is hard. If no rollup has `sufficient` sample,
    we return [] and the caller surfaces a ComingSoonCard.
  - Every draft must be turnable into a fully-populated AiRecommendation
    by `recommender.compose()` — drafts carry only the kind, impact
    category, evidence, and confidence; the words are added later.

The thresholds below are deliberately conservative. They live here as
named constants so they can be tuned without touching rule logic.
"""

from __future__ import annotations

from aicmo.modules.performance.intelligence import (
    audience as audience_layer,
    creatives as creatives_layer,
    offers as offers_layer,
    scaling as scaling_layer,
)
from aicmo.modules.performance.schemas import (
    CreativeRollup,
    DiagnosticDraft,
)

# ---------------------------------------------------------------------
#  Tunable thresholds — keep here for visibility
# ---------------------------------------------------------------------

# Sample-state thresholds. Mirrors `service.compute_sample_state`.
MIN_IMPRESSIONS = 500
MIN_SPEND_MICROS = 1_000 * 1_000_000  # 1,000 of the row's currency
MIN_CONVERSIONS = 1  # need at least one to compute CPL at all

# How much "better" the winner must be than the runner-up before we
# call it a winner with confidence. Below this, sample-size-aware
# bands kick in and shrink confidence.
WINNER_CPL_RATIO = 0.75  # winner CPL ≤ 75% of runner-up CPL


# ---------------------------------------------------------------------
#  Public surface
# ---------------------------------------------------------------------


def diagnose(rollups: list[CreativeRollup]) -> list[DiagnosticDraft]:
    """Run the full Phase 9.1 + 9.1.5 rule set over a brand's rollups.

    Always returns a list (may be empty). Caller decides whether to
    persist + render or surface a ComingSoonCard.

    9.1.5 orchestration:
      1. Run all 9.1 + 9.1.5 layers independently (pure functions).
      2. Apply family-based top-N gate (max 1 per family for the new
         layers; baseline 9.1 cards always allowed).
      3. Dedupe by subject — never ship two cards about the exact
         same creative.
      4. Sort by confidence desc.
    """
    drafts: list[DiagnosticDraft] = []

    # Filter to "sufficient" sample only — Constitution's
    # small-sample discipline. Everything below the floor is silent.
    candidates = [r for r in rollups if r.sample_state == "sufficient"]
    if not candidates:
        return drafts

    convertible = [r for r in candidates if r.cpl is not None]
    if not convertible:
        # Has spend + impressions but no conversions. Stay quiet
        # in 9.1/9.1.5; Phase 9.2 will add a "no conversions despite
        # spend" diagnostic. Hide-don't-fake.
        return drafts

    # ---- 9.1 baseline cards (always candidates) ---------------------
    winner_draft = _maybe_winner(convertible)
    if winner_draft is not None:
        drafts.append(winner_draft)

    realloc_draft = _maybe_budget_reallocation(convertible, winner_draft)
    if realloc_draft is not None:
        drafts.append(realloc_draft)

    # ---- 9.1.5 intelligence layers ---------------------------------
    audience_drafts = audience_layer.summarise_audiences(convertible)
    creative_drafts = (
        creatives_layer.summarise_concepts(convertible)
        + creatives_layer.summarise_emotions(convertible)
        + creatives_layer.summarise_funnel_stages(convertible)
        + creatives_layer.summarise_patterns(convertible)
    )
    offer_drafts = (
        offers_layer.summarise_offers(convertible)
        + offers_layer.summarise_pricing_sensitivity(convertible)
    )
    scaling_drafts = (
        scaling_layer.summarise_scale_candidates(convertible)
        + scaling_layer.summarise_budget_waste(convertible)
    )
    dna_drafts = creatives_layer.summarise_creative_dna(convertible)

    # Family top-N gate — at most ONE per layer (highest confidence
    # wins inside the layer). Approved ceiling: 7 cards total
    # (baseline 2 + audience 1 + creative 1 + offer 1 + scaling 1 + dna 1).
    drafts.extend(_top_one(audience_drafts))
    drafts.extend(_top_one(creative_drafts))
    drafts.extend(_top_one(offer_drafts))
    drafts.extend(_top_one(scaling_drafts))
    drafts.extend(_top_one(dna_drafts))

    # Dedup by subject_creative_ref — never ship two cards about the
    # same exact creative. Higher-confidence one wins. Baseline winner
    # is the most authoritative; layer cards lose ties to it.
    drafts = _dedup_by_subject(drafts)

    # Final order: confidence desc; ties broken by 'is baseline kind'.
    drafts.sort(
        key=lambda d: (
            -d.confidence,
            0 if d.kind in {"winner", "budget_reallocation"} else 1,
        )
    )
    return drafts


def _top_one(drafts: list[DiagnosticDraft]) -> list[DiagnosticDraft]:
    if not drafts:
        return []
    return [max(drafts, key=lambda d: d.confidence)]


def _dedup_by_subject(drafts: list[DiagnosticDraft]) -> list[DiagnosticDraft]:
    """Drop later cards that point at the same subject as an earlier,
    higher-confidence one. Layer cards yield to baseline cards on ties."""
    # Stable rank: confidence desc, baseline-first on tie.
    ordered = sorted(
        drafts,
        key=lambda d: (
            -d.confidence,
            0 if d.kind in {"winner", "budget_reallocation"} else 1,
        ),
    )
    seen: set[str] = set()
    out: list[DiagnosticDraft] = []
    for d in ordered:
        if d.subject_creative_ref in seen:
            continue
        seen.add(d.subject_creative_ref)
        out.append(d)
    return out


# ---------------------------------------------------------------------
#  Rule 1 — winner
# ---------------------------------------------------------------------


def _maybe_winner(rollups: list[CreativeRollup]) -> DiagnosticDraft | None:
    """Pick the best creative by CPL. Returns None if there isn't
    one (e.g. only one candidate AND its CPL is poor — there is no
    'winner' relative to anything)."""
    if not rollups:
        return None

    ranked = sorted(rollups, key=lambda r: r.cpl)  # type: ignore[arg-type]
    winner = ranked[0]

    # Confidence calibration: stronger margin + more conversions = more confident.
    # Hard cap 90 (single-upload observation, not multi-week experiment).
    confidence = _winner_confidence(winner, runner_up=ranked[1] if len(ranked) > 1 else None)

    # Speculative band — Constitution says don't ship.
    if confidence < 40:
        return None

    # Decide impact category. With conversion_value we can talk
    # revenue; without it we talk leads (we still have CPL).
    impact_category = "revenue" if winner.conversion_value > 0 else "lead"

    return DiagnosticDraft(
        kind="winner",
        impact_category=impact_category,
        confidence=confidence,
        subject_creative_ref=winner.creative_ref,
        evidence={
            "creative_ref": winner.creative_ref,
            "platform": winner.platform,
            "concept_family": winner.concept_family,
            "audience": winner.audience,
            "offer_type": winner.offer_type,
            "impressions": winner.impressions,
            "clicks": winner.clicks,
            "conversions": winner.conversions,
            "spend": winner.spend,
            "currency": winner.currency,
            "cpl": winner.cpl,
            "roas": winner.roas,
            "runner_up_ref": ranked[1].creative_ref if len(ranked) > 1 else None,
            "runner_up_cpl": ranked[1].cpl if len(ranked) > 1 else None,
        },
    )


def _winner_confidence(
    winner: CreativeRollup, *, runner_up: CreativeRollup | None
) -> int:
    """Confidence bands per Constitution:
        sample size component + margin component, capped 90.
    """
    base = 60  # met sample → at least Medium-band floor

    # Sample-size bonus — more conversions = more trust.
    if winner.conversions >= 50:
        base += 25
    elif winner.conversions >= 20:
        base += 15
    elif winner.conversions >= 5:
        base += 5

    # Margin bonus — if winner clearly outperforms next-best, +10.
    if runner_up is not None and runner_up.cpl is not None and winner.cpl is not None:
        if winner.cpl <= runner_up.cpl * WINNER_CPL_RATIO:
            base += 10

    return min(base, 90)


# ---------------------------------------------------------------------
#  Rule 2 — budget reallocation
# ---------------------------------------------------------------------


def _maybe_budget_reallocation(
    rollups: list[CreativeRollup], winner: DiagnosticDraft | None
) -> DiagnosticDraft | None:
    """Recommend shifting budget TOWARD the winner FROM an underperformer.

    Only fires if:
      - there is a winner (Rule 1 returned something), AND
      - at least one OTHER rollup has sufficient sample with materially
        worse CPL (≥ 1.5x the winner's CPL).
    """
    if winner is None:
        return None
    winner_ref = winner.subject_creative_ref
    winner_cpl = winner.evidence.get("cpl")
    if winner_cpl is None:
        return None

    others = [
        r for r in rollups
        if r.creative_ref != winner_ref and r.cpl is not None
    ]
    if not others:
        return None

    worst = max(others, key=lambda r: r.cpl)  # type: ignore[arg-type]
    if worst.cpl is None or worst.cpl < winner_cpl * 1.5:
        return None

    # Confidence is one band lower than the winner's — reallocation
    # is a derived recommendation, not a directly observed outcome.
    confidence = max(40, winner.confidence - 10)

    return DiagnosticDraft(
        kind="budget_reallocation",
        impact_category=winner.impact_category,
        confidence=confidence,
        # Subject is the underperformer (the card's recommendation is
        # about moving ITS budget). Also keeps the 9.1.5 dedup-by-subject
        # from collapsing winner + budget_reallocation onto one row.
        subject_creative_ref=worst.creative_ref,
        evidence={
            "winner_ref": winner_ref,
            "winner_cpl": winner_cpl,
            "winner_currency": winner.evidence.get("currency"),
            "underperformer_ref": worst.creative_ref,
            "underperformer_cpl": worst.cpl,
            "underperformer_spend": worst.spend,
            "underperformer_conversions": worst.conversions,
            "cpl_ratio": worst.cpl / winner_cpl if winner_cpl else None,
        },
    )
