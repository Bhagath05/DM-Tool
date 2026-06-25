"""Phase 10.2b — Notification catalog (static, code-defined).

This is the SINGLE SOURCE OF TRUTH for:

  1. Which categories exist
  2. Which channels exist
  3. Default on/off for each (category, channel) cell
  4. Which cells are LOCKED (cannot be disabled — server-coerced)
  5. Delivery status per channel — surfaces "placeholder" honestly
     until each channel's dispatcher ships

The DB CHECK constraints in migration 0023 mirror the category +
channel id lists below. Editing either of them in isolation will drift
— always update both in the same PR (and add a follow-up migration if
the enum range changes).

Locked cells (CRITICAL: do not loosen without a security review):

  - billing_alert.email — a founder cannot accidentally mute "your card
    expired" → "your account was downgraded" notifications.
  - security_alert.email — a founder cannot accidentally mute "someone
    logged in from a new device" → "your password was changed".

Both are channel-locked on email specifically because email is the
universal lowest-common-denominator destination. Once SMS dispatch
ships in a later phase, we may add SMS locks too — but never remove
the email locks.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Iterable

from aicmo.modules.notifications.schemas import (
    CategoryDescriptor,
    ChannelDescriptor,
    NotificationCatalog,
    NotificationCategory,
    NotificationChannel,
)


# ---------------------------------------------------------------------
#  Channels
# ---------------------------------------------------------------------

# Every channel is 'placeholder' in Phase 10.2b. The pending_reason
# strings are the exact copy the UI surfaces — kept here so a/b copy
# changes don't require a frontend PR.
_CHANNELS: tuple[ChannelDescriptor, ...] = (
    ChannelDescriptor(
        id="email",
        display_name="Email",
        description="Delivered to your account email address.",
        delivery_status="placeholder",
        pending_reason="Email delivery launches with notifications dispatcher.",
    ),
    ChannelDescriptor(
        id="slack",
        display_name="Slack",
        description="Posted to a Slack channel you connect to your workspace.",
        delivery_status="placeholder",
        pending_reason="Connect a Slack workspace once the Slack integration ships.",
    ),
    ChannelDescriptor(
        id="sms",
        display_name="SMS",
        description="Text message to a verified phone number.",
        delivery_status="placeholder",
        pending_reason="SMS delivery launches after phone-number verification ships.",
    ),
)


# ---------------------------------------------------------------------
#  Categories — defaults + locks
# ---------------------------------------------------------------------

# Each entry: (id, display_name, description, default_channels, locked_channels)
_CATEGORIES: tuple[CategoryDescriptor, ...] = (
    CategoryDescriptor(
        id="weekly_digest",
        display_name="Weekly digest",
        description=(
            "Every Monday: what moved, what's working, and your three "
            "highest-impact actions for the week."
        ),
        default_channels=["email"],
        locked_channels=[],
    ),
    CategoryDescriptor(
        id="winner_alert",
        display_name="Winning creative alert",
        description=(
            "We spotted a creative outperforming its peers. Scale it before "
            "the auction catches up."
        ),
        default_channels=["email", "slack"],
        locked_channels=[],
    ),
    CategoryDescriptor(
        id="campaign_alert",
        display_name="Campaign health alert",
        description=(
            "A campaign's performance changed materially — spend spike, "
            "CPL drift, or a stalled delivery — surfaced before it bleeds."
        ),
        default_channels=["email", "slack"],
        locked_channels=[],
    ),
    CategoryDescriptor(
        id="billing_alert",
        display_name="Billing alert",
        description=(
            "Card expiring, payment failed, plan downgrade pending. Email "
            "delivery cannot be disabled — these stop your business if missed."
        ),
        default_channels=["email"],
        locked_channels=["email"],
    ),
    CategoryDescriptor(
        id="security_alert",
        display_name="Security alert",
        description=(
            "Sign-in from a new device, password changed, API key rotated. "
            "Email delivery cannot be disabled."
        ),
        default_channels=["email"],
        locked_channels=["email"],
    ),
    CategoryDescriptor(
        id="system_alert",
        display_name="System notice",
        description=(
            "Planned maintenance, breaking changes, and platform-wide "
            "announcements from the DM Tool team."
        ),
        default_channels=["email"],
        locked_channels=[],
    ),
)


# ---------------------------------------------------------------------
#  Public surface
# ---------------------------------------------------------------------


def get_catalog() -> NotificationCatalog:
    """Return the static catalog. Same for every user."""
    return NotificationCatalog(
        categories=list(_CATEGORIES),
        channels=list(_CHANNELS),
    )


# Frozen sets for O(1) lookups in the service layer.
_CATEGORY_IDS: frozenset[str] = frozenset(c.id for c in _CATEGORIES)
_CHANNEL_IDS: frozenset[str] = frozenset(c.id for c in _CHANNELS)

# Default-enabled set, flattened for O(1) lookup.
_DEFAULTS: frozenset[tuple[str, str]] = frozenset(
    (c.id, ch)
    for c in _CATEGORIES
    for ch in c.default_channels
)

# Locked set, flattened for O(1) lookup.
_LOCKED: frozenset[tuple[str, str]] = frozenset(
    (c.id, ch)
    for c in _CATEGORIES
    for ch in c.locked_channels
)


def all_category_ids() -> frozenset[str]:
    return _CATEGORY_IDS


def all_channel_ids() -> frozenset[str]:
    return _CHANNEL_IDS


def all_cells() -> Iterable[tuple[NotificationCategory, NotificationChannel]]:
    """Yield every (category, channel) tuple in canonical order — the
    same order the matrix endpoint returns. Stable so frontend snapshots
    don't churn."""
    for c in _CATEGORIES:
        for ch in _CHANNELS:
            yield (c.id, ch.id)


def default_for(category: str, channel: str) -> bool:
    """Code-defined default for a cell. Source of truth when no DB row exists."""
    return (category, channel) in _DEFAULTS


def is_locked(category: str, channel: str) -> bool:
    """True if the user cannot disable this cell. Server coerces on upsert."""
    return (category, channel) in _LOCKED


@dataclass(frozen=True)
class CellSpec:
    """Resolved cell, ready to materialise into a PreferenceCell."""

    category: NotificationCategory
    channel: NotificationChannel
    default_enabled: bool
    locked: bool


def cell_spec(category: NotificationCategory, channel: NotificationChannel) -> CellSpec:
    return CellSpec(
        category=category,
        channel=channel,
        default_enabled=default_for(category, channel),
        locked=is_locked(category, channel),
    )
