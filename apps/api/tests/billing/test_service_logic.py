"""Phase 10.2e — Service logic that doesn't need a real DB.

Pin the honest-placeholder contract, the constants, and the projection
logic for SubscriptionRead. Full DB-backed paths (ensure_subscription,
record_usage, get_usage_summary) get a real-DB smoke pass in 10.2e-7.
"""

from __future__ import annotations

import uuid
from datetime import datetime, timezone
from unittest.mock import MagicMock

import pytest

from aicmo.modules.billing import plan_catalog, service


# ---------------------------------------------------------------------
#  UPGRADE_REQUEST_MESSAGE — copy pinned
# ---------------------------------------------------------------------


def test_upgrade_message_says_no_payment_taken() -> None:
    """The whole point of the honest-placeholder design — the response
    must explicitly tell the founder no money moved. If you weaken
    this copy, you risk creating the impression of a phantom charge."""
    msg = service.UPGRADE_REQUEST_MESSAGE.lower()
    assert "no payment" in msg or "no charge" in msg, (
        f"UPGRADE_REQUEST_MESSAGE lost its 'no payment taken' "
        f"assurance: {service.UPGRADE_REQUEST_MESSAGE!r}"
    )


def test_upgrade_message_promises_human_followup() -> None:
    """Founder needs to know that someone is going to reach out — not
    'we got your form, please wait indefinitely'."""
    msg = service.UPGRADE_REQUEST_MESSAGE.lower()
    assert (
        "reach out" in msg or "contact" in msg or "follow up" in msg
    ), (
        f"UPGRADE_REQUEST_MESSAGE lost its 'we'll contact you' "
        f"promise: {service.UPGRADE_REQUEST_MESSAGE!r}"
    )


# ---------------------------------------------------------------------
#  _to_subscription_read — projection logic
# ---------------------------------------------------------------------


class TestSubscriptionReadProjection:
    @staticmethod
    def _row(slug: str = "early_access"):
        row = MagicMock()
        row.id = uuid.uuid4()
        row.organization_id = uuid.uuid4()
        row.plan_slug = slug
        row.status = "active"
        row.period_start = None
        row.period_end = None
        row.trial_ends_at = None
        row.canceled_at = None
        row.cancel_at_period_end = False
        row.created_at = datetime(2026, 6, 5, tzinfo=timezone.utc)
        row.updated_at = datetime(2026, 6, 5, tzinfo=timezone.utc)
        return row

    def test_early_access_marked_as_default_and_not_paid(self) -> None:
        read = service._to_subscription_read(self._row("early_access"))
        assert read.is_on_default_plan is True
        assert read.is_paid_plan is False
        assert read.plan_display_name == "Early Access"

    def test_growth_marked_as_paid_and_not_default(self) -> None:
        read = service._to_subscription_read(self._row("growth"))
        assert read.is_on_default_plan is False
        assert read.is_paid_plan is True
        assert read.plan_display_name == "Growth"

    def test_scale_marked_as_paid(self) -> None:
        read = service._to_subscription_read(self._row("scale"))
        assert read.is_paid_plan is True

    def test_unknown_plan_in_db_row_raises_loudly(self) -> None:
        """Design choice: strict-failure over silent-fallback.

        If a DB row carries a plan slug not in the catalog (a future
        migration added a slug but old API code is still running),
        the Pydantic Literal refuses to project it. The endpoint
        will 500 rather than render wrong data — explicit failure is
        safer than a phantom plan name slipping through.

        This is intentional: catch the version mismatch in monitoring
        rather than letting a customer see 'unknown_plan' on their
        billing page.
        """
        from pydantic import ValidationError

        row = self._row("future_plan_we_havent_added")  # type: ignore[arg-type]
        with pytest.raises(ValidationError):
            service._to_subscription_read(row)


# ---------------------------------------------------------------------
#  record_usage — input validation
# ---------------------------------------------------------------------


@pytest.mark.asyncio
async def test_record_usage_rejects_zero_quantity() -> None:
    """The DB CHECK enforces quantity > 0. We also guard at the
    service layer so callers see a clean ValueError before hitting
    a postgres-specific IntegrityError."""
    session = MagicMock()
    with pytest.raises(ValueError, match="quantity must be > 0"):
        await service.record_usage(
            session,
            organization_id=uuid.uuid4(),
            kind="csv_upload",
            quantity=0,
        )


@pytest.mark.asyncio
async def test_record_usage_rejects_negative_quantity() -> None:
    session = MagicMock()
    with pytest.raises(ValueError, match="quantity must be > 0"):
        await service.record_usage(
            session,
            organization_id=uuid.uuid4(),
            kind="ai_recommendation",
            quantity=-5,
        )


# ---------------------------------------------------------------------
#  Catalog integration — service-layer lookups
# ---------------------------------------------------------------------


def test_default_plan_slug_matches_catalog() -> None:
    """If the catalog's default ever drifts from 'early_access', the
    service's ensure_subscription would auto-provision the wrong plan
    — pin tight."""
    assert plan_catalog.default_plan_slug() == "early_access"


def test_growth_and_scale_are_upgradeable_targets() -> None:
    """Service.request_upgrade rejects the default plan as an
    upgrade target. Growth and Scale must be valid upgrade targets."""
    for slug in ("growth", "scale"):
        d = plan_catalog.descriptor_for(slug)
        assert d is not None and d.is_default is False, (
            f"{slug} is marked default — would be rejected as upgrade target"
        )
