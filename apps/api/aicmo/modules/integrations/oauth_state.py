"""Signed `state` parameter for OAuth round-trips.

When we redirect the founder to the provider's authorize URL, we pass
a `state` query parameter. The provider includes it verbatim on the
callback. We use it to:

  1. Look up which `IntegrationConnection` row this callback belongs
     to (PENDING_AUTH → ACTIVE transition target).
  2. Defend against CSRF — an attacker who tricks the founder into
     visiting our callback URL with a forged `state` shouldn't be
     able to attach an arbitrary token to someone else's connection.

Both concerns are handled by signing a small JWT containing
`{connection_id, nonce, expires_at}`. We re-use the Fernet key that
encrypts tokens — there's no benefit to introducing a second key for
short-lived state values that are sent over the wire anyway.

Lifetime: 10 minutes. If the founder takes longer than that on the
provider's screen, they get a clean "this auth attempt expired,
please try again" message instead of a 500.
"""

from __future__ import annotations

import json
import secrets
import uuid
from datetime import datetime, timedelta, timezone

from aicmo.modules.integrations.crypto import (
    InvalidIntegrationToken,
    decrypt,
    encrypt,
)


class InvalidOAuthState(ValueError):
    """The state value couldn't be decoded or had expired. Router
    returns a clean 400."""


_TTL = timedelta(minutes=10)


def issue(connection_id: uuid.UUID) -> str:
    """Mint a fresh signed state value for an OAuth attempt."""
    payload = {
        "cid": str(connection_id),
        "nonce": secrets.token_urlsafe(16),
        "exp": (datetime.now(timezone.utc) + _TTL).timestamp(),
    }
    return encrypt(json.dumps(payload, separators=(",", ":"))).decode("ascii")


def verify(state: str) -> uuid.UUID:
    """Decode a state value and return the connection id it was issued
    against. Raises `InvalidOAuthState` if the signature fails or the
    state has expired."""
    if not state:
        raise InvalidOAuthState("Missing OAuth state parameter.")
    try:
        raw = decrypt(state.encode("ascii"))
    except InvalidIntegrationToken as exc:
        raise InvalidOAuthState(
            "OAuth state failed integrity check."
        ) from exc
    try:
        payload = json.loads(raw)
    except json.JSONDecodeError as exc:
        raise InvalidOAuthState("OAuth state is not valid JSON.") from exc

    exp = payload.get("exp")
    if not isinstance(exp, (int, float)):
        raise InvalidOAuthState("OAuth state has no expiry.")
    if datetime.now(timezone.utc).timestamp() > exp:
        raise InvalidOAuthState("OAuth state has expired.")

    cid_raw = payload.get("cid")
    if not isinstance(cid_raw, str):
        raise InvalidOAuthState("OAuth state has no connection id.")
    try:
        return uuid.UUID(cid_raw)
    except ValueError as exc:
        raise InvalidOAuthState("OAuth state has invalid connection id.") from exc
