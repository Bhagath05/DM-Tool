"""Compose Constitution-shaped diagnostic cards from drafts.

Pure functions. No LLM in Phase 9.1 — the words are deterministic
templates parameterised on the evidence. This is deliberate:
LLM-only narrative is reserved for Phase 9.2 (and even then, gated
behind L1/L2 rule triggers per PERFORMANCE_INTELLIGENCE.md §4).

Every card we emit answers the founder's five questions:
  - What happened?
  - Why?
  - What should I do next?
  - Expected business impact
  - How confident are you?

Each function returns a 4-tuple of strings: (what, why, recommendation,
expected_result). The Pydantic schema validates non-empty at the API
edge; the templates here enforce it by construction.
"""

from __future__ import annotations

from aicmo.modules.performance.schemas import (
    DiagnosticDraft,
    PerformanceDiagnosticCard,
)

# Bare-minimum money formatter. Account currency, never hardcoded INR.
def _money(amount: float | int | None, currency: str | None) -> str:
    if amount is None or currency is None:
        return "—"
    if amount >= 1000:
        # Show whole-rupees / whole-dollars at scale to keep founder
        # sentences readable.
        return f"{currency} {int(round(amount)):,}"
    return f"{currency} {amount:,.2f}"


def _short_ref(ref: str, max_len: int = 48) -> str:
    """Trim long Meta ad names so they read cleanly inline."""
    ref = ref.strip()
    if len(ref) <= max_len:
        return ref
    return ref[: max_len - 1].rstrip() + "…"


# ---------------------------------------------------------------------
#  Public surface
# ---------------------------------------------------------------------


def compose(draft: DiagnosticDraft) -> tuple[str, str, str, str, str]:
    """Returns (what_happened, why, recommendation, expected_result, reason).

    Why a single dispatch function:
      - It's the one place where evidence-keys are read by name. If
        the schema changes, you only fix it here.
      - Tests in `test_recommender.py` pin every draft kind through
        this entry point so we can't drift.

    9.1 ships: winner, budget_reallocation.
    9.1.5 ships: audience_winner, audience_loser, concept_winner,
                 emotion_winner, funnel_winner, pattern_winner,
                 offer_winner, offer_pricing_sensitivity,
                 scale_candidate, budget_waste, creative_dna.
    """
    # 9.1 baseline
    if draft.kind == "winner":
        return _winner(draft)
    if draft.kind == "budget_reallocation":
        return _budget_reallocation(draft)
    # 9.1.5 — Audience Intelligence
    if draft.kind == "audience_winner":
        return _audience_winner(draft)
    if draft.kind == "audience_loser":
        return _audience_loser(draft)
    # 9.1.5 — Creative Intelligence
    if draft.kind == "concept_winner":
        return _concept_winner(draft)
    if draft.kind == "emotion_winner":
        return _emotion_winner(draft)
    if draft.kind == "funnel_winner":
        return _funnel_winner(draft)
    if draft.kind == "pattern_winner":
        return _pattern_winner(draft)
    # 9.1.5 — Offer Intelligence
    if draft.kind == "offer_winner":
        return _offer_winner(draft)
    if draft.kind == "offer_pricing_sensitivity":
        return _offer_pricing(draft)
    # 9.1.5 — Scaling Intelligence
    if draft.kind == "scale_candidate":
        return _scale_candidate(draft)
    if draft.kind == "budget_waste":
        return _budget_waste(draft)
    # 9.1.5 — Apex card
    if draft.kind == "creative_dna":
        return _creative_dna(draft)
    raise NotImplementedError(f"recommender has no template for kind={draft.kind!r}")


