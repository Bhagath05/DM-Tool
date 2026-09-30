"""Evidence-backed belief / learning memory (Phase 3A).

A thin, tenant-scoped graph over EXISTING evidence (brain_evidence, advisor
recommendations/outcomes, learning insights) that records what DM Tool currently
believes — with server-derived confidence, explicit status, structured scope, and
auditable supersession/contradiction. Writes go only through the service (never
the LLM); the resolver returns a bounded snapshot for the future agent.
"""
