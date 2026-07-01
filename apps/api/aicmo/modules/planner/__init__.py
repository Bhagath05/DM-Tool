"""Phase 3.3 — Autonomous Task Planner.

Turns the marketing strategy (3.2) + business profile (3.1) into a concrete
daily plan: a short, prioritized list of today's tasks ("Post a reel about X",
"Reply to hot leads", "Draft this week's newsletter"). Grounded in the
strategy; every task explains WHY.

PLANS ONLY — nothing executes. Each task carries a `suggested_action` naming
the surface a human would use, but the planner never publishes, spends, or
sends. Ephemeral (generated on demand, cached client-side) — no persistence
until the Approval Queue (3.7) needs it.
"""
