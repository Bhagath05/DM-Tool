"""Phase 10.2e — Billing backend (no Stripe yet).

What this module owns:
  - The 3-plan catalog (Early Access / Growth / Scale)
  - subscription / invoice / usage_event / billing_upgrade_request tables
  - Lazy provisioning of Early Access on first read
  - Internal `record_usage()` Python API for future service wiring
  - Honest-placeholder upgrade-request endpoint (no Stripe checkout URL)

What this module DOESN'T own (and why):
  - Real billing / payment processing — deferred to a future phase
    when Stripe lands. The schema already accepts `external_*_id`
    fields so Stripe rows drop in without migration.
  - Usage emission from existing services (CSV ingest, lead capture,
    AI engine, etc.) — wiring those is a non-trivial cross-cutting
    change that risks the "preserve all existing tests" non-negotiable.
    Future phase wires `billing_service.record_usage(...)` into each
    emitting site.
"""

from aicmo.modules.billing.router import router

__all__ = ["router"]
