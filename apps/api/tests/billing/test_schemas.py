"""Phase 10.2e — Schema invariants.

Reflection guard plus billing-specific checks:
  - No schema exposes Stripe correlation handles (external_*_id)
  - delivery_status on UpgradeRequestResponse is FROZEN to 'manual'
    until Stripe ships — pin so a future loosening is an intentional PR
  - No schema accepts a client-supplied `used` count (anti-inflation)
"""

from __future__ import annotations

import inspect

from pydantic import BaseModel, ValidationError

from aicmo.modules.billing import schemas
import pytest


# Mirrors prior phases + billing-specific:
FORBIDDEN_FIELD_SUBSTRINGS = (
    "token",
    "secret",
    "credential",
    "password",
    "api_key",
    "client_secret",
    "private_key",
    # billing-specific: Stripe correlation handles never go on the API
    "external_subscription_id",
    "external_customer_id",
    "external_invoice_id",
    "stripe_customer_id",
)


def _public_schemas() -> list[type[BaseModel]]:
    return [
        obj
        for _name, obj in inspect.getmembers(schemas)
        if inspect.isclass(obj)
        and issubclass(obj, BaseModel)
        and obj is not BaseModel
        and obj.__module__ == schemas.__name__
    ]


def test_no_schema_exposes_stripe_ids_or_secrets() -> None:
    found = _public_schemas()
    assert found, "expected at least one schema in billing.schemas"
    for model in found:
        for field_name in model.model_fields:
            lower = field_name.lower()
            for forbidden in FORBIDDEN_FIELD_SUBSTRINGS:
                assert forbidden not in lower, (
                    f"{model.__name__}.{field_name} contains forbidden "
                    f"substring {forbidden!r} — Stripe correlation "
                    "handles must not leak via the API."
                )


def test_subscription_read_field_set_stable() -> None:
    expected = {
        "id",
        "organization_id",
        "plan_slug",
        "plan_display_name",
        "status",
        "period_start",
        "period_end",
        "trial_ends_at",
        "canceled_at",
        "cancel_at_period_end",
        "is_on_default_plan",
        "is_paid_plan",
        "created_at",
        "updated_at",
    }
    actual = set(schemas.SubscriptionRead.model_fields.keys())
    assert actual == expected, (
        f"SubscriptionRead drifted: added={actual - expected}, "
        f"removed={expected - actual}"
    )


def test_invoice_read_does_NOT_expose_external_id() -> None:
    """`external_invoice_id` is server-only Stripe correlation. The
    UI uses `hosted_invoice_url` for the public link."""
    fields = set(schemas.InvoiceRead.model_fields.keys())
    assert "external_invoice_id" not in fields
    assert "hosted_invoice_url" in fields


def test_usage_breakdown_does_NOT_accept_client_used_count() -> None:
    """`extra='forbid'` ensures a client can't smuggle a `used` field
    into a request. The summary endpoint is GET-only so there's no
    PATCH path, but pin the response schema's `extra='forbid'` so a
    future POST endpoint doesn't accidentally accept inflation
    payloads."""
    # The schema definition itself uses extra='forbid' — verify by
    # constructing with an unknown field and expecting failure.
    with pytest.raises(ValidationError):
        schemas.UsageBreakdownCell(  # type: ignore[call-arg]
            kind="csv_upload",
            display_name="CSV uploads",
            used=42,
            limit=None,
            percent_used=None,
            forged_by_attacker="oops",
        )


def test_upgrade_request_response_delivery_status_frozen_to_manual() -> None:
    """The Literal['manual'] type is the contract. Loosening it (e.g.
    to Literal['manual', 'automatic']) would let Stripe-wiring code
    drop in without anyone noticing the UI implications. Pin until
    Stripe lands as a deliberate phase."""
    field = schemas.UpgradeRequestResponse.model_fields["delivery_status"]
    # Pydantic stores the Literal as the field annotation.
    import typing

    args = typing.get_args(field.annotation)
    assert args == ("manual",), (
        f"delivery_status arms drifted from ('manual',) to {args} — "
        "did Stripe ship?"
    )


def test_upgrade_request_rejects_unknown_plan() -> None:
    """Pydantic Literal blocks the obvious 'enterprise_secret_plan'
    attempt before service ever runs."""
    with pytest.raises(ValidationError):
        schemas.UpgradeRequest(
            requested_plan_slug="enterprise_secret_plan",  # type: ignore[arg-type]
        )


def test_upgrade_request_rejects_extra_fields() -> None:
    """`extra='forbid'` blocks smuggled fields like `delivery_status`
    (which is server-controlled, not client-supplied)."""
    with pytest.raises(ValidationError):
        schemas.UpgradeRequest(  # type: ignore[call-arg]
            requested_plan_slug="growth",
            delivery_status="automatic",
        )


def test_plan_descriptor_field_set_stable() -> None:
    expected = {
        "slug",
        "display_name",
        "tagline",
        "description",
        "monthly_price_cents",
        "currency",
        "quotas",
        "availability",
        "is_default",
        "cta_label",
        "cta_kind",
        "feature_highlights",
    }
    actual = set(schemas.PlanDescriptor.model_fields.keys())
    assert actual == expected


def test_currency_field_must_be_3_chars() -> None:
    """ISO 4217 alpha-3. Pin so a 'USD!' or 'usd' bug fails loudly."""
    with pytest.raises(ValidationError):
        schemas.PlanDescriptor(
            slug="early_access",
            display_name="Early Access",
            tagline="x" * 30,
            description="x" * 50,
            monthly_price_cents=None,
            currency="USDD",  # 4 chars — invalid
            quotas=[],
            availability="current",
            is_default=True,
            cta_label="x",
            cta_kind="current",
            feature_highlights=["x"],
        )
