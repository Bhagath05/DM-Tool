"""Phase 10.2d — Schema invariants.

Reflection guard mirrors integrations + notifications + security:
no schema in this module exposes secrets, tokens, hashes, or passwords.

Special-case allowance: `InviteCreateResponse.accept_url` carries the
raw token — that's intentional and the whole point of the create flow
(it's the one-time return value). The forbidden-substring guard
explicitly tolerates `accept_url` (which doesn't match any forbidden
substring anyway, since 'url' isn't in the list).
"""

from __future__ import annotations

import inspect

from pydantic import BaseModel

from aicmo.modules.team import schemas


# Same lock-step list as prior phases, extended with team-specific:
# no schema should ever expose `token_hash` (we hash invites for a reason).
FORBIDDEN_FIELD_SUBSTRINGS = (
    "token_hash",  # never expose the hash — defeats the purpose
    "secret",
    "credential",
    "password",
    "api_key",
    "client_secret",
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


def test_no_schema_exposes_token_hash_or_secrets() -> None:
    found = _public_schemas()
    assert found, "expected at least one schema in team.schemas"
    for model in found:
        for field_name in model.model_fields:
            lower = field_name.lower()
            for forbidden in FORBIDDEN_FIELD_SUBSTRINGS:
                assert forbidden not in lower, (
                    f"{model.__name__}.{field_name} contains forbidden "
                    f"substring {forbidden!r}"
                )


def test_invite_create_response_has_accept_url() -> None:
    """The one-time-return contract: this is the ONLY surface that
    carries the raw token. If you remove `accept_url`, the invite
    flow becomes unrecoverable — pin it."""
    assert "accept_url" in schemas.InviteCreateResponse.model_fields


def test_invite_read_does_NOT_have_token_or_token_hash() -> None:
    """List/detail views must never carry the token in any form."""
    fields = set(schemas.InviteRead.model_fields.keys())
    assert "token" not in fields
    assert "token_hash" not in fields


def test_invite_create_rejects_owner_role() -> None:
    """Pydantic Literal must reject 'owner' before service even runs.
    First line of defence — invite catalog policy is the second."""
    from pydantic import ValidationError
    import pytest

    with pytest.raises(ValidationError):
        schemas.InviteCreate(email="x@example.com", role_slug="owner")  # type: ignore[arg-type]


def test_invite_create_rejects_unknown_role() -> None:
    from pydantic import ValidationError
    import pytest

    with pytest.raises(ValidationError):
        schemas.InviteCreate(
            email="x@example.com", role_slug="not-a-role"  # type: ignore[arg-type]
        )


def test_invite_create_extra_field_rejected() -> None:
    """`extra='forbid'` blocks smuggled fields. Trying to set `status`
    or `token_hash` on the create payload must fail — only `email` +
    `role_slug` are caller-settable."""
    from pydantic import ValidationError
    import pytest

    with pytest.raises(ValidationError):
        schemas.InviteCreate(  # type: ignore[call-arg]
            email="x@example.com",
            role_slug="analyst",
            status="accepted",
        )


def test_team_overview_field_set_stable() -> None:
    expected = {
        "members",
        "pending_invites",
        "roles",
        "member_count",
        "pending_invite_count",
        "can_invite",
        "can_revoke_owner",
    }
    actual = set(schemas.TeamOverview.model_fields.keys())
    assert actual == expected


def test_member_summary_field_set_stable() -> None:
    expected = {
        "member_id",
        "user_id",
        "email",
        "display_name",
        "role_slugs",
        "is_owner",
        "joined_at",
        "last_active_at",
    }
    assert set(schemas.MemberSummary.model_fields.keys()) == expected


def test_invite_read_field_set_stable() -> None:
    expected = {
        "id",
        "organization_id",
        "email",
        "role_slug",
        "status",
        "invited_by_user_id",
        "expires_at",
        "accepted_at",
        "revoked_at",
        "created_at",
        "is_expired",
    }
    assert set(schemas.InviteRead.model_fields.keys()) == expected
