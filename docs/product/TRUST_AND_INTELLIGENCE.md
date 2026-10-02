# Trust & Intelligence — Product Principles

**Status: non-negotiable product constitution for the Trust & Intelligence Layer.**
This document states the rules. The *how* (data model, pipeline, enforcement
points, phases) lives in [TRUST_INTELLIGENCE_ARCHITECTURE.md](TRUST_INTELLIGENCE_ARCHITECTURE.md).
Where this conflicts with a convenience, this wins.

> DM Tool optimizes for **trustworthy decisions, not impressive answers.**
> The system must never sound more certain than the evidence supports, and the
> LLM is never the final authority on whether its own answer is trustworthy.

These principles extend — they do not replace — the Constitution in
[/CLAUDE.md](../../CLAUDE.md) (the 10-second rule, the AI Recommendation
Contract, Simple Mode, business-impact framing) and the safety boundaries of the
approval architecture (Phases 4A–4C).

---

## The 17 non-negotiables

Each rule names where it is (or will be) enforced. "Today" = already true in the
codebase; "Trust Layer" = to be enforced by the new layer.

1. **Never fabricate evidence.** Every evidence reference points at a real stored
   row by id. *Today:* `belief_evidence` references existing rows; `BrainEvidence`
   carries `source_url`/`snippet`/`discovered_at`. *Trust Layer:* a claim with no
   resolvable evidence is rejected or downgraded, never shown as fact.

2. **Never fabricate metrics.** Metrics shown to a user must come from a
   deterministic calculation over real data, never from LLM text. *Trust Layer:*
   the LLM explains verified calculations; it is not the calculator (§10 arch).

3. **Never fabricate revenue, ROAS, CAC, conversion, or performance.** These are
   high-consequence numbers; absent real source data they are `INSUFFICIENT_EVIDENCE`,
   not estimated.

4. **Never hide contradictory evidence.** Opposing evidence is preserved, not
   suppressed. *Today:* beliefs keep `contradicted`/`superseded` history; brain
   evidence has `contradicted` status. *Trust Layer:* a claim with live
   contradictions surfaces as `MIXED_EVIDENCE`.

5. **Never present correlation as causation.** Observational association may not
   become causal language. A causal claim requires a controlled/randomized basis
   (§9 arch). *Trust Layer:* deterministic causal-language gate downgrades
   unsupported causal phrasing to observation.

6. **Never claim an action happened unless execution was verified.** *Today:* the
   approval state machine only marks `EXECUTED` after a validated result; the UI
   shows proposals as "approval required," never as done. The Trust Layer must
   not weaken this.

7. **Never claim provider data exists without provider evidence.** First-party
   provider data must trace to a provider source; otherwise the source is marked
   `UNVERIFIED` (§16 arch).

8. **Never let an LLM-generated confidence number become authoritative.**
   *Today:* belief confidence is deterministically derived (`derive_confidence`),
   and advisor recommendations carry a server `confidence_cap`. *Gap:* the
   conversational agent currently surfaces LLM-set `confidence`/`evidence_status`.
   *Trust Layer:* confidence is derived/validated server-side; any LLM number is
   at most clamped down, never trusted up.

9. **Never convert uncertainty into certainty.** Confidence has an explicit
   **ceiling** when evidence is weak; freshness decays authority over time.
   *Today:* belief ceiling 95 + freshness decay. *Trust Layer:* a global
   evidence-quality → confidence-ceiling mapping.

10. **Distinguish FACT, OBSERVATION, INTERPRETATION, HYPOTHESIS, RECOMMENDATION.**
    These are different trust levels and must render differently. *Today:*
    `BrainEvidence.kind ∈ {fact, observation, hypothesis, recommendation}`;
    beliefs model hypotheses/conclusions. *Trust Layer:* a unified claim type on
    every user-visible important conclusion.

11. **Recommendations must be traceable to evidence.** Every significant
    recommendation carries WHY, EVIDENCE, CONFIDENCE, LIMITATIONS, EXPECTED
    EFFECT, HOW-TO-TEST. *Today:* the 6-field advisor recommendation contract +
    `data_used`. *Trust Layer:* enforce traceability (evidence_ids) before display.

12. **Consequential actions require human authorization.** Unchanged from Phases
    4A–4C. The Trust Layer never becomes a path that executes anything.

13. **Critical calculations use deterministic logic.** CTR, conversion, ROAS,
    CAC, revenue/percentage change, budget totals, experiment statistics — all
    computed in code. *Today:* `analytics`, `performance/intelligence`,
    `advisor/outcomes` compute deterministically. *Trust Layer:* a named
    calculation registry the LLM may only *read from*.

14. **Insufficient evidence stays explicitly insufficient.** `INSUFFICIENT_EVIDENCE`
    is a first-class terminal state; gaps are never filled by assumption. *Today:*
    advisor `InsufficientData`, agent `evidence_status`, belief "unvalidated".

15. **Outcomes must be evaluated.** Recommendations/actions get measured. *Today:*
    `advisor/outcomes.evaluate_due_outcomes` (deterministic) + belief formation
    from evaluated outcomes.

16. **Failed recommendations become learning evidence.** A wrong recommendation
    is retained and feeds the belief lifecycle (contradiction/supersession), never
    silently deleted. *Today:* belief reconcile + formation; outcome→belief.

17. **Users remain the final decision makers.** The system advises and prepares;
    the human decides and authorizes. Advisory-only by default.

---

## Two hard boundaries that the Trust Layer must never cross

- **No chain-of-thought storage or exposure.** The system stores *structured
  provenance* (claim → evidence ids → sources → timestamps → transformation name
  → conclusion), never private reasoning traces. *Today:* `ai_audit` stores
  structured metadata and runs a secret scrubber; reasoning is a bounded
  `ReasoningSummary`, not a transcript.

- **No security bypass.** Tenant isolation, RLS, auth, the approval state machine,
  action fingerprints, idempotency, audit, secret handling, and prompt-injection
  fencing are unchanged. The Trust Layer is a *validation gate*, not an authority
  that can act, cross tenants, or widen access.

---

## What "trustworthy" means operationally

A user-visible important conclusion is trustworthy when **all** hold:

- it declares its **claim type** (fact/observation/interpretation/hypothesis/recommendation);
- its **confidence is server-derived** from evidence quality + quantity +
  consistency + freshness, and respects the ceiling for weak evidence;
- it is **traceable** to real evidence ids (provenance resolvable);
- its **contradictions** are surfaced, not hidden;
- any **causal** language is backed by an appropriate design, else downgraded;
- any **metric** in it was deterministically calculated;
- when evidence is missing/weak/stale/conflicting, it says so (`INSUFFICIENT_EVIDENCE`
  / `MIXED_EVIDENCE` / stale downgrade) rather than guessing.

If it cannot meet these, the Trust Layer downgrades or rejects it before the user
sees it.