def to_card(
    draft: DiagnosticDraft,
    *,
    record_id,
    status: str = "open",
    created_at,
) -> PerformanceDiagnosticCard:
    """Bridge — combine `compose()` output with the DB-side fields
    to produce the response shape. Used by `service` after insert."""
    what, why, rec, expected, reason = compose(draft)
    return PerformanceDiagnosticCard(
        id=record_id,
        kind=draft.kind,
        impact_category=draft.impact_category,
        what_happened=what,
        why=why,
        recommendation=rec,
        expected_result=expected,
        reason=reason,
        confidence=draft.confidence,
        evidence=draft.evidence,
        status=status,  # type: ignore[arg-type]
        created_at=created_at,
    )


# ---------------------------------------------------------------------
#  Per-kind templates
# ---------------------------------------------------------------------


def _winner(draft: DiagnosticDraft) -> tuple[str, str, str, str, str]:
    e = draft.evidence
    ref = _short_ref(e["creative_ref"])
    cpl = e.get("cpl")
    currency = e.get("currency")
    conv = e.get("conversions") or 0
    spend = e.get("spend") or 0
    audience = e.get("audience")
    concept = e.get("concept_family")
    offer = e.get("offer_type")

    # What happened — plain-English headline.
    what = (
        f"Your best-performing creative right now is “{ref}”. "
        f"It brought in {conv} lead{'s' if conv != 1 else ''} "
        f"at {_money(cpl, currency)} each."
    )

    # Why — point at the cheapest-cost-per-lead vs everything else.
    runner = e.get("runner_up_ref")
    runner_cpl = e.get("runner_up_cpl")
    if runner and runner_cpl:
        why = (
            f"On the rows you uploaded, it converted at "
            f"{_money(cpl, currency)} per lead — "
            f"cheaper than “{_short_ref(runner)}” at "
            f"{_money(runner_cpl, currency)}."
        )
    else:
        why = (
            f"It met the minimum sample size and produced leads at "
            f"{_money(cpl, currency)} each — the only creative that did."
        )

    # Recommendation — concrete, single next step.
    tag_hint = _tag_hint(concept=concept, audience=audience, offer=offer)
    rec = (
        f"Keep this creative running and make 2–3 more variants in the same "
        f"direction{tag_hint}. Don't change the offer or audience yet — "
        f"protect what's working."
    )

    # Expected result — banded by confidence.
    if draft.confidence >= 75:
        expected = (
            f"Doubling down on this winner usually adds 30–50% more leads "
            f"over the next 2 weeks at a similar cost per lead."
        )
    else:
        expected = (
            f"If the next round of variants performs like this one, "
            f"expect 15–30% more leads next period at a similar cost per lead."
        )

    # Reason — point at the evidence (not the prompt).
    reason = (
        f"Based on {e.get('impressions', 0):,} impressions, "
        f"{e.get('clicks', 0):,} clicks, and {conv} converted leads "
        f"from {_money(spend, currency)} of spend in the file you uploaded."
    )

    return what, why, rec, expected, reason


def _budget_reallocation(draft: DiagnosticDraft) -> tuple[str, str, str, str, str]:
    e = draft.evidence
    winner = _short_ref(e["winner_ref"])
    loser = _short_ref(e["underperformer_ref"])
    currency = e.get("winner_currency")
    win_cpl = e.get("winner_cpl")
    lose_cpl = e.get("underperformer_cpl")
    lose_spend = e.get("underperformer_spend") or 0
    ratio = e.get("cpl_ratio") or 0

    what = (
        f"“{loser}” is costing you about {ratio:.1f}× more per lead than "
        f"your winner “{winner}”."
    )

    why = (
        f"On the rows you uploaded, “{loser}” converted at "
        f"{_money(lose_cpl, currency)} per lead vs "
        f"{_money(win_cpl, currency)} for “{winner}”. "
        f"Same audience, materially worse outcome."
    )

    rec = (
        f"Move the spend behind “{loser}” over to “{winner}” for the next "
        f"7 days. Don't pause “{loser}” yet — just shift the budget."
    )

    # Sized to the underperformer's spend — concrete, not generic.
    if lose_spend > 0 and win_cpl and lose_cpl:
        extra_leads_if_shifted = int(lose_spend / win_cpl) - int(lose_spend / lose_cpl)
        if extra_leads_if_shifted > 0:
            expected = (
                f"Shifting {_money(lose_spend, currency)} from “{loser}” "
                f"to “{winner}” at the current rates should produce roughly "
                f"{extra_leads_if_shifted} more leads next week — same money."
            )
        else:
            expected = (
                f"At the current rates this should preserve your lead volume "
                f"while improving your cost per lead."
            )
    else:
        expected = (
            f"Expect a noticeable drop in cost per lead within the first "
            f"week if you shift the spend."
        )

    reason = (
        f"Based on cost-per-lead comparison across creatives in the file "
        f"you uploaded — winner at {_money(win_cpl, currency)}, "
        f"underperformer at {_money(lose_cpl, currency)}."
    )

    return what, why, rec, expected, reason


