"""Audit read schemas (Phase 6.6 Slice 4).

The write path (`audit.service.record`) is unchanged. These are the
read-side projections for the org-wide Audit Log page.
"""

from __future__ import annotations

import uuid
from datetime import datetime

from pydantic import BaseModel


class AuditEventRead(BaseModel):
    """One audit row, with the actor's identity joined in."""

    id: uuid.UUID
    action: str
    actor_user_id: uuid.UUID
    actor_email: str | None = None
    actor_name: str | None = None
    target_type: str | None = None
    target_id: uuid.UUID | None = None
    brand_id: uuid.UUID | None = None
    before: dict | None = None
    after: dict | None = None
    occurred_at: datetime


class AuditEventList(BaseModel):
    items: list[AuditEventRead]
    # Distinct actions present in the org's log — lets the UI build its
    # action filter without a second round-trip or a hardcoded list.
    actions: list[str] = []
