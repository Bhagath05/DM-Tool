"""Deterministic feasibility scoring.

Pure Python — no LLM, no I/O. Sub-millisecond. Produces a 0-100 score and
a list of plain-English signals that explain it. The LLM never adjusts the
score; it only writes the narrative around it.

Design notes:
- Adjustments are small (±5–25). Goal is to land in a believable range, not
  to crown winners or punish ambition.
- The score is a SIGNAL of how much the user's stated goal stretches their
  current resources. A LOW score means "we should help them rephrase,"
  not "they're wrong to dream."
- Thresholds live in this file. Bumping them is a one-line change.
"""

from __future__ import annotations

import re
from typing import Iterable

from aicmo.modules.coach.schemas import FeasibilityLabel
from aicmo.modules.onboarding.schemas import BusinessProfileResponse

# ---------- tunable knobs ----------

_BASE_SCORE = 70  # neutral-positive starting point

_STAGE_ADJ: dict[str, int] = {
    # current_monthly_leads_band values from the conversational onboarding
    "starting": -5,
    "1-50": 0,
    "50-500": +5,
    "500-5000": +8,
    "5000+": +10,
}

_BUDGET_ADJ: dict[str, int] = {
    "0": -8,
    "under-200": -3,
    "200-1000": 0,
    "1000-5000": +5,
    "5000+": +8,
}

# Goal-magnitude keywords. Matched case-insensitively as whole-word-ish.
# Only ONE keyword counts (the most ambitious one found) — we don't stack
# penalties for synonyms.
_MAGNITUDE_KEYWORDS: list[tuple[str, int]] = [
    ("million", -25),
    ("1m", -25),
    ("100k", -15),
    ("50k", -10),
    ("10x", -12),
    ("100x", -20),
    ("viral", -8),
    ("explode", -8),
    ("overnight", -15),
    ("dominate", -10),
]

# Timeline-urgency phrases. Same single-match rule.
_URGENCY_PHRASES: list[tuple[str, int, str]] = [
    # phrase, score-adjustment, plain-english reason
    ("tomorrow", -25, "Tomorrow is too short a horizon for any meaningful marketing outcome."),
    ("this week", -22, "One week is below the cycle time of most acquisition channels."),
    ("7 days", -22, "Seven days is below the cycle time of most acquisition channels."),
    ("two weeks", -15, "Two weeks lets you test, but rarely lets you scale."),
    ("2 weeks", -15, "Two weeks lets you test, but rarely lets you scale."),
    ("30 days", -8, "A month is enough to validate, not always enough to scale."),
    ("one month", -8, "A month is enough to validate, not always enough to scale."),
    ("1 month", -8, "A month is enough to validate, not always enough to scale."),
    ("90 days", +2, "Three months is a healthy growth window."),
    ("3 months", +2, "Three months is a healthy growth window."),
    ("6 months", +5, "Six months is a realistic horizon for meaningful traction."),
    ("year", +5, "A year is realistic for compounding results."),
]


# ---------- parsing helpers ----------


_NUM_PATTERN = re.compile(r"\b(\d{1,3}(?:,\d{3})+|\d+)\s*([kKmM]?)\b")


def _extract_numbers(text: str) -> list[int]:
    """Pull out numeric goals like '1000 customers', '50k followers', '1M views'."""
    out: list[int] = []
    for match in _NUM_PATTERN.finditer(text):
        raw = match.group(1).replace(",", "")
        suffix = (match.group(2) or "").lower()
        try:
            n = int(raw)
        except ValueError:
            continue
        if suffix == "k":
            n *= 1_000
        elif suffix == "m":
            n *= 1_000_000
        out.append(n)
    return out


def _lower(s: str | None) -> str:
    return (s or "").lower()


def _first_match(text: str, table: Iterable[tuple[str, int]]) -> tuple[str, int] | None:
    """Find the first matching keyword/phrase. Used so synonyms don't stack."""
    t = text.lower()
    for kw, adj in table:
        if kw in t:
            return kw, adj
    return None