def _tag_hint(
    *,
    concept: str | None,
    audience: str | None,
    offer: str | None,
) -> str:
    """Soft hint that only renders when we have actual tags. Keeps
    the recommendation honest when tags are NULL (older creatives)."""
    bits = []
    if concept:
        bits.append(f"same '{concept.replace('_', ' ')}' angle")
    if audience:
        bits.append(f"targeted at the same audience ({audience.replace('_', ' ')})")
    if offer and offer != "none":
        bits.append(f"keeping the {offer.replace('_', ' ')} offer")
    if not bits:
        return ""
    return " — " + ", ".join(bits)


# ---------------------------------------------------------------------
#  9.1.5 — founder-language helpers
# ---------------------------------------------------------------------


def _human_tag(value: str | None) -> str:
    """Snake-case tag → space-separated phrase. Defensive: returns
    'an untagged group' rather than 'None' if the value is missing."""
    if not value:
        return "an untagged group"
    return value.replace("_", " ").strip()


def _human_audience(value: str | None) -> str:
    """Audience labels read more naturally with a soft prefix."""
    if not value:
        return "untagged people"
    return _human_tag(value)


def _human_funnel(stage: str | None) -> str:
    """Funnel stages translated to plain-language buyer states."""
    return {
        "awareness": "people who are new to your business",
        "consideration": "people who are weighing their options",
        "conversion": "people who are ready to buy or book",
        "retention": "your existing customers",
    }.get(stage or "", "an untagged buyer group")


def _human_offer(offer: str | None) -> str:
    """Offer type → founder phrase. 'none' is intentional, not absent."""
    return {
        "discount": "a discount",
        "free_trial": "a free trial",
        "consultation": "a free consultation",
        "bundle": "a bundle",
        "promotion": "a promotion",
        "seasonal": "a seasonal offer",
        "none": "no special offer",
    }.get(offer or "", "your current offer")


# ---------------------------------------------------------------------
#  9.1.5 — Audience templates
# ---------------------------------------------------------------------


def _audience_winner(draft: DiagnosticDraft) -> tuple[str, str, str, str, str]:
    e = draft.evidence
    aud = _human_audience(e.get("audience"))
    cpl = e.get("cpl")
    runner = _human_audience(e.get("runner_up_audience"))
    runner_cpl = e.get("runner_up_cpl")
    currency = e.get("currency")
    convs = e.get("conversions") or 0
    n_creatives = e.get("creatives_count") or 0

    what = (
        f"People matching “{aud}” are your best customer group "
        f"right now — they brought in {convs} lead"
        f"{'s' if convs != 1 else ''} at {_money(cpl, currency)} each."
    )
    why = (
        f"Across {n_creatives} creative{'s' if n_creatives != 1 else ''}, "
        f"this group converted at {_money(cpl, currency)} per lead — "
        f"cheaper than “{runner}” at {_money(runner_cpl, currency)}."
    )
    rec = (
        f"For your next 2 ads, focus on people matching “{aud}”. "
        f"Don't dilute the audience to chase reach yet — protect what's working."
    )
    if draft.confidence >= 75:
        expected = (
            f"Doubling down on this group usually adds 40–60% more leads "
            f"at the same spend over the next 2 weeks."
        )
    else:
        expected = (
            f"You should see 15–30% more leads at the same spend once your "
            f"next round of ads zeroes in on this group."
        )
    reason = (
        f"Based on comparison across {e.get('field_size', 0)} audience groups "
        f"in the file you uploaded."
    )
    return what, why, rec, expected, reason


