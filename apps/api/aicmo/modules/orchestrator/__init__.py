"""Module 8 — Agent Orchestrator.

The conductor of the autonomous marketing employee. It does NOT generate new
intelligence and it NEVER executes anything: it assesses where the brand sits in
the autonomous lifecycle (understand → strategize → plan → decide → execute →
learn → review) by reading each module's state, then produces a coordinated,
human-approval-gated plan of the single next best action plus the full stage map.

Deterministic and ephemeral — no LLM, no table, no migration. Every actionable
step is a recommendation the human triggers; the `execute` stage is always
gated behind explicit approval.
"""
