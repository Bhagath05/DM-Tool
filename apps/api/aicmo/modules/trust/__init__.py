"""Trust & Intelligence Layer — T0: pure, deterministic contracts + validators.

This module is the validation core designed in
``docs/product/TRUST_INTELLIGENCE_ARCHITECTURE.md`` (the Phase-1 Implementation
Contract). T0 is **pure**: no database, no ORM session, no network, no LLM, no
tenant retrieval, no tool/approval execution, and no agent-runtime or UI
integration. Every function operates on typed inputs and returns typed outputs,
and every rule here is DM Tool server policy — never derived from how a model
"sounds".

Nothing in T0 is wired into the agent; wiring (shadow mode) is T2 and is a
separate, reviewed phase.
"""