def _audience_loser(draft: DiagnosticDraft) -> tuple[str, str, str, str, str]:
    e = draft.evidence
    aud = _human_audience(e.get("audience"))
    winner_aud = _human_audience(e.get("winner_audience"))
    cpl = e.get("cpl")
    win_cpl = e.get("winner_cpl")
    ratio = e.get("cpl_ratio") or 0
    spend = e.get("spend") or 0
    currency = e.get("currency")

    what = (
        f"People matching “{aud}” are costing you about {ratio:.1f}× "
        f"more per lead than “{winner_aud}”."
    )
    why = (
        f"You spent {_money(spend, currency)} on this group at "
        f"{_money(cpl, currency)} per lead. Your “{winner_aud}” group "
        f"is producing leads at {_money(win_cpl, currency)} — same money, "
        f"very different result."
    )
    rec = (
        f"For the next 2 weeks, stop adding new ads aimed at “{aud}”. "
        f"Send that budget to your “{winner_aud}” group instead — don't "
        f"pause the existing ads, just don't feed the losing audience."
    )
    expected = (
        f"Shifting this budget should produce roughly the same number of "
        f"leads at a much lower cost — your overall cost per lead should drop "
        f"noticeably within the first week."
    )
    reason = (
        f"Based on cost-per-lead comparison across audience groups in your upload."
    )
    return what, why, rec, expected, reason


# ---------------------------------------------------------------------
#  9.1.5 — Creative templates
# ---------------------------------------------------------------------


def _concept_winner(draft: DiagnosticDraft) -> tuple[str, str, str, str, str]:
    return _generic_creative_winner(
        draft,
        tag_key="concept_family",
        noun="angle",
        action_hint="Make 2-3 more ads using the same angle.",
    )


def _emotion_winner(draft: DiagnosticDraft) -> tuple[str, str, str, str, str]:
    return _generic_creative_winner(
        draft,
        tag_key="emotion",
        noun="feeling",
        action_hint=(
            "Write your next 2 ads with the same feeling — let the tone "
            "do the work rather than chasing a new style."
        ),
    )


def _funnel_winner(draft: DiagnosticDraft) -> tuple[str, str, str, str, str]:
    e = draft.evidence
    stage_value = e.get("funnel_stage")
    stage_phrase = _human_funnel(stage_value if isinstance(stage_value, str) else None)
    runner_stage_value = e.get("runner_up")
    runner_phrase = _human_funnel(
        runner_stage_value if isinstance(runner_stage_value, str) else None
    )
    cpl = e.get("cpl")
    runner_cpl = e.get("runner_up_cpl")
    currency = e.get("currency")
    convs = e.get("conversions") or 0

    what = (
        f"Ads aimed at {stage_phrase} are bringing you the cheapest leads — "
        f"{convs} lead{'s' if convs != 1 else ''} at {_money(cpl, currency)} each."
    )
    why = (
        f"Same money buys roughly the same volume from {runner_phrase}, "
        f"but they cost {_money(runner_cpl, currency)} each by comparison."
    )
    rec = (
        f"For your next 2 ads, write to {stage_phrase}. Save the "
        f"{runner_phrase}-style angles for when you have a bigger budget to spare."
    )
    expected = (
        f"Leaning into this part of the buyer journey should keep your cost "
        f"per lead steady while volume grows 20–40% next period."
    )
    reason = (
        f"Based on comparing each funnel stage across the file you uploaded."
    )
    return what, why, rec, expected, reason


