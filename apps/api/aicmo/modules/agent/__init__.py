"""Read-only conversational agent runtime (Phase 2).

Orchestrates existing systems — MarketingBrainContext (read context), the Phase-1
Tool Registry (capabilities), LLMRouter + task policies (model access),
TenantContext + RLS (isolation), and ai_audit_events (provenance) — into a
bounded, read-only conversational turn. It owns conversation state only; all
business logic stays in the existing services.
"""
