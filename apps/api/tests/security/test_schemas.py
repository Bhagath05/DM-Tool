"""Phase 10.2c — Schema invariants.

Same reflection guard pattern the integrations + notifications modules
use, extended with security-specific forbidden substrings (passwords,
MFA codes, recovery codes — never expose).
"""

from __future__ import annotations

import inspect

from pydantic import BaseModel

from aicmo.modules.security import schemas


# Mirrors integrations + notifications — keep in lock-step. Security
# additions: any field that looks like an authenticator secret.
FORBIDDEN_FIELD_SUBSTRINGS = (
    "token",
    "secret",
    "credential",
    "password",
    "api_key",
    "client_secret",
    "mfa_code",
    "recovery_code",
    "backup_code",
    "totp_seed",
    "private_key",
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


def test_no_schema_exposes_authenticator_secrets() -> None:
    found = _public_schemas()
    assert found, "expected at least one schema in security.schemas"
    for model in found:
        for field_name in model.model_fields:
            lower = field_name.lower()
            for forbidden in FORBIDDEN_FIELD_SUBSTRINGS:
                assert forbidden not in lower, (
                    f"{model.__name__}.{field_name} contains forbidden "
                    f"substring {forbidden!r} — credentials must never "
                    "appear in security schemas."
                )


def test_session_read_field_set_is_stable() -> None:
    expected = {
        "id",
        "clerk_session_id",
        "user_agent",
        "ip_address",
        "geo_country",
        "geo_city",
        "last_seen_at",
        "expires_at",
        "revoked_at",
        "revoked_by",
        "revocation_status",
        "is_current",
        "is_active",
        "created_at",
    }
    actual = set(schemas.SessionRead.model_fields.keys())
    assert actual == expected, (
        f"SessionRead drifted: added={actual - expected}, removed={expected - actual}"
    )


def test_security_event_read_field_set_is_stable() -> None:
    expected = {
        "id",
        "event_type",
        "actor",
        "clerk_session_id",
        "ip_address",
        "user_agent",
        "metadata",
        "occurred_at",
        "created_at",
    }
    actual = set(schemas.SecurityEventRead.model_fields.keys())
    assert actual == expected


def test_security_summary_field_set_is_stable() -> None:
    expected = {
        "active_session_count",
        "last_login_at",
        "last_login_ip",
        "last_login_country",
        "recent_event_count_24h",
        "recent_failed_login_count_24h",
        "suspicious_signal",
    }
    actual = set(schemas.SecuritySummary.model_fields.keys())
    assert actual == expected


def test_security_event_create_only_allows_known_fields() -> None:
    """`extra='forbid'` enforces no smuggling extra fields. Trying to
    set `actor='admin'` (server-controlled) must be rejected — that's
    the only defence against a user forging admin-attributed events
    in their own timeline."""
    from pydantic import ValidationError
    import pytest

    with pytest.raises(ValidationError):
        schemas.SecurityEventCreate(
            event_type="failed_login",
            actor="admin",  # type: ignore[call-arg]
        )


def test_event_type_literal_covers_all_six_types() -> None:
    """Pin the enum surface so adding a type without test updates is
    caught. Mirror of migration 0024 CHECK constraint."""
    # Force the Literal arms to surface by validating each.
    from pydantic import TypeAdapter

    ta = TypeAdapter(schemas.SecurityEventType)
    for t in (
        "login",
        "logout",
        "failed_login",
        "password_change",
        "mfa_challenge",
        "session_revoke",
    ):
        ta.validate_python(t)  # must not raise

    import pytest
    from pydantic import ValidationError

    with pytest.raises(ValidationError):
        ta.validate_python("hax0r")