def _pattern_winner(draft: DiagnosticDraft) -> tuple[str, str, str, str, str]:
    e = draft.evidence
    concept = _human_tag(e.get("concept_family") if isinstance(e.get("concept_family"), str) else None)
    emotion = _human_tag(e.get("emotion") if isinstance(e.get("emotion"), str) else None)
    cpl = e.get("cpl")
    currency = e.get("currency")
    convs = e.get("conversions") or 0

    what = (
        f"Your strongest hook so far combines the “{concept}” angle "
        f"with a {emotion} tone — {convs} lead"
        f"{'s' if convs != 1 else ''} at {_money(cpl, currency)} each."
    )
    why = (
        f"Across your other combinations, nothing else matched both the "
        f"angle and the feeling at this cost per lead."
    )
    rec = (
        f"Write your next batch of ads using a “{concept}” angle and a "
        f"{emotion} tone. Vary the copy and image, but keep the hook the same."
    )
    expected = (
        f"Variants in this style typically hold the cost per lead within "
        f"10–20% of the original while adding fresh volume."
    )
    reason = (
        f"Based on every angle × feeling combination in the file you uploaded. "
        f"Note: we infer the hook from the angle and feeling — once we read "
        f"the headline directly, this gets sharper."
    )
    return what, why, rec, expected, reason


def _generic_creative_winner(
    draft: DiagnosticDraft,
    *,
    tag_key: str,
    noun: str,
    action_hint: str,
) -> tuple[str, str, str, str, str]:
    e = draft.evidence
    value_raw = e.get(tag_key)
    label = _human_tag(value_raw if isinstance(value_raw, str) else None)
    runner_label = _human_tag(
        e.get("runner_up") if isinstance(e.get("runner_up"), str) else None
    )
    cpl = e.get("cpl")
    runner_cpl = e.get("runner_up_cpl")
    currency = e.get("currency")
    convs = e.get("conversions") or 0
    n_creatives = e.get("creatives_count") or 0

    what = (
        f"The “{label}” {noun} is your strongest performer so far — "
        f"{convs} lead{'s' if convs != 1 else ''} at "
        f"{_money(cpl, currency)} each across {n_creatives} ad"
        f"{'s' if n_creatives != 1 else ''}."
    )
    why = (
        f"By comparison, the next best {noun} (“{runner_label}”) is producing "
        f"leads at {_money(runner_cpl, currency)} — same idea, harder dollars."
    )
    rec = action_hint
    if draft.confidence >= 75:
        expected = (
            f"Sticking with this {noun} for your next round of ads should add "
            f"30–50% more leads at a similar cost per lead."
        )
    else:
        expected = (
            f"Sticking with this {noun} should add 15–30% more leads at a "
            f"similar cost per lead — a small but reliable lift."
        )
    reason = (
        f"Based on comparing every {noun} across the file you uploaded."
    )
    return what, why, rec, expected, reason


# ---------------------------------------------------------------------
#  9.1.5 — Offer templates
# ---------------------------------------------------------------------


def _offer_winner(draft: DiagnosticDraft) -> tuple[str, str, str, str, str]:
    e = draft.evidence
    offer = _human_offer(e.get("offer_type") if isinstance(e.get("offer_type"), str) else None)
    runner = _human_offer(
        e.get("runner_up_offer") if isinstance(e.get("runner_up_offer"), str) else None
    )
    cvr_pct = (e.get("cvr") or 0) * 100
    runner_cvr_pct = (e.get("runner_up_cvr") or 0) * 100

    what = (
        f"When you led with {offer}, people converted about twice as often "
        f"as when you led with {runner}."
    )
    why = (
        f"{offer.capitalize()} converted at {cvr_pct:.1f}% of clicks vs "
        f"{runner_cvr_pct:.1f}% for {runner}. People responded more to the "
        f"first offer."
    )
    rec = (
        f"For your next 2 campaigns, lead with {offer}. Keep {runner} as a "
        f"follow-up message for people who don't act on the first one."
    )
    expected = (
        f"Switching the lead offer typically lifts bookings 30–50% at the "
        f"same ad spend."
    )
    reason = (
        f"Based on comparing every offer in the file you uploaded by "
        f"how often people who clicked went on to convert."
    )
    return what, why, rec, expected, reason


