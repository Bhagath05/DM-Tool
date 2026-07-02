"""Module 9 — Autonomy Policy Layer.

The central policy that governs what the AI may execute automatically vs. what
requires human approval. It does NOT add another approve/reject inbox — the
per-module approval mechanisms already exist. Instead it provides one
tenant-level configuration + a reusable evaluation function
(`evaluate_policy`) that the Agent Orchestrator (and, later, execution paths)
consult before acting.

Safe by default: an unconfigured workspace resolves to `always_approve` for
every action, so nothing runs automatically until an administrator opts in.
This is the foundation for Module 10 (Future Autonomy Flags), where customers
progressively raise autonomy over time.
"""
