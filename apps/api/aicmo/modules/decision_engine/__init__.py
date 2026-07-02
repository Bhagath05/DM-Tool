"""Phase 3.5 — AI Decision Engine (the reasoning layer).

Gathers CHEAP, factual signals from the existing modules (analytics KPIs,
performance overview, publishing status, strategy, business profile) — never
re-running their expensive LLM analyses — and reasons over that real data to
produce structured DECISIONS (not actions).

Every decision cites the real evidence it stands on; when the evidence is thin
the engine says so explicitly rather than inventing data. Nothing executes —
execution stays human-approved.
"""