def _offer_pricing(draft: DiagnosticDraft) -> tuple[str, str, str, str, str]:
    e = draft.evidence
    better = e.get("better_side")
    ratio = e.get("cvr_ratio") or 0
    better_cvr_pct = (e.get("better_cvr") or 0) * 100
    worse_cvr_pct = (e.get("worse_cvr") or 0) * 100

    if better == "discount_on":
        what = (
            f"Ads that offered a discount converted about {ratio:.1f}× better "
            f"than ads without one."
        )
        why = (
            f"With a discount, {better_cvr_pct:.1f}% of clickers acted vs "
            f"{worse_cvr_pct:.1f}% without one. People in your audience "
            f"respond strongly to a clear price drop."
        )
        rec = (
            f"Test a slightly bigger discount on your next campaign. "
            f"Don't make it permanent — use it to bring new customers in, "
            f"then sell them at full price the second time."
        )
        expected = (
            f"A clearer discount-led campaign typically lifts bookings "
            f"20–40% within the first 2 weeks. Watch your repeat-buy rate "
            f"so the discount doesn't train people to wait."
        )
    else:
        what = (
            f"Ads without a discount converted about {ratio:.1f}× better than "
            f"ads with one."
        )
        why = (
            f"At full price, {better_cvr_pct:.1f}% of clickers acted vs "
            f"{worse_cvr_pct:.1f}% with a discount. People here trust the "
            f"value — the discount may actually be making them suspicious."
        )
        rec = (
            f"Stop leading with a discount in your next 2 campaigns. Lead "
            f"with what makes the product worth the full price instead."
        )
        expected = (
            f"Dropping the discount from the headline often holds volume "
            f"steady while raising your average sale by 15–30%."
        )
    reason = (
        f"Based on a side-by-side of {e.get('better_creatives', 0)} ads with the "
        f"better-performing setup vs {e.get('worse_creatives', 0)} on the other side."
    )
    return what, why, rec, expected, reason


# ---------------------------------------------------------------------
#  9.1.5 — Scaling templates
# ---------------------------------------------------------------------


def _scale_candidate(draft: DiagnosticDraft) -> tuple[str, str, str, str, str]:
    e = draft.evidence
    ref = _short_ref(e.get("creative_ref") or "this creative")
    cpl = e.get("cpl")
    brand_cpl = e.get("brand_avg_cpl")
    currency = e.get("currency")
    spend = e.get("spend") or 0

    what = (
        f"“{ref}” is bringing in leads cheaper than your average — and "
        f"there's room to spend more on it."
    )
    why = (
        f"It's at {_money(cpl, currency)} per lead vs your overall average "
        f"of {_money(brand_cpl, currency)}. You've only spent "
        f"{_money(spend, currency)} on it so far, so it hasn't run out of "
        f"audience yet."
    )
    rec = (
        f"Double the spend behind “{ref}” next week. Don't change the ad "
        f"itself yet — just give it more budget and let it keep working."
    )
    if cpl and spend:
        # Extra leads if we doubled the spend at the current CPL.
        extra = int(spend / cpl)
        expected = (
            f"Doubling the budget should bring roughly {extra} more leads "
            f"next week at the same cost per lead — assuming the audience "
            f"hasn't peaked."
        )
    else:
        expected = (
            f"Adding budget here should bring measurably more leads next "
            f"week at the same cost per lead."
        )
    reason = (
        f"Based on a comparison of this ad's cost per lead against the "
        f"average across everything in the file you uploaded."
    )
    return what, why, rec, expected, reason


