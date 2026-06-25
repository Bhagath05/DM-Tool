"""Phase 10.2b — Pydantic schemas for notification preferences.

Hard rule (mirrored from integrations): no schema in this module exposes
secrets, tokens, or destinations. Email addresses, slack webhooks, and
phone numbers live elsewhere — preferences are pure on/off toggles.

The category + channel Literal types are the single source of truth
the frontend consumes via OpenAPI codegen.
"""

from __future__ import annotations

from datetime import datetime
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field


# ---------------------------------------------------------------------
#  Enums — kept in lock-step with:
#    apps/api/aicmo/modules/notifications/catalog.py
#    apps/api/alembic/versions/0023_notifications.py CHECK constraints
# ---------------------------------------------------------------------

NotificationCategory = Literal[
    "weekly_digest",
    "winner_alert",
    "campaign_alert",
    "billing_alert",
    "security_alert",
    "system_alert",
]

NotificationChannel = Literal["email", "slack", "sms"]

DeliveryStatus = Literal["placeholder", "available"]
# Phase 10.2b: every channel is 'placeholder' (preferences stored, nothing
# fires). Phase 12+ flips channels to 'available' as their dispatchers ship.

PreferenceSource = Literal["user", "admin", "system"]


# ---------------------------------------------------------------------
#  Catalog descriptors
# ---------------------------------------------------------------------


class ChannelDescriptor(BaseModel):
    """One channel — email / slack / sms — with its delivery status.

    `delivery_status` is the honesty knob: the UI should render an
    explicit "coming soon" affordance when it's 'placeholder' rather
    than letting users believe the toggle does something.
    """

    model_config = ConfigDict(extra="forbid")

    id: NotificationChannel
    display_name: str
    description: str
    delivery_status: DeliveryStatus
    pending_reason: str | None = Field(
        default=None,
        description="When delivery_status='placeholder', why. Surface to the user.",
    )


class CategoryDescriptor(BaseModel):
    """One notification category — what kind of message it is."""

    model_config = ConfigDict(extra="forbid")

    id: NotificationCategory
    display_name: str
    description: str
    default_channels: list[NotificationChannel] = Field(
        description="Channels enabled by default for this category.",
    )
    locked_channels: list[NotificationChannel] = Field(
        default_factory=list,
        description=(
            "Channels that cannot be disabled for this category. "
            "Server coerces these to enabled=True on upsert."
        ),
    )


class NotificationCatalog(BaseModel):
    """Static catalog — categories + channels — served from /catalog.

    No tenant context. Same response for every user. Frontend caches
    aggressively (it's effectively a static asset).
    """

    model_config = ConfigDict(extra="forbid")

    categories: list[CategoryDescriptor]
    channels: list[ChannelDescriptor]


# ---------------------------------------------------------------------
#  Preference matrix
# ---------------------------------------------------------------------


class PreferenceCell(BaseModel):
    """One cell of the matrix: (category, channel) → enabled.

    Carries `source` + `locked` so the UI can render disabled toggles
    and the "set by admin" affordance the right way.
    """

    model_config = ConfigDict(extra="forbid")

    category: NotificationCategory
    channel: NotificationChannel
    enabled: bool
    source: PreferenceSource
    locked: bool = Field(
        description="If true, frontend renders the toggle disabled.",
    )
    updated_at: datetime | None = Field(
        default=None,
        description="None when the cell is a code-defined default with no DB row.",
    )


class PreferenceMatrix(BaseModel):
    """The full 18-cell matrix for one (user, org).

    Always returns every (category × channel) combination — defaults
    are materialised server-side so the UI never has to guess.
    """

    model_config = ConfigDict(extra="forbid")

    cells: list[PreferenceCell]


class PreferenceUpdate(BaseModel):
    """One cell in a PUT payload. Only `enabled` is settable.

    `source` and `locked` are server-controlled; clients can't promote
    themselves to source='admin' or unlock a locked cell.
    """

    model_config = ConfigDict(extra="forbid")

    category: NotificationCategory
    channel: NotificationChannel
    enabled: bool


class UpdatePreferencesPayload(BaseModel):
    """PUT body — bulk update.

    A partial update is fine; any cell not present in `updates` is left
    untouched. To reset a cell to the default, omit it (rather than
    sending the default value), and the server-side row will be deleted
    on the next "reset" action — Phase 10.2b doesn't ship a DELETE path
    yet; an explicit POST /preferences/reset can land later.
    """

    model_config = ConfigDict(extra="forbid")

    updates: list[PreferenceUpdate] = Field(min_length=1, max_length=64)
