"""Module 7 — Autonomous Insights (the unified AI Insights Feed).

A PURE aggregation, ranking, and presentation layer. It generates NO new
intelligence: it reads the outputs already produced by other modules
(Learning Engine, Advisor recommendations + Opportunities, Performance
diagnostics, Marketing Strategy, Business Understanding), normalises them into
one shape, deduplicates overlap, ranks by severity/urgency/confidence/impact,
groups related items, explains why each surfaced, and links back to the
originating module.

Ephemeral by design — no table, no migration, no LLM call. The generative
surfaces (Task Planner, Decision Engine, Competitor Watch) are surfaced as
live-links, never re-run here (that would duplicate their analysis).
"""