# ---------- scoring ----------


def score_goal(
    *, profile: BusinessProfileResponse, goal_text: str, timeline_hint: str | None
) -> tuple[int, list[str]]:
    """Compute feasibility score (0-100) and the signals that produced it.

    `signals` are user-readable strings (no jargon) so the frontend can
    surface them in a tooltip without re-asking the LLM.
    """
    score = _BASE_SCORE
    signals: list[str] = []

    # Stage maturity ----------------------------------------------------------
    stage = profile.current_monthly_leads_band
    if stage and stage in _STAGE_ADJ:
        delta = _STAGE_ADJ[stage]
        if delta != 0:
            score += delta
            signals.append(
                _stage_signal(stage, delta)
            )

    # Budget capacity ---------------------------------------------------------
    budget = profile.monthly_budget_band
    if budget and budget in _BUDGET_ADJ:
        delta = _BUDGET_ADJ[budget]
        if delta != 0:
            score += delta
            signals.append(_budget_signal(budget, delta))

    # Goal-magnitude keywords -------------------------------------------------
    magnitude_hit = _first_match(goal_text, _MAGNITUDE_KEYWORDS)
    if magnitude_hit:
        kw, delta = magnitude_hit
        score += delta
        signals.append(
            f"The phrase “{kw}” signals a large-magnitude goal — adjusted for ambition."
        )

    # Explicit numbers in the goal --------------------------------------------
    numbers = _extract_numbers(goal_text)
    if numbers:
        biggest = max(numbers)
        if biggest >= 1_000_000:
            score -= 20
            signals.append(
                f"The number {biggest:,} requires sustained scale most early-stage businesses don't reach quickly."
            )
        elif biggest >= 100_000:
            score -= 10
            signals.append(
                f"A target of {biggest:,} is ambitious — possible with focused channels and time."
            )
        elif biggest >= 10_000:
            score -= 3
            signals.append(
                f"Targeting {biggest:,} is realistic with consistent execution."
            )

    # Timeline urgency --------------------------------------------------------
    timeline_search_text = " ".join(filter(None, [timeline_hint, goal_text]))
    urgency = _first_urgency(timeline_search_text)
    if urgency is not None:
        phrase, delta, reason = urgency
        score += delta
        signals.append(reason)

    # Goal-vs-stage gap penalty -----------------------------------------------
    if stage in {"starting", "1-50"} and numbers:
        biggest = max(numbers)
        if biggest >= 1_000:
            score -= 5
            signals.append(
                "Big numerical goals get harder when current traction is still small. The path matters more than the headline."
            )

    # Channel realism ---------------------------------------------------------
    if profile.preferred_platforms is not None and len(profile.preferred_platforms) == 0:
        score -= 5
        signals.append(
            "No platforms selected yet — every plan starts with a place to publish."
        )

    return _clamp(score), signals


def _first_urgency(text: str) -> tuple[str, int, str] | None:
    t = text.lower()
    for phrase, delta, reason in _URGENCY_PHRASES:
        if phrase in t:
            return phrase, delta, reason
    return None


def _stage_signal(stage: str, delta: int) -> str:
    direction = "favours" if delta > 0 else "tightens"
    return f"Current traction ({stage}) {direction} the goal's feasibility."


def _budget_signal(budget: str, delta: int) -> str:
    direction = "supports" if delta > 0 else "constrains"
    label = "$0" if budget == "0" else f"the “{budget}” band"
    return f"A monthly budget of {label} {direction} how fast you can buy growth."


def _clamp(n: int) -> int:
    return max(0, min(100, n))


# ---------- label mapping ----------


def label_for_score(score: int) -> FeasibilityLabel:
    """Deterministic mapping. No surprises: same score → same label."""
    if score >= 80:
        return "Highly achievable"
    if score >= 65:
        return "Achievable with strong execution"
    if score >= 45:
        return "Aggressive but possible"
    if score >= 25:
        return "High-risk target"
    return "Unrealistic under current constraints"
