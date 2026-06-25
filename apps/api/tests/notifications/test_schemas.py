"""Phase 10.2b — Pydantic schema invariants.

Same reflection guard the integrations module uses: no schema in
notifications should ever leak a destination (email address, slack
webhook, phone number). Preferences are pure on/off toggles — the
destination lookup happens in the dispatcher (post-Phase-10.2b).
"""

from __future__ import annotations

import inspect

from pydantic import BaseModel

from aicmo.modules.notifications import schemas


# Mirrors integrations test_schemas.py — keep the lists in lock-step.
FORBIDDEN_FIELD_SUBSTRINGS = (
    "token",
    "secret",
    "credential",
    "password",
    "api_key",
    "client_secret",
    # notifications-specific: destinations belong to the dispatcher table,
    # never to the preference matrix.
    "phone",
    "webhook",
    "address",
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


def test_no_schema_exposes_destination_or_secret_fields() -> None:
    found = _public_schemas()
    assert found, "expected at least one schema in notifications.schemas"
    for model in found:
        for field_name in model.model_fields:
            lower = field_name.lower()
            for forbidden in FORBIDDEN_FIELD_SUBSTRINGS:
                assert forbidden not in lower, (
                    f"{model.__name__}.{field_name} contains forbidden "
                    f"substring {forbidden!r} — destinations + secrets "
                    "must not appear in the preference matrix."
                )


def test_preference_cell_field_set_is_stable() -> None:
    """If you add or remove a field from PreferenceCell, decide whether
    the new field is API-safe BEFORE updating this list."""
    expected = {
        "category",
        "channel",
        "enabled",
        "source",
        "locked",
        "updated_at",
    }
    actual = set(schemas.PreferenceCell.model_fields.keys())
    assert actual == expected, (
        f"PreferenceCell drifted: added={actual - expected}, "
        f"removed={expected - actual}"
    )


def test_preference_matrix_only_has_cells() -> None:
    assert set(schemas.PreferenceMatrix.model_fields.keys()) == {"cells"}


def test_notification_catalog_only_has_categories_and_channels() -> None:
    assert set(schemas.NotificationCatalog.model_fields.keys()) == {
        "categories",
        "channels",
    }


def test_channel_descriptor_field_set() -> None:
    expected = {
        "id",
        "display_name",
        "description",
        "delivery_status",
        "pending_reason",
    }
    assert set(schemas.ChannelDescriptor.model_fields.keys()) == expected


def test_category_descriptor_field_set() -> None:
    expected = {
        "id",
        "display_name",
        "description",
        "default_channels",
        "locked_channels",
    }
    assert set(schemas.CategoryDescriptor.model_fields.keys()) == expected


def test_update_payload_only_accepts_known_fields() -> None:
    """`extra='forbid'` enforced — try to send an unknown field and the
    Pydantic validator should reject it. This is the only line of
    defence against a forged `source='admin'` self-promotion attempt."""
    from pydantic import ValidationError
    import pytest

    with pytest.raises(ValidationError):
        schemas.PreferenceUpdate(
            category="weekly_digest",
            channel="email",
            enabled=True,
            source="admin",  # type: ignore[call-arg]
        )
