"""Observability — Sentry integration.

One job: production exception capture with tenant context attached.
Initialised exactly once at app startup (see aicmo/main.py).
"""

from aicmo.observability.sentry import (
    bind_tenant_context,
    clear_tenant_context,
    init_sentry,
)

__all__ = ["init_sentry", "bind_tenant_context", "clear_tenant_context"]
