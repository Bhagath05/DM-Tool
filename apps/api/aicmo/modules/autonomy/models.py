"""Module 9 — Autonomy Policy ORM model (one row per brand)."""

from __future__ import annotations

import uuid

from sqlalchemy import Boolean, String
from sqlalchemy.dialects.postgresql import JSONB, UUID
from sqlalchemy.orm import Mapped, mapped_column

from aicmo.db.base import Base, TenantMixin, TimestampMixin


class AutonomyPolicy(Base, TimestampMixin, TenantMixin):
    """The autonomy configuration for one brand. A single row per brand
    (upserted); absence resolves to the safe default (everything requires
    approval)."""

    __tablename__ = "autonomy_policies"

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, default=uuid.uuid4
    )
    # Last editor (for "who changed autonomy"); mirrors the String user_id used
    # across business tables.
    user_id: Mapped[str] = mapped_column(String(255), index=True)

    # Fallback policy mode for any action type not explicitly configured.
    # Safe default: require approval for everything.
    default_mode: Mapped[str] = mapped_column(
        String(32), default="always_approve", server_default="always_approve"
    )

    # Per-action-type overrides:
    #   {action_type: {"mode": str, "threshold_amount": float|None,
    #                  "threshold_currency": str|None}}
    policies: Mapped[dict] = mapped_column(JSONB, default=dict, server_default="{}")

    # Business-hours window for the `auto_business_hours` mode:
    #   {"enabled": bool, "start_hour": int, "end_hour": int,
    #    "timezone": str, "days": [0-6]}
    business_hours: Mapped[dict] = mapped_column(
        JSONB, default=dict, server_default="{}"
    )

    # Workspace-trust flag for the `auto_if_trusted` mode. Only an admin can set
    # it; false by default.
    trusted: Mapped[bool] = mapped_column(
        Boolean, default=False, server_default="false"
    )
