"""Phase 10.2a — Pydantic schema invariants.

Hard rule: **no schema in `integrations/schemas.py` should ever
expose a token field.** This test enforces it via reflection so a
future "let me just add access_token here for debugging" PR fails
in CI instead of leaking secrets.
"""

from __future__ import annotations

import inspect

from pydantic import BaseModel

from aicmo.modules.integrations import schemas


FORBIDDEN_FIELD_SUBSTRINGS = (
    "token",
    "secret",
    "credential",
    "password",
    "api_key",
    "client_secret",
)


def _public_schemas() -> list[type[BaseModel]]:
    """All BaseModel subclasses declared directly in the schemas module."""
    return [
        obj
        for _name, obj in inspect.getmembers(schemas)
        if inspect.isclass(obj)
        and issubclass(obj, BaseModel)
        and obj is not BaseModel
        and obj.__module__ == schemas.__name__
    ]


def test_no_schema_exposes_credential_fields() -> None:
    found = _public_schemas()
    assert found, "expected at least one schema in integrations.schemas"
    for model in found:
        for field_name in model.model_fields:
            lower = field_name.lower()
            for forbidden in FORBIDDEN_FIELD_SUBSTRINGS:
                assert forbidden not in lower, (
                    f"{model.__name__}.{field_name} contains forbidden "
                    f"substring {forbidden!r} — tokens/secrets must "
                    "NEVER appear in an API schema."
                )


def test_connection_read_field_set_is_stable() -> None:
    """If you add or remove a field from ConnectionRead, decide
    whether the new field is API-safe BEFORE updating this list."""
    expected = {
        "id",
        "organization_id",
        "brand_id",
        "provider_slug",
        "state",
        "external_account_id",
        "external_account_name",
        "scopes_granted",
        "error_message",
        "connected_at",
        "last_sync_at",
        "last_error_at",
        "created_at",
        "updated_at",
    }
    actual = set(schemas.ConnectionRead.model_fields.keys())
    assert actual == expected, (
        f"ConnectionRead field set drifted: "
        f"added={actual - expected}, removed={expected - actual}"
    )


def test_provider_info_has_no_secrets() -> None:
    """Even though `scopes` looks credential-adjacent, scope strings
    are public OAuth identifiers — keep them. But pin the field set."""
    expected = {
        "slug",
        "display_name",
        "category",
        "icon_id",
        "description",
        "scopes",
        "available",
    }
    actual = set(schemas.ProviderInfo.model_fields.keys())
    assert actual == expected
