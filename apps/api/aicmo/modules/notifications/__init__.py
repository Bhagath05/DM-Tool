"""Phase 10.2b — Notification preferences (per-user, per-org).

This module owns the preference matrix: what categories of message a
founder wants delivered on which channels (email / slack / sms).

It does NOT own delivery. Phase 10.2b ships preferences only — the
dispatcher comes later. Channel descriptors carry an explicit
`delivery_status: "placeholder"` flag so the UI can render an honest
"Email delivery coming soon" badge instead of pretending it works.

Public surface:
  - GET  /api/v1/notifications/catalog       — categories + channels
  - GET  /api/v1/notifications/preferences   — the user's 18-cell matrix
  - PUT  /api/v1/notifications/preferences   — bulk update

Defaults live in `catalog.py`. Storage is sparse — only divergences
from defaults are persisted.
"""

from aicmo.modules.notifications.router import router

__all__ = ["router"]