def _budget_waste(draft: DiagnosticDraft) -> tuple[str, str, str, str, str]:
    e = draft.evidence
    ref = _short_ref(e.get("creative_ref") or "this creative")
    cpl = e.get("cpl")
    brand_cpl = e.get("brand_avg_cpl")
    ratio = e.get("cpl_overrun_ratio") or 0
    spend = e.get("spend") or 0
    currency = e.get("currency")
    spend_share_pct = int(round((e.get("spend_share") or 0) * 100))
    freed_leads = e.get("freed_leads_estimate") or 0

    what = (
        f"“{ref}” is eating about {spend_share_pct}% of your spend without "
        f"producing matching results."
    )
    why = (
        f"It's at {_money(cpl, currency)} per lead — about {ratio:.1f}× your "
        f"overall average of {_money(brand_cpl, currency)}. "
        f"{_money(spend, currency)} has already gone in."
    )
    rec = (
        f"Move the budget behind “{ref}” to your best-performing ad. Don't "
        f"pause yet — just stop adding new spend here for the next 7 days."
    )
    if freed_leads > 0:
        expected = (
            f"Shifting the spend should free up roughly {freed_leads} more "
            f"leads next period — same money, better outcome."
        )
    else:
        expected = (
            f"Shifting the spend should noticeably lower your overall cost "
            f"per lead within the first week."
        )
    reason = (
        f"Based on this ad's cost per lead vs the average across everything "
        f"in the file you uploaded."
    )
    return what, why, rec, expected, reason


# ---------------------------------------------------------------------
#  9.1.5 — Creative DNA (apex card)
# ---------------------------------------------------------------------


def _creative_dna(draft: DiagnosticDraft) -> tuple[str, str, str, str, str]:
    e = draft.evidence
    aud = _human_audience(e.get("audience") if isinstance(e.get("audience"), str) else None)
    concept = _human_tag(e.get("concept_family") if isinstance(e.get("concept_family"), str) else None)
    emotion = _human_tag(e.get("emotion") if isinstance(e.get("emotion"), str) else None)
    offer = _human_offer(e.get("offer_type") if isinstance(e.get("offer_type"), str) else None)
    funnel = _human_funnel(e.get("funnel_stage") if isinstance(e.get("funnel_stage"), str) else None)
    cpl = e.get("cpl")
    currency = e.get("currency")
    convs = e.get("conversions") or 0
    n_creatives = e.get("creatives_count") or 0

    # The card the user spec'd — pattern signature spelled out cleanly
    # in plain English. Six lines, founder-readable, no jargon.
    what = (
        "This combination produced the strongest business result in this upload.\n\n"
        "Winning pattern:\n"
        f"  • Audience: {aud}\n"
        f"  • Feeling: {emotion}\n"
        f"  • Angle: {concept}\n"
        f"  • Offer: {offer}\n"
        f"  • Buyer stage: {funnel}\n\n"
        f"It produced {convs} lead{'s' if convs != 1 else ''} at "
        f"{_money(cpl, currency)} each across {n_creatives} ad"
        f"{'s' if n_creatives != 1 else ''}."
    )
    why = (
        f"No other combination of these five ingredients brought leads at "
        f"this cost. The mix of who you spoke to, the feeling, the angle, "
        f"the offer, and where they were in the buying journey all clicked "
        f"together."
    )
    rec = (
        f"Make 2-3 more ads using this exact recipe — same audience "
        f"({aud}), same {emotion} feeling, same {concept} angle, same offer "
        f"({offer}), aimed at {funnel}. Vary only the copy and the image."
    )
    if draft.confidence >= 70:
        expected = (
            f"Variants in this style usually hold the cost per lead within "
            f"10–20% of the original and add 30–50% more leads over the next "
            f"2 weeks."
        )
    else:
        expected = (
            f"Variants in this style typically add 15–30% more leads at a "
            f"similar cost per lead — worth running 2-3 to confirm before "
            f"shifting budget."
        )
    reason = (
        f"Based on every audience × feeling × angle × offer × buyer-stage "
        f"combination in the file you uploaded. The winning combination "
        f"beat the next-best across all five dimensions."
    )
    return what, why, rec, expected, reason
